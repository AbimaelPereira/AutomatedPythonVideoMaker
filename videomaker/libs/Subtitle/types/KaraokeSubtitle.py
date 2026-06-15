"""
KaraokeSubtitle — legenda "karaokê acumulativo word-by-word" (type "karaoke").

As palavras surgem uma a uma, no tempo exato da fala (start do SRT por palavra),
e se acumulam na tela. Quando o bloco atual "fecha", a tela limpa e o próximo
recomeça do zero. O tamanho da fonte é calculado dinamicamente para preencher a
largura disponível (entre paddings); a altura é ignorada de propósito.

Dois MODOS de agrupamento, escolhidos pela presença dos campos no JSON:

  ── MODO LEGADO (default) ──────────────────────────────────────────────
  Ativo quando NEM `min_chars_per_line` NEM `line_fill_ratio` estão setados.
  Cada palavra recebe, em rotação, um estilo da `palette` e é dimensionada
  sozinha. A tela limpa a cada `words_per_group` palavras. Layouts:
    - "one_per_line": cada palavra numa linha própria, empilhadas.
    - "fill_line":    acumula palavras na mesma linha até estourar a largura.

  ── MODO LINHAS (novo) ─────────────────────────────────────────────────
  Ativo quando `min_chars_per_line` E/OU `line_fill_ratio` estão setados.
  As palavras são agrupadas em LINHAS por dois critérios combináveis:
    - `min_chars_per_line`: piso anti-órfã — a linha não fecha enquanto não
      atingir esse total de caracteres (palavra curta nunca fica sozinha).
    - `line_fill_ratio`: teto de largura — a linha fecha quando adicionar a
      próxima palavra faria a linha passar dessa fração da faixa.
  Com os dois ativos: a linha fecha quando `min_chars` foi atingido E a
  próxima palavra estouraria o `line_fill_ratio`. A última linha órfã (abaixo
  do min_chars) é grudada na linha anterior. Depois, `lines_per_group` linhas
  formam um bloco que limpa a tela. Neste modo a `palette` rotaciona POR LINHA
  (não por palavra) e o `font_size` é UNIFORME por linha (fit da linha inteira).

Em ambos os modos o timing é word-by-word: cada palavra aparece no seu start
do SRT e some quando o bloco limpa. Sem animação de entrada.
"""

import numpy as np
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip

from libs.Subtitle import SubtitleUtils as utils


# Estilo default usado quando a paleta não é informada (1 cor branca simples).
_DEFAULT_PALETTE = [
    {
        "fill": "#FFFFFF",
        "stroke": "#000000",
        "stroke_width": 3,
        "shadow": {"color": "#000000", "opacity": 0.85, "blur": 6, "offset": [4, 4]},
        "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf",
    },
]


class KaraokeSubtitle:
    def __init__(self, params=None):
        defaults = {
            "subtitle_narration_file": None,

            "words_per_group": 4,
            "layout": "one_per_line",          # ou "fill_line" (só modo legado)
            "uppercase": True,
            "palette": _DEFAULT_PALETTE,

            # --- Modo LINHAS (novo) — opt-in. Ver docstring. ---
            # Ativo se qualquer um destes dois estiver setado (não-None).
            "min_chars_per_line": None,        # piso anti-órfã (int)
            "line_fill_ratio": None,           # teto de largura por linha (0–1)
            "lines_per_group": 3,              # linhas por tela antes de limpar

            # Limites do dimensionamento dinâmico por palavra.
            "max_font_size": 300,
            "min_font_size": 24,
            # Espaçamento vertical entre linhas (fração da altura da linha).
            "line_gap_ratio": 0.12,

            "has_visual_elements": False,
            "resolution_output": (1080, 1920),
            "padding_side": 50,
            "padding_bottom": 850,
            "padding_top": 100,
            "subtitle_position": "center",
            "placement": None,   # novo: {"anchor":[x,y], "region": "30%"}
        }
        if params:
            defaults.update(params)

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.palette:
            self.palette = _DEFAULT_PALETTE

        import os
        if not self.subtitle_narration_file or not os.path.exists(self.subtitle_narration_file):
            raise FileNotFoundError(
                f"Arquivo de legenda (.srt) não encontrado: {self.subtitle_narration_file}"
            )

    # ------------------------------------------------------------------
    # ESTILO
    # ------------------------------------------------------------------

    def _build_style(self, palette_item: dict, font_size: int) -> dict:
        """Converte um item de paleta (JSON) no dict de estilo do SubtitleUtils."""
        shadow = palette_item.get("shadow")
        stroke_width = int(palette_item.get("stroke_width", 0))
        offset = (0, 0)
        if shadow and shadow.get("offset"):
            offset = tuple(shadow["offset"])

        return {
            "font_path": palette_item.get("font_path", _DEFAULT_PALETTE[0]["font_path"]),
            "font_size": font_size,
            "fill": palette_item.get("fill", "white"),
            "stroke_enabled": stroke_width > 0,
            "stroke_color": palette_item.get("stroke", "black"),
            "stroke_width": stroke_width,
            "shadow_enabled": bool(shadow),
            "shadow_color": (shadow or {}).get("color", "black"),
            "shadow_opacity": (shadow or {}).get("opacity", 0.8),
            "blur_radius": (shadow or {}).get("blur", 0.0),
            "shadow_offset": offset,
        }

    # ------------------------------------------------------------------
    # GERAÇÃO
    # ------------------------------------------------------------------

    def _line_mode_active(self) -> bool:
        """True quando algum critério do MODO LINHAS está setado no JSON."""
        return self.min_chars_per_line is not None or self.line_fill_ratio is not None

    def _cased(self, word: str, palette_item: dict) -> str:
        """Aplica a caixa (maiúsculas) ao texto da palavra.

        Por padrão usa o `uppercase` global, mas um item de paleta pode
        sobrescrever com sua própria chave `uppercase` (True/False) — permitindo,
        p.ex., deixar só UM estilo em maiúsculas no karaokê.
        """
        up = palette_item.get("uppercase", self.uppercase)
        return word.upper() if up else word

    def generate(self):
        # Parseia CRU (sem forçar caixa) para que a caixa possa ser decidida
        # por item de paleta no render. O agrupamento usa o nº de caracteres,
        # que não muda com upper/lower.
        words = utils.parse_srt_words(self.subtitle_narration_file, uppercase=False)
        if not words:
            return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        # Resolve a caixa de posicionamento (placement novo OU legado).
        # A LARGURA da caixa vira o safe_w → palavras são dimensionadas para
        # caber na faixa (ex.: region "30%" encolhe as palavras).
        self._box = utils.resolve_subtitle_box(
            {
                "placement": self.placement,
                "subtitle_position": self.subtitle_position,
                "has_visual_elements": self.has_visual_elements,
                "padding_side": self.padding_side,
                "padding_top": self.padding_top,
                "padding_bottom": self.padding_bottom,
            },
            self.resolution_output,
        )

        groups = (
            self._build_line_groups(words)
            if self._line_mode_active()
            else self._build_legacy_groups(words)
        )

        clips = []
        for group in groups:
            clips.extend(self._render_group(group, self._box))

        if not clips:
            return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        return CompositeVideoClip(clips, size=self.resolution_output)

    # ------------------------------------------------------------------
    # AGRUPAMENTO  (palavras → grupos de linhas; cada linha = lista de palavras)
    # ------------------------------------------------------------------
    #
    # Formato comum de "grupo" consumido por `_render_group`:
    #   grupo = [ linha, linha, ... ]   onde linha = [ word_dict, ... ]
    # Cada `word_dict` é {word, start, end} vindo do SRT.

    def _build_legacy_groups(self, words: list) -> list:
        """MODO LEGADO: grupos fixos de `words_per_group`; a quebra em linhas
        (one_per_line / fill_line) é resolvida depois, por palavra."""
        wpg = max(1, int(self.words_per_group))
        groups = []
        for g_start in range(0, len(words), wpg):
            chunk = words[g_start:g_start + wpg]
            if self.layout == "fill_line":
                # Uma "linha lógica" só; o fill real por largura acontece no
                # render (palavra a palavra), como antes.
                groups.append([chunk])
            else:  # one_per_line
                groups.append([[w] for w in chunk])
        return groups

    def _build_line_groups(self, words: list) -> list:
        """MODO LINHAS: agrupa palavras em linhas por min_chars/line_fill_ratio,
        depois empacota `lines_per_group` linhas por bloco."""
        lines = self._words_into_lines(words)
        lpg = max(1, int(self.lines_per_group))
        return [lines[i:i + lpg] for i in range(0, len(lines), lpg)]

    def _words_into_lines(self, words: list) -> list:
        """Quebra a sequência de palavras em linhas conforme os critérios ativos.

        - min_chars_per_line: a linha não fecha enquanto não atingir esse total.
        - line_fill_ratio: a linha fecha quando adicionar a próxima palavra
          faria a largura passar de `ratio * largura_da_faixa`.
        Última linha órfã (abaixo do min_chars) é grudada na anterior.
        """
        box_w = self._box["width"]
        min_chars = self.min_chars_per_line
        ratio = self.line_fill_ratio
        # Largura-alvo em pixels (só usada se line_fill_ratio ativo).
        target_w = int(box_w * float(ratio)) if ratio is not None else None

        # Fonte de referência p/ medir largura ao agrupar: a 1ª da paleta num
        # tamanho fixo. Serve só p/ comparar palavras entre si (o fit final é
        # recalculado por linha depois). Evita medir em N tamanhos durante o
        # agrupamento.
        ref = self.palette[0]
        ref_font_path = ref.get("font_path", _DEFAULT_PALETTE[0]["font_path"])
        ref_size = 100

        def text_width(text: str) -> int:
            font = utils.load_font(ref_font_path, ref_size)
            w, _, _, _ = utils.measure(text, font, 0)
            return w

        def line_chars(line: list) -> int:
            return sum(len(w["word"]) for w in line)

        lines, current = [], []
        for w in words:
            tentative = current + [w]
            chars_ok = (min_chars is None) or (line_chars(current) >= int(min_chars))
            if ratio is not None and current:
                joined = " ".join(x["word"] for x in tentative)
                width_over = text_width(joined) > target_w
            else:
                width_over = False

            # Fecha ANTES de adicionar `w` se o piso de chars já caiu e a
            # largura estouraria. Sem line_fill_ratio, o único gatilho é o
            # min_chars: fecha assim que o piso é atingido.
            should_close = current and chars_ok and (width_over if ratio is not None else True)
            if should_close:
                lines.append(current)
                current = [w]
            else:
                current.append(w)
        if current:
            lines.append(current)

        # Última linha órfã → gruda na anterior.
        if (
            len(lines) > 1
            and min_chars is not None
            and line_chars(lines[-1]) < int(min_chars)
        ):
            lines[-2].extend(lines[-1])
            lines.pop()

        return lines

    # ------------------------------------------------------------------
    # RENDER DE UM GRUPO
    # ------------------------------------------------------------------

    def _render_group(self, group: list, box: dict) -> list:
        """Renderiza um grupo (lista de linhas) em ImageClips word-by-word.

        - Modo LINHAS: paleta rotaciona por linha; font_size uniforme por linha.
        - Modo LEGADO: paleta rotaciona por palavra; font_size por palavra.
        O modo é inferido por `_line_mode_active()`.
        """
        safe_w = box["width"]
        line_mode = self._line_mode_active()

        # group_end = fim da última palavra de todo o grupo (quando a tela limpa).
        group_end = max(w["end"] for line in group for w in line)

        rendered_lines = []  # cada item: lista de {word, arr, h, w}
        for li, line in enumerate(group):
            if line_mode:
                palette_item = self.palette[li % len(self.palette)]
                rendered_lines.append(self._render_line_uniform(line, palette_item, safe_w))
            else:
                rendered_lines.append(self._render_line_per_word(line, safe_w))

        positions = self._layout_lines(rendered_lines, box)

        clips = []
        for item, (x, y) in positions:
            arr = item["arr"]
            start = item["word"]["start"]
            duration = max(0.05, group_end - start)

            rgb = arr[:, :, :3]
            alpha = arr[:, :, 3].astype(float) / 255.0

            clip = ImageClip(rgb, ismask=False).set_duration(duration)
            clip = clip.set_mask(ImageClip(alpha, ismask=True).set_duration(duration))
            clip = (
                clip.set_position((int(x), int(y)))
                .fl_image(utils.force_rgb)
                .set_start(start)
                .set_end(group_end)
            )
            clips.append(clip)
        return clips

    def _render_line_uniform(self, line: list, palette_item: dict, safe_w: int) -> list:
        """MODO LINHAS: um único font_size para a linha toda (fit da linha
        inteira, incluindo os espaços), todas as palavras na mesma fonte/cor."""
        font_path = palette_item.get("font_path", _DEFAULT_PALETTE[0]["font_path"])
        stroke_width = int(palette_item.get("stroke_width", 0))
        eff_stroke = stroke_width * 2 if stroke_width > 0 else 0

        joined = " ".join(self._cased(w["word"], palette_item) for w in line)
        font_size = utils.fit_font_size(
            joined, font_path, max_width=safe_w,
            stroke_width=eff_stroke,
            max_size=int(self.max_font_size), min_size=int(self.min_font_size),
        )
        style = self._build_style(palette_item, font_size)
        style["stroke_width"] = eff_stroke
        # Baseline/altura fixas: palavras da mesma linha (mesmo font/size)
        # compartilham baseline → ficam alinhadas ao serem empilhadas lado a lado.
        style["fixed_line_box"] = True

        rendered = []
        for w in line:
            arr = utils.render_text(self._cased(w["word"], palette_item), style)
            rendered.append({"word": w, "arr": arr, "h": arr.shape[0], "w": arr.shape[1]})
        return rendered

    def _render_line_per_word(self, line: list, safe_w: int) -> list:
        """MODO LEGADO: cada palavra com seu estilo (rotação por palavra) e
        seu próprio fit de largura."""
        rendered = []
        for i, w in enumerate(line):
            palette_item = self.palette[i % len(self.palette)]
            font_path = palette_item.get("font_path", _DEFAULT_PALETTE[0]["font_path"])
            stroke_width = int(palette_item.get("stroke_width", 0))
            eff_stroke = stroke_width * 2 if stroke_width > 0 else 0

            cased = self._cased(w["word"], palette_item)
            font_size = utils.fit_font_size(
                cased, font_path, max_width=safe_w,
                stroke_width=eff_stroke,
                max_size=int(self.max_font_size), min_size=int(self.min_font_size),
            )
            style = self._build_style(palette_item, font_size)
            style["stroke_width"] = eff_stroke
            arr = utils.render_text(cased, style)
            rendered.append({"word": w, "arr": arr, "h": arr.shape[0], "w": arr.shape[1]})
        return rendered

    # ------------------------------------------------------------------
    # LAYOUT
    # ------------------------------------------------------------------

    def _block_y(self, total_h: int, box: dict) -> int:
        """Posição Y do topo do bloco de legenda, alinhado dentro da caixa."""
        anchor_y = box.get("anchor_y", "center")
        if anchor_y == "top":
            return box["y"]
        if anchor_y == "bottom":
            return box["y"] + max(0, box["height"] - total_h)
        # center (default)
        return box["y"] + max(0, (box["height"] - total_h) // 2)

    def _visual_lines(self, rendered_lines: list, safe_w: int) -> list:
        """Converte as linhas LÓGICAS (de `_render_group`) em linhas VISUAIS.

        No modo legado com `layout: "fill_line"`, uma linha lógica pode conter
        palavras demais para a largura; aqui ela é quebrada em várias linhas
        visuais por largura acumulada (comportamento histórico). Nos demais
        casos cada linha lógica já é uma linha visual.
        """
        if self._line_mode_active() or self.layout != "fill_line":
            return list(rendered_lines)

        visual = []
        for logical in rendered_lines:
            current, cur_w = [], 0
            for it in logical:
                if current and cur_w + it["w"] > safe_w:
                    visual.append(current)
                    current, cur_w = [], 0
                current.append(it)
                cur_w += it["w"]
            if current:
                visual.append(current)
        return visual

    def _layout_lines(self, rendered_lines: list, box: dict) -> list:
        """Calcula (x, y) de cada palavra a partir de linhas já renderizadas.

        Retorna lista de pares (item, (x, y)) — uma entrada por palavra, na
        ordem em que aparecem. Posições fixas para o grupo todo (as palavras só
        vão surgindo nelas, sem reflow). Tudo dentro da caixa resolvida.
        """
        safe_w = box["width"]
        lines = self._visual_lines(rendered_lines, safe_w)

        # Altura/limites da TINTA por linha (pixels realmente visíveis), não a
        # altura cheia do array. O array inclui o padding do render e — no modo
        # linha — a caixa cheia da fonte (ascent+descent), o que inflava muito o
        # espaço entre linhas. Avançar pela tinta faz `line_gap_ratio` controlar
        # o gap visível de verdade. `ink_top` por linha alinha as palavras (que
        # compartilham baseline no modo linha) ao topo da tinta.
        line_bounds = [self._line_ink_bounds(line) for line in lines]   # (top, height)
        visible_heights = [h for (_, h) in line_bounds]

        gap = int(max(visible_heights) * float(self.line_gap_ratio)) if visible_heights else 0
        total_h = sum(visible_heights) + gap * (len(lines) - 1)

        block_top = self._block_y(total_h, box)

        out = []
        y = block_top
        for line, (ink_top, vh) in zip(lines, line_bounds):
            line_w = sum(it["w"] for it in line)
            x = box["x"] + max(0, (safe_w - line_w) // 2)
            for it in line:
                # Desloca a palavra p/ que a tinta da linha comece exatamente em y
                # (preserva o baseline compartilhado dentro da linha).
                wy = y - ink_top
                out.append((it, (x, wy)))
                x += it["w"]
            y += vh + gap

        return out

    @staticmethod
    def _line_ink_bounds(line: list) -> tuple:
        """Retorna (ink_top, ink_height) da linha — a faixa de linhas de pixel
        com alguma opacidade, considerando todas as palavras da linha juntas.
        Fallback para a altura cheia do array se a linha estiver vazia/transparente."""
        top = None
        bottom = None
        for it in line:
            arr = it["arr"]
            if arr.shape[2] < 4:
                rows = np.where(arr.any(axis=(1, 2)))[0]
            else:
                rows = np.where(arr[:, :, 3].any(axis=1))[0]
            if len(rows) == 0:
                continue
            t, b = int(rows[0]), int(rows[-1])
            top = t if top is None else min(top, t)
            bottom = b if bottom is None else max(bottom, b)
        if top is None:
            h = max((it["h"] for it in line), default=1)
            return 0, h
        return top, (bottom - top + 1)
