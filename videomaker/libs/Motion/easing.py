"""Curvas de easing em DUAS implementações que precisam concordar.

Cada easing existe como função Python (caminho MoviePy) e como expressão de
filtro ffmpeg (caminho rápido). Se as duas divergirem, o mesmo JSON gera vídeos
diferentes dependendo do backend — por isso `tests/test_motion_core.py` amostra
as 21 curvas nos dois avaliadores e exige `|py - ff| < 0.004` (1/255).

O avaliador do ffmpeg não aceita função definida pelo usuário: toda curva é
inline, montada por substituição de `{p}` (a sub-expressão de progresso, que no
uso real é algo como `clip((t-0.4)/0.55\\,0\\,1)`). `{p}` aparece várias vezes na
mesma expressão de propósito — não há como guardar valor intermediário.

Vocabulário FECHADO (princípio P5): nome fora desta tabela é erro de validação.
"""

import math

# Constantes canônicas das curvas `back`/`elastic`/`bounce` (as mesmas do
# easings.net), repetidas literalmente nas expressões ffmpeg.
_C1 = 1.70158
_C3 = _C1 + 1.0        # 2.70158
_C2 = _C1 * 1.525      # 2.5949095
_C4 = 2 * math.pi / 3
_N1 = 7.5625
_D1 = 2.75


def _in_out_back_py(p: float) -> float:
    if p < 0.5:
        return ((2 * p) ** 2 * ((_C2 + 1) * 2 * p - _C2)) / 2
    return ((2 * p - 2) ** 2 * ((_C2 + 1) * (2 * p - 2) + _C2) + 2) / 2


def _out_bounce_py(p: float) -> float:
    if p < 1 / _D1:
        return _N1 * p * p
    if p < 2 / _D1:
        p -= 1.5 / _D1
        return _N1 * p * p + 0.75
    if p < 2.5 / _D1:
        p -= 2.25 / _D1
        return _N1 * p * p + 0.9375
    p -= 2.625 / _D1
    return _N1 * p * p + 0.984375


def _out_elastic_py(p: float) -> float:
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return 2 ** (-10 * p) * math.sin((p * 10 - 0.75) * _C4) + 1


# Sub-expressões do out_bounce, montadas de dentro para fora para a árvore de
# `if` não ficar ilegível na tabela.
_BOUNCE_2 = f"({_N1}*pow(({{p}})-{1.5 / _D1}\\,2)+0.75)"
_BOUNCE_3 = f"({_N1}*pow(({{p}})-{2.25 / _D1}\\,2)+0.9375)"
_BOUNCE_4 = f"({_N1}*pow(({{p}})-{2.625 / _D1}\\,2)+0.984375)"
_OUT_BOUNCE = (
    f"if(lt({{p}}\\,{1 / _D1})\\,{_N1}*pow({{p}}\\,2)\\,"
    f"if(lt({{p}}\\,{2 / _D1})\\,{_BOUNCE_2}\\,"
    f"if(lt({{p}}\\,{2.5 / _D1})\\,{_BOUNCE_3}\\,{_BOUNCE_4})))"
)

# nome → (função Python, expressão ffmpeg com `{p}`)
#
# As vírgulas das expressões já vêm ESCAPADAS (`\,`): elas vivem dentro de
# `'...'` num filtro, onde vírgula crua encerraria o filtro. Ver
# `compile_ffmpeg.esc`.
EASINGS: dict = {
    "linear": (lambda p: p, "({p})"),

    "in_sine":     (lambda p: 1 - math.cos(p * math.pi / 2), "(1-cos(({p})*PI/2))"),
    "out_sine":    (lambda p: math.sin(p * math.pi / 2), "sin(({p})*PI/2)"),
    "in_out_sine": (lambda p: -(math.cos(math.pi * p) - 1) / 2, "(-(cos(PI*({p}))-1)/2)"),

    "in_quad":  (lambda p: p * p, "pow({p}\\,2)"),
    "out_quad": (lambda p: 1 - (1 - p) ** 2, "(1-pow(1-({p})\\,2))"),
    "in_out_quad": (
        lambda p: 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2,
        "if(lt({p}\\,0.5)\\,2*pow({p}\\,2)\\,1-pow(-2*({p})+2\\,2)/2)",
    ),

    "in_cubic":  (lambda p: p ** 3, "pow({p}\\,3)"),
    "out_cubic": (lambda p: 1 - (1 - p) ** 3, "(1-pow(1-({p})\\,3))"),
    "in_out_cubic": (
        lambda p: 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2,
        "if(lt({p}\\,0.5)\\,4*pow({p}\\,3)\\,1-pow(-2*({p})+2\\,3)/2)",
    ),

    "in_quart":  (lambda p: p ** 4, "pow({p}\\,4)"),
    "out_quart": (lambda p: 1 - (1 - p) ** 4, "(1-pow(1-({p})\\,4))"),
    "in_out_quart": (
        lambda p: 8 * p ** 4 if p < 0.5 else 1 - (-2 * p + 2) ** 4 / 2,
        "if(lt({p}\\,0.5)\\,8*pow({p}\\,4)\\,1-pow(-2*({p})+2\\,4)/2)",
    ),

    "in_expo": (
        lambda p: 0.0 if p <= 0 else 2 ** (10 * p - 10),
        "if(lte({p}\\,0)\\,0\\,pow(2\\,10*({p})-10))",
    ),
    "out_expo": (
        lambda p: 1.0 if p >= 1 else 1 - 2 ** (-10 * p),
        "if(gte({p}\\,1)\\,1\\,1-pow(2\\,-10*({p})))",
    ),
    "in_out_expo": (
        lambda p: 0.0 if p <= 0 else (1.0 if p >= 1 else (
            2 ** (20 * p - 10) / 2 if p < 0.5 else (2 - 2 ** (-20 * p + 10)) / 2)),
        "if(lte({p}\\,0)\\,0\\,if(gte({p}\\,1)\\,1\\,"
        "if(lt({p}\\,0.5)\\,pow(2\\,20*({p})-10)/2\\,(2-pow(2\\,-20*({p})+10))/2)))",
    ),

    "in_back": (
        lambda p: _C3 * p ** 3 - _C1 * p ** 2,
        f"({_C3}*pow({{p}}\\,3)-{_C1}*pow({{p}}\\,2))",
    ),
    "out_back": (
        lambda p: 1 + _C3 * (p - 1) ** 3 + _C1 * (p - 1) ** 2,
        f"(1+{_C3}*pow(({{p}})-1\\,3)+{_C1}*pow(({{p}})-1\\,2))",
    ),
    "in_out_back": (
        _in_out_back_py,
        f"if(lt({{p}}\\,0.5)\\,pow(2*({{p}})\\,2)*(({_C2}+1)*2*({{p}})-{_C2})/2\\,"
        f"(pow(2*({{p}})-2\\,2)*(({_C2}+1)*(2*({{p}})-2)+{_C2})+2)/2)",
    ),

    "out_elastic": (
        _out_elastic_py,
        f"if(lte({{p}}\\,0)\\,0\\,if(gte({{p}}\\,1)\\,1\\,"
        f"pow(2\\,-10*({{p}}))*sin((({{p}})*10-0.75)*{_C4})+1))",
    ),
    "out_bounce": (_out_bounce_py, _OUT_BOUNCE),
}

NAMES = tuple(EASINGS.keys())


def py(name: str):
    """Função Python da curva. Levanta KeyError se o nome não existir — quem
    valida é o `schema.py`, que roda antes."""
    return EASINGS[name][0]


def expr(name: str, p_expr: str) -> str:
    """Expressão ffmpeg da curva, com `{p}` trocado por `p_expr`.

    `p_expr` deve vir pronto e já clampado em [0,1] por quem chama
    (`compile_ffmpeg.track_expr` usa `clip(...)`): as curvas não reclampam, do
    mesmo jeito que as funções Python.
    """
    return EASINGS[name][1].replace("{p}", p_expr)


def apply(name: str, p: float) -> float:
    """Avalia a curva em Python, com o progresso clampado em [0,1]."""
    p = 0.0 if p < 0.0 else (1.0 if p > 1.0 else p)
    return float(EASINGS[name][0](p))
