"""AssBuilder — converte legendas do pipeline em um arquivo ASS (libass).

Motivação (fase 1 do plano de performance): hoje cada palavra do karaokê é um
`ImageClip` PIL composto pelo MoviePy **frame a frame** em Python. Medido em
1080p, uma cena de 5 s com fundo+zoom+karaokê levava 47,6 s; o mesmo resultado
via filtergraph (`ass` + `scale`) levou 2,0 s — ~23x.

O ASS é renderizado pelo libass dentro do ffmpeg, em C, sem nenhum frame
atravessando o interpretador. Como o texto é vetorial, também sai mais nítido
que o bitmap PIL redimensionado.

Escopo: este módulo só CONSTRÓI o arquivo .ass. Quem o aplica é o
`FFmpegSceneRenderer`, via filtro `ass=`.

Dois detalhes que exigiram cuidado (ambos já resolvidos, mas fáceis de reintroduzir):

  - **nome da fonte**: o ASS referencia a fonte por NOME, não por caminho. É
    obrigatório usar a família legada (nameID 1 = "Montserrat Black"), e não o
    Typographic Family (nameID 16 = "Montserrat"), senão o fontconfig resolve
    para o peso 400 e a legenda sai em Regular no lugar de Black. Ver
    `resolve_font_name`.
  - **tamanho**: PIL e libass interpretam `font_size` de formas diferentes; o
    fator é calibrado por fonte em `ass_size_scale` e vale também para stroke,
    sombra e blur.

Sombra borrada (`shadow.blur`) e estilos sem fonte legível caem no caminho
MoviePy — ver `can_handle_style` para o porquê (medido, não suposto).
"""

import os
import struct

# ---------------------------------------------------------------------------
# COR
# ---------------------------------------------------------------------------


def _to_ass_color(rgba: tuple, alpha_override: float | None = None) -> str:
    """(r,g,b,a) → &HAABBGGRR (ASS usa BGR + alpha invertido: 00=opaco)."""
    r, g, b = int(rgba[0]), int(rgba[1]), int(rgba[2])
    a = rgba[3] if len(rgba) > 3 else 255
    if alpha_override is not None:
        a = int(255 * float(alpha_override))
    inv_a = 255 - int(a)      # ASS: 00 = totalmente opaco, FF = transparente
    return f"&H{inv_a:02X}{b:02X}{g:02X}{r:02X}"


def _fmt_time(seconds: float) -> str:
    """Segundos → H:MM:SS.cc (centésimos), formato de tempo do ASS."""
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    rest = s - h * 3600 - m * 60
    return f"{h}:{m:02d}:{rest:05.2f}"


# ---------------------------------------------------------------------------
# FONTE
# ---------------------------------------------------------------------------

_font_name_cache: dict = {}


def _read_name_records(font_path: str) -> dict:
    """Lê a tabela `name` de um TTF/OTF → {name_id: valor}.

    Retorna {} se o arquivo não for legível como sfnt.
    """
    out: dict = {}
    try:
        with open(font_path, "rb") as f:
            data = f.read()

        # Cabeçalho sfnt: numTables em offset 4; diretório de tabelas em 12.
        num_tables = struct.unpack(">H", data[4:6])[0]
        name_off = None
        for i in range(num_tables):
            rec = 12 + i * 16
            if data[rec:rec + 4] == b"name":
                name_off, _len = struct.unpack(">II", data[rec + 8:rec + 16])
                break
        if name_off is None:
            return {}

        count, string_off = struct.unpack(">HH", data[name_off + 2:name_off + 6])
        strings_base = name_off + string_off
        for i in range(count):
            rec = name_off + 6 + i * 12
            platform_id, encoding_id, _lang, name_id, length, offset = struct.unpack(
                ">HHHHHH", data[rec:rec + 12]
            )
            raw = data[strings_base + offset: strings_base + offset + length]
            try:
                if platform_id == 3 or encoding_id == 1:   # UTF-16BE
                    value = raw.decode("utf-16-be").strip()
                else:
                    value = raw.decode("latin-1").strip()
            except Exception:
                continue
            # Primeiro registro válido de cada nameID vence.
            if value and name_id not in out:
                out[name_id] = value
    except Exception:
        return {}
    return out


def resolve_font_name(font_path: str) -> str | None:
    """Nome de família de um TTF/OTF, para referência no ASS.

    Usa a **família legada (nameID 1)**, que inclui o peso no nome
    ("Montserrat Black"), e NÃO o Typographic Family (nameID 16), que o remove
    ("Montserrat"). A distinção é crítica: com "Montserrat" no estilo, o
    fontconfig resolve para o peso 400 e o libass renderiza Montserrat-Regular
    no lugar de Montserrat-Black — a legenda sai visivelmente mais fina.

    Retorna None se não conseguir ler; nesse caso a cena cai no caminho MoviePy
    em vez de renderizar com a fonte errada.

    Itálico continua vindo do flag no estilo (ver `font_is_italic`), porque
    `X-Black.ttf` e `X-BlackItalic.ttf` compartilham o nameID 1.
    """
    if not font_path:
        return None
    key = os.path.abspath(font_path)
    if key in _font_name_cache:
        return _font_name_cache[key]

    records = _read_name_records(font_path)
    name = records.get(1) or records.get(16)
    _font_name_cache[key] = name
    return name


_scale_cache: dict = {}


def ass_size_scale(font_path: str) -> float:
    """Fator para converter um `font_size` do pipeline (PIL) em `Fontsize` ASS.

    PIL e libass interpretam "tamanho da fonte" de formas diferentes: com o mesmo
    número, o texto renderizado pelo libass sai visivelmente menor (medido em
    Montserrat-Black: ~1,70x). O fator depende das métricas de cada fonte, e
    tentativas de derivá-lo de `unitsPerEm`/`hhea` não bateram com o observado
    (previa 1,22 contra 1,70 reais) — libass aplica sua própria normalização.

    Em vez de adivinhar, calibramos EMPIRICAMENTE uma vez por fonte: renderiza a
    mesma string nos dois motores e compara a largura da tinta. O resultado fica
    em cache (memória + disco) porque exige uma chamada de ffmpeg.

    Retorna 1.0 se a calibração falhar — o texto sai menor, mas nunca quebra.
    """
    if not font_path:
        return 1.0
    key = os.path.abspath(font_path)
    if key in _scale_cache:
        return _scale_cache[key]

    scale = _load_cached_scale(key)
    if scale is None:
        scale = _calibrate_scale(font_path)
        _store_cached_scale(key, scale)

    _scale_cache[key] = scale
    return scale


def _scale_cache_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "cache", "ass_font_scale.json")


def _load_cached_scale(key: str):
    import json
    path = _scale_cache_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get(key)
        # Invalida se o arquivo da fonte mudou.
        if entry and entry.get("mtime") == os.path.getmtime(key):
            return float(entry["scale"])
    except Exception:
        pass
    return None


def _store_cached_scale(key: str, scale: float):
    import json
    path = _scale_cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        data[key] = {"scale": float(scale), "mtime": os.path.getmtime(key)}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass


def _calibrate_scale(font_path: str) -> float:
    """Mede largura da tinta em PIL vs libass e devolve a razão PIL/ASS."""
    import subprocess
    import tempfile
    import numpy as np

    PROBE, SIZE = "HAMBURGEFONTS", 100
    try:
        from libs.Subtitle.SubtitleUtils import load_font, measure
        font = load_font(font_path, SIZE)
        pil_w, _, _, _ = measure(PROBE, font, 0)
        if not pil_w:
            return 1.0

        with tempfile.TemporaryDirectory() as td:
            builder = AssBuilder((1920, 1080))
            builder.add_text(
                PROBE,
                {"font_path": font_path, "font_size": SIZE, "fill": "#FFFFFF",
                 "stroke_enabled": False, "shadow_enabled": False},
                (960, 540), 0.0, 1.0,
                _raw_size=True,          # evita recursão: não re-escalar aqui
            )
            ass_path = os.path.join(td, "probe.ass")
            builder.write(ass_path)
            png = os.path.join(td, "probe.png")
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30:d=1",
                 "-vf", f"ass={ass_path}:fontsdir={os.path.dirname(os.path.abspath(font_path))}",
                 "-frames:v", "1", png],
                check=True, capture_output=True,
            )
            from PIL import Image
            arr = np.array(Image.open(png).convert("L"))
            cols = np.where((arr > 128).any(axis=0))[0]
            if len(cols) < 2:
                return 1.0
            ass_w = int(cols[-1] - cols[0])
            if ass_w <= 0:
                return 1.0
            return round(pil_w / ass_w, 4)
    except Exception:
        return 1.0


def font_is_italic(font_path: str) -> bool:
    """True se o TTF declara subfamília itálica/oblíqua.

    Necessário porque a família ASS não distingue `X-Black` de `X-BlackItalic`;
    o flag Italic no estilo é o que faz o libass escolher o arquivo certo.
    """
    records = _read_name_records(font_path)
    sub = (records.get(17) or records.get(2) or "").lower()
    return "italic" in sub or "oblique" in sub


# ---------------------------------------------------------------------------
# BUILDER
# ---------------------------------------------------------------------------

# Alinhamento ASS (numpad). 5 = centro, usado com \pos (que ancora no centro
# do texto, batendo com o layout já calculado em pixels pelo pipeline).
_ALIGN_CENTER = 5


class AssBuilder:
    """Constrói um arquivo .ass a partir de itens de texto posicionados.

    A entrada é deliberadamente a MESMA estrutura que o KaraokeSubtitle já
    calcula (palavra, posição em pixels, tempos, estilo) — assim a lógica de
    agrupamento, fit de fonte e layout continua sendo a existente, testada, e só
    a RENDERIZAÇÃO muda de PIL/MoviePy para libass.
    """

    def __init__(self, resolution: tuple):
        self.width, self.height = int(resolution[0]), int(resolution[1])
        self._styles: dict = {}     # nome → linha de estilo
        self._events: list = []

    # -- validação ---------------------------------------------------------

    @staticmethod
    def can_handle_style(style: dict) -> tuple:
        """(ok, motivo) — o estilo é reproduzível fielmente em ASS?

        `shadow.blur` recusa de propósito. A tag `\\blur` do libass existe, mas
        borra o GLIFO junto com a sombra, enquanto o caminho PIL borra apenas a
        camada de sombra e mantém o texto nítido. Medido em Montserrat Black 140
        (pixels de branco sólido no miolo do texto):

            blur=0 → 13261    blur=3 → 8062    blur=6 → 2598    blur=9 → 164

        Com o blur=9 que o canal usa, o texto praticamente desaparece. Não há
        equivalente fiel, então a cena vai para o MoviePy.
        """
        if float(style.get("blur_radius", 0) or 0) > 0 and style.get("shadow_enabled"):
            return (False, "shadow.blur borra o glifo em ASS (só a sombra deveria borrar)")
        font_path = style.get("font_path")
        if font_path and not os.path.exists(font_path):
            return (False, f"fonte não encontrada: {font_path}")
        if font_path and not resolve_font_name(font_path):
            return (False, f"não foi possível ler o nome da família em {font_path}")
        return (True, "")

    # -- estilos -----------------------------------------------------------

    def _style_name(self, style: dict, raw_size: bool = False) -> str:
        """Registra (ou reusa) um estilo ASS e devolve seu nome.

        `raw_size=True` usa o font_size sem a correção de escala — só a
        calibração usa isso (senão a medição se auto-referenciaria).
        """
        font_path = style.get("font_path")
        font_name = resolve_font_name(font_path) or "Sans"
        base_size = int(style.get("font_size", 48))
        # PIL e libass dimensionam diferente; converte p/ manter o tamanho visual
        # que o layout do pipeline calculou.
        font_size = base_size if raw_size else max(1, int(round(base_size * ass_size_scale(font_path))))

        from libs.Subtitle.SubtitleUtils import resolve_color

        primary = _to_ass_color(resolve_color(style.get("fill", "white")))
        # Stroke e sombra estão na mesma escala do texto: acompanham o fator.
        scale = 1.0 if raw_size else ass_size_scale(font_path)
        stroke_w = (
            max(1, int(round(int(style.get("stroke_width", 0)) * scale)))
            if style.get("stroke_enabled") and int(style.get("stroke_width", 0)) > 0
            else 0
        )
        outline = _to_ass_color(resolve_color(style.get("stroke_color", "black")))

        shadow_enabled = bool(style.get("shadow_enabled"))
        shadow_offset = style.get("shadow_offset") or (0, 0)
        # ASS tem um único valor de deslocamento (x=y); usa o maior componente.
        shadow_depth = (
            int(round(max(abs(int(shadow_offset[0])), abs(int(shadow_offset[1]))) * scale))
            if shadow_enabled else 0
        )
        back = _to_ass_color(
            resolve_color(style.get("shadow_color", "black")),
            alpha_override=float(style.get("shadow_opacity", 0.8)) if shadow_enabled else 0.0,
        )

        italic = -1 if font_is_italic(font_path) else 0

        key = (font_name, font_size, primary, outline, back, stroke_w, shadow_depth, italic)
        existing = self._styles.get(key)
        if existing:
            return existing[0]

        name = f"S{len(self._styles)}"
        # BorderStyle=1 (outline + shadow), Alignment=5 (centro), margens 0
        # porque a posição vem de \pos por evento. Bold=-1: as fontes do projeto
        # já vêm no peso desejado no próprio arquivo (Black/Bold/…), então o
        # peso é do arquivo, não sintético.
        line = (
            f"Style: {name},{font_name},{font_size},{primary},{primary},{outline},{back},"
            f"0,{italic},0,0,100,100,0,0,1,{stroke_w},{shadow_depth},{_ALIGN_CENTER},0,0,0,1"
        )
        self._styles[key] = (name, line)
        return name

    # -- eventos -----------------------------------------------------------

    def add_text(self, text: str, style: dict, center_xy: tuple,
                 start: float, end: float, _raw_size: bool = False):
        """Adiciona uma palavra/linha posicionada pelo CENTRO em pixels."""
        if not text or end <= start:
            return
        style_name = self._style_name(style, raw_size=_raw_size)
        cx, cy = int(round(center_xy[0])), int(round(center_xy[1]))
        # \an5 = ancora no centro do texto; \pos posiciona esse centro.
        tags = f"\\an{_ALIGN_CENTER}\\pos({cx},{cy})"
        payload = f"{{{tags}}}{_escape(text)}"
        self._events.append(
            f"Dialogue: 0,{_fmt_time(start)},{_fmt_time(end)},{style_name},,0,0,0,,{payload}"
        )

    # -- saída -------------------------------------------------------------

    def is_empty(self) -> bool:
        return not self._events

    def build(self) -> str:
        header = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {self.width}",
            f"PlayResY: {self.height}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: None",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
        ]
        header += [line for (_name, line) in self._styles.values()]
        header += [
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text",
        ]
        header += self._events
        return "\n".join(header) + "\n"

    def write(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.build())
        return path


def _escape(text: str) -> str:
    """Escapa o que o ASS trata como marcação dentro do texto do evento."""
    return (
        text.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("\n", "\\N")
    )
