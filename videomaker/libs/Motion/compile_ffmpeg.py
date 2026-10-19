"""Timeline → expressões de filtro ffmpeg (o caminho rápido).

Princípio P2: toda propriedade animável nasce aqui. O MoviePy é paridade, não
referência — animar é justamente o caso em que a lentidão dele explode (23x).

ESCAPE (crítico). O `filter_complex` vai como UM único argv, e cada expressão
vive dentro de `'...'` numa opção de filtro. Vírgula CRUA ali encerra o filtro e
o ffmpeg devolve um erro que não tem nada a ver com a causa. Por isso toda
vírgula gerada neste módulo (e nas expressões de `easing.py`) já sai como `\\,`,
e `tests/test_compile_ffmpeg.py` conta vírgulas não escapadas.

Expressões não têm variável auxiliar: o avaliador do ffmpeg só tem operadores e
funções embutidas. Logo o tempo (`{T}`) e o progresso aparecem repetidos na
árvore de `if` — é feio e é o único jeito.
"""

from libs.Motion import easing
from libs.Motion.errors import ValidationError
from libs.Motion.keyframes import Track

# Teto de keyframes por track. Acima disso a árvore de `if` fica grande o
# bastante para degradar o parser do ffmpeg — a cena vai para o MoviePy, que não
# tem limite de tamanho de expressão.
MAX_KEYFRAMES = 24

# Variável de tempo de cada filtro. `zoompan` não expõe `t`: conta frames de
# saída em `on` (ver FilterGraphBuilder._ZOOM_T).
T_DEFAULT = "t"


def esc(expr: str) -> str:
    """Escapa uma string CRUA para uso dentro de `'...'` num filtro.

    Para texto que vem de fora (caminho, cor, nome). As expressões montadas
    neste módulo já saem escapadas — passá-las por aqui duplicaria as barras.
    """
    return (expr.replace("\\", "\\\\").replace(",", "\\,")
            .replace(":", "\\:").replace("'", "\\'"))


def _num(value: float) -> str:
    """Número sem notação científica (que o avaliador do ffmpeg não entende)."""
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def _loop_time(track: Track, t_var: str) -> str:
    """`t` dobrado para dentro do bloco, quando a track é em loop.

    Espelha `Track.loop_time`: antes do início, tempo normal; depois do fim da
    janela, congela no fim; no meio, `mod()` sobre o período.
    """
    if not track.loop:
        return t_var
    period, start, until = track.loop
    s, p = _num(start), _num(max(0.001, period))
    folded = f"({s}+mod(({t_var})-{s}\\,{p}))"
    if until is not None:
        folded = f"if(gt({t_var}\\,{_num(until)})\\,{s}+mod({_num(until)}-{s}\\,{p})\\,{folded})"
    return f"if(lt({t_var}\\,{s})\\,{t_var}\\,{folded})"


def track_expr(track: Track, *, t_var: str = T_DEFAULT, scale: float = 1.0,
               offset: float = 0.0) -> str:
    """Expressão que devolve o valor da track em função do tempo.

    `scale`/`offset` compõem a conversão final sem uma segunda árvore: `scale`
    multiplica o valor (ex.: `scale` de 1.08 → largura `BASE_W * 1.08`) e
    `offset` soma (ex.: `x` → `BASE_X + DX(t)`).

    Track estática devolve a CONSTANTE, não a árvore — é o que permite não pagar
    custo por uma propriedade que ninguém animou.
    """
    def convert(value: float) -> str:
        return _num(offset + value * scale)

    if not track.keys:
        return convert(track.base)
    if track.is_constant():
        return convert(track.keys[0].value)

    tt = _loop_time(track, t_var)
    keys = track.keys

    # Monta de dentro para fora: o último valor é o fundo do poço dos `if`.
    expr = convert(keys[-1].value)
    for i in range(len(keys) - 2, -1, -1):
        a, b = keys[i], keys[i + 1]
        t0, t1 = _num(a.t), _num(b.t)
        v0, v1 = convert(a.value), convert(b.value)
        if abs(b.t - a.t) < 1e-9 or abs(b.value - a.value) < 1e-12:
            segment = v1 if abs(b.t - a.t) < 1e-9 else v0
        else:
            span = _num(b.t - a.t)
            progress = f"clip((({tt})-{t0})/{span}\\,0\\,1)"
            curve = easing.expr(a.ease, progress)
            delta = _num((b.value - a.value) * scale)
            segment = f"({v0}+({delta})*({curve}))"
        expr = f"if(lt({tt}\\,{t1})\\,{segment}\\,{expr})"

    # Antes do primeiro keyframe: segura o primeiro valor.
    return f"if(lt({tt}\\,{_num(keys[0].t)})\\,{convert(keys[0].value)}\\,{expr})"


# ---------------------------------------------------------------------------
# SUPORTE (gate)
# ---------------------------------------------------------------------------

def check(timeline) -> tuple:
    """(ok, motivo) — a timeline cabe no caminho ffmpeg?

    Regra de ouro do módulo de render: na dúvida, recusar. Um falso positivo
    entrega vídeo errado; um falso negativo só perde performance.
    """
    if timeline is None:
        return (True, "")

    for prop, track in timeline.tracks.items():
        # `gblur` recebe `sigma` como float fixo: não há `eval=frame` nem
        # comando de runtime no ffmpeg 4.x. Blur CONSTANTE é filtro normal;
        # blur ANIMADO só existe no MoviePy (PIL por frame).
        if prop == "blur" and not track.is_constant():
            return (False, "motion.blur animado não tem equivalente em filtro "
                           "(gblur não aceita expressão em sigma)")
        if len(track.keys) > MAX_KEYFRAMES:
            return (False, f"motion.{prop} com {len(track.keys)} keyframes "
                           f"(teto de {MAX_KEYFRAMES} no caminho ffmpeg)")
    return (True, "")


# ---------------------------------------------------------------------------
# PLANOS POR PROPRIEDADE
# ---------------------------------------------------------------------------

def check_element(element: dict, *, path: str = "") -> tuple:
    """(ok, motivo) ANTES de resolver a timeline — para o gate `can_handle`.

    Faz o que se decide olhando só o JSON: valida o schema (erro de JSON aborta
    alto, princípio P3) e recusa o que ainda não existe em filtro. O que depende
    dos valores resolvidos (contagem de keyframes) é conferido no `check()`,
    durante o render.
    """
    from libs.Motion import has_motion
    from libs.Motion.schema import check as schema_check
    from libs.Motion.timeline import normalize

    if not has_motion(element):
        return (True, "")

    if (element.get("animation") or {}).get("type") not in (None, "none"):
        raise ValidationError(
            "elemento declara `animation` (legado) e `motion` ao mesmo tempo",
            path, "escolha um dos dois")

    motion = normalize(element["motion"])
    schema_check(motion, f"{path}.motion" if path else "motion")

    return (True, "")


def _active(timeline, prop):
    track = timeline.tracks.get(prop) if timeline else None
    if track is None or track.is_static():
        return None
    return track


def zoom_expr(timeline, *, t_var: str) -> str:
    """Expressão de `zoom` (janela fixa, recorta — ken burns), ou None.

    `t_var` aqui é o tempo do `zoompan`, que não é `t`.
    """
    track = _active(timeline, "zoom")
    if track is None:
        return None
    return track_expr(track, t_var=t_var)


def rotation_expr(timeline, *, t_var: str = T_DEFAULT) -> str:
    """Expressão de `rotation` em RADIANOS para o filtro `rotate`, ou None.

    O JSON declara graus (mais legível); a conversão fica aqui, num lugar só.
    """
    track = _active(timeline, "rotation")
    if track is None:
        return None
    import math

    return track_expr(track, t_var=t_var, scale=math.pi / 180.0)


def blur_sigma(timeline) -> float:
    """Sigma CONSTANTE do `gblur`, ou None.

    Só o caso constante: o `check()` já recusou a cena quando o blur é animado,
    porque o `gblur` não aceita expressão em `sigma`.
    """
    track = _active(timeline, "blur")
    if track is None or not track.is_constant():
        return None
    return max(0.0, track.keys[0].value)


def scale_exprs(timeline, box: tuple, *, t_var: str = T_DEFAULT) -> tuple:
    """(w_expr, h_expr) para `scale=eval=frame`, ou None.

    Dimensão ÍMPAR quebra o `yuv420p`, então o `trunc(x/2)*2` é obrigatório — e
    fica aqui, não no chamador, para não haver como esquecer.
    """
    track = _active(timeline, "scale")
    if track is None:
        return None
    _, _, box_w, box_h = box
    w_expr = track_expr(track, t_var=t_var, scale=float(box_w))
    h_expr = track_expr(track, t_var=t_var, scale=float(box_h))
    return (f"trunc(({w_expr})/2)*2", f"trunc(({h_expr})/2)*2")


def position_exprs(timeline, box: tuple, *, anchor=("center", "center"),
                   scaled: bool = False, t_var: str = T_DEFAULT) -> tuple:
    """(x_expr, y_expr) para o `overlay`, ou None se nada se move.

    Duas somas entram aqui:

    1. o deslocamento animado (`x`/`y`), delta sobre a caixa do layout;
    2. a compensação da `scale`, porque o overlay posiciona pelo CANTO e um
       clipe que cresceu precisa continuar ancorado onde o JSON pediu.
       `overlay_w`/`overlay_h` são avaliados por frame, então a compensação
       acompanha a escala sem precisar repetir a curva.
    """
    bx, by, bw, bh = box
    x_track = _active(timeline, "x")
    y_track = _active(timeline, "y")
    if x_track is None and y_track is None and not scaled:
        return None

    x_expr = track_expr(x_track, t_var=t_var, offset=float(bx)) if x_track else _num(bx)
    y_expr = track_expr(y_track, t_var=t_var, offset=float(by)) if y_track else _num(by)

    if scaled:
        ax = str(anchor[0]) if len(anchor) > 0 else "center"
        ay = str(anchor[1]) if len(anchor) > 1 else "center"
        if ax == "left":
            pass                                    # canto já é o certo
        elif ax == "right":
            x_expr = f"({x_expr})+{_num(bw)}-overlay_w"
        else:
            x_expr = f"({x_expr})+({_num(bw)}-overlay_w)/2"
        if ay == "top":
            pass
        elif ay == "bottom":
            y_expr = f"({y_expr})+{_num(bh)}-overlay_h"
        else:
            y_expr = f"({y_expr})+({_num(bh)}-overlay_h)/2"

    return (x_expr, y_expr)


def opacity_plan(timeline, *, t_var: str = T_DEFAULT) -> dict:
    """Como aplicar a opacidade animada. None = nada a fazer.

    Duas estratégias, nessa ordem:

    - `{"kind": "fade", "segments": [(tipo, start, duração), …]}` — o filtro
      `fade` nativo, barato. Serve quando cada trecho é linear entre 0 e 1,
      que cobre fade-in, fade-out e piscadas (é por isso que os presets usam
      easing `linear` na opacidade).
    - `{"kind": "geq", "expr": …}` — expressão por pixel, caso geral. Custa
      caro em 1080p; o renderer loga aviso para a conta aparecer no profile.
    """
    track = _active(timeline, "opacity")
    if track is None:
        return None

    low, high = track.bounds()
    if low < -1e-6 or high > 1 + 1e-6:
        return {"kind": "geq", "expr": f"clip({track_expr(track, t_var=t_var)}\\,0\\,1)"}

    segments = []
    linear = True
    for i in range(len(track.keys) - 1):
        a, b = track.keys[i], track.keys[i + 1]
        if abs(b.value - a.value) < 1e-9:
            continue                                  # patamar: nada a fazer
        rising = b.value > a.value
        # O `fade` nativo é SEMPRE 0→1 (ou 1→0) e sempre linear. Trecho que
        # começa/termina no meio (0,3 → 0,8) ou com easing não-linear precisa
        # do caminho geral.
        if a.ease != "linear" or min(a.value, b.value) > 1e-6 \
                or max(a.value, b.value) < 1 - 1e-6:
            linear = False
            break
        segments.append(("in" if rising else "out", a.t, b.t - a.t))

    if linear and segments:
        return {"kind": "fade", "segments": segments,
                "starts_hidden": track.keys[0].value < 0.5}
    return {"kind": "geq", "expr": f"clip({track_expr(track, t_var=t_var)}\\,0\\,1)"}


def enable_expr(timeline, *, t_var: str = T_DEFAULT) -> str:
    """`enable=` do overlay a partir de `visible`, ou None."""
    if timeline is None or not timeline.visible:
        return None
    start, end = timeline.visible
    return f"between({t_var}\\,{_num(start)}\\,{_num(end)})"
