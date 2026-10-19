"""Keyframes, tracks e a timeline resolvida.

Aqui mora toda a conversão de unidades e a semântica de interpolação. O resto do
pacote só manipula `Track`/`Timeline`, que já estão em segundos absolutos da
cena e em px / multiplicador / 0–1 — nenhum backend reinterpreta string de JSON.
"""

import difflib
from bisect import bisect_right
from dataclasses import dataclass, field

from libs.Motion import easing
from libs.Motion.errors import ValidationError

# Folga usada para ancorar o keyframe de retenção logo antes do início da ação
# seguinte (ver `Track.add`). Menor que um frame a 1000 fps.
_HOLD_EPS = 1e-4


def _ease_hint(name) -> str:
    """Sugestão com os easings mais parecidos (princípio P3)."""
    close = difflib.get_close_matches(str(name), easing.NAMES, n=5, cutoff=0.3)
    return "talvez: " + ", ".join(close) if close else \
        "válidos: " + ", ".join(easing.NAMES)

# Valor de repouso de cada propriedade animável. Serve de base para os deltas
# (x/y são deslocamentos sobre a caixa do layout) e para `is_static`.
BASES = {
    "x": 0.0, "y": 0.0, "rotation": 0.0, "blur": 0.0,
    "scale": 1.0, "zoom": 1.0, "opacity": 1.0,
}

PROPS = tuple(BASES.keys())

# Propriedades cujo valor é adimensional (multiplicador, 0–1 ou sigma): `%`
# nelas é apenas /100, e não fração da caixa.
_SCALAR_PROPS = {"scale", "zoom", "opacity", "blur"}


@dataclass(frozen=True)
class Keyframe:
    t: float        # segundos absolutos na cena
    value: float    # px / multiplicador / 0–1, já convertido
    ease: str       # easing do trecho que COMEÇA aqui


@dataclass
class Track:
    prop: str
    keys: list = field(default_factory=list)   # list[Keyframe], ordenado por t
    base: float = 0.0
    # Repetição de uma ação `"loop": true`: (período, t_inicial, t_final). O
    # bloco de keyframes é reaproveitado por `mod()` em vez de ser copiado N
    # vezes — copiar estouraria o teto de keyframes e jogaria a cena no MoviePy.
    loop: tuple = None

    # -- consulta ----------------------------------------------------------

    def is_constant(self) -> bool:
        """True se o valor nunca muda (mas pode ser diferente da base).

        Permite compilar a track como uma CONSTANTE em vez de uma árvore de
        `if` — ex.: um `opacity` fixo em 0,4 declarado via motion.
        """
        if not self.keys:
            return True
        first = self.keys[0].value
        return all(abs(k.value - first) < 1e-9 for k in self.keys)

    def is_static(self) -> bool:
        """True se a track não muda NADA (constante e igual à base).

        Permite desligar o filtro/callable correspondente e não pagar o custo.
        """
        return all(abs(k.value - self.base) < 1e-9 for k in self.keys)

    def sample(self, t: float) -> float:
        """Valor em `t`. Antes do 1º keyframe segura o 1º; depois do último,
        segura o último (o `hold: false` já materializou o retorno à base como
        keyframe explícito)."""
        if not self.keys:
            return self.base
        t = self.loop_time(t)
        if t <= self.keys[0].t:
            return self.keys[0].value
        if t >= self.keys[-1].t:
            return self.keys[-1].value

        i = bisect_right([k.t for k in self.keys], t) - 1
        a, b = self.keys[i], self.keys[i + 1]
        span = b.t - a.t
        if span <= 0:
            return b.value
        p = (t - a.t) / span
        return a.value + (b.value - a.value) * easing.apply(a.ease, p)

    def loop_time(self, t: float) -> float:
        """Dobra `t` de volta para dentro do bloco, quando a track é em loop."""
        if not self.loop:
            return t
        period, start, until = self.loop
        if period <= 0 or t < start:
            return t
        if until is not None and t > until:
            return until
        return start + ((t - start) % period)

    def bounds(self) -> tuple:
        """(mínimo, máximo) dos valores — usado para decidir se cabe no filtro
        barato (ex.: `fade` só vale para opacidade entre 0 e 1)."""
        if not self.keys:
            return (self.base, self.base)
        values = [k.value for k in self.keys]
        return (min(values), max(values))

    def window(self) -> tuple:
        """(t_inicial, t_final) cobertos pelos keyframes."""
        if not self.keys:
            return (0.0, 0.0)
        return (self.keys[0].t, self.keys[-1].t)

    # -- construção --------------------------------------------------------

    def add(self, keys: list, *, hold: bool = True, base_snap_at: float = None):
        """Mescla keyframes de uma ação nova por cima do que já existe.

        Entre o fim de uma ação e o início da próxima o valor é SEGURADO: insere
        um keyframe implícito no instante de início da nova ação com o valor
        retido. Sem isso, o ffmpeg e o MoviePy interpolariam do último valor
        antigo até o primeiro novo ao longo de todo o intervalo morto — um
        movimento fantasma que ninguém declarou.
        """
        if not keys:
            return
        new_start = keys[0].t

        # Ações posteriores escrevem por cima do mesmo intervalo.
        kept = [k for k in self.keys if k.t < new_start - _HOLD_EPS]
        if kept and abs(kept[-1].value - keys[0].value) > 1e-9:
            # O keyframe de retenção fica uma fração de ms ANTES do início da
            # nova ação: no mesmo instante ele seria deduplicado, e sem ele a
            # interpolação cobriria todo o intervalo morto entre as duas ações.
            kept.append(Keyframe(new_start - _HOLD_EPS, kept[-1].value, "linear"))

        self.keys = kept + list(keys)

        if not hold and base_snap_at is not None:
            self.keys.append(Keyframe(base_snap_at, self.base, "linear"))

        self.keys.sort(key=lambda k: k.t)
        self._dedupe()

    def _dedupe(self):
        """Remove keyframes com o mesmo `t` (o último declarado vence)."""
        out = []
        for k in self.keys:
            if out and abs(out[-1].t - k.t) < 1e-9:
                out[-1] = k
            else:
                out.append(k)
        self.keys = out

    def clamp(self, t0: float, t1: float):
        """Prende os keyframes na janela da cena, preservando os valores nas
        bordas (reamostra em t0/t1 em vez de simplesmente descartar)."""
        if not self.keys:
            return
        inside = [k for k in self.keys if t0 <= k.t <= t1]
        head = None if (not self.keys or self.keys[0].t >= t0) else \
            Keyframe(t0, self.sample(t0), self.keys[0].ease)
        tail = None if (not self.keys or self.keys[-1].t <= t1) else \
            Keyframe(t1, self.sample(t1), "linear")
        keys = ([head] if head else []) + inside + ([tail] if tail else [])
        self.keys = keys
        self._dedupe()


@dataclass
class Timeline:
    tracks: dict = field(default_factory=dict)    # prop → Track
    visible: tuple = None                         # (inicio, fim) de `enable`
    duration: float = 0.0
    actions: list = field(default_factory=list)   # p/ debug/inspect
    warnings: list = field(default_factory=list)

    def get(self, prop: str):
        return self.tracks.get(prop)

    def sample(self, prop: str, t: float) -> float:
        track = self.tracks.get(prop)
        return track.sample(t) if track else BASES.get(prop, 0.0)

    def active(self) -> dict:
        """Só as tracks que realmente movem algo."""
        return {p: tr for p, tr in self.tracks.items() if not tr.is_static()}

    def is_empty(self) -> bool:
        return not self.active() and self.visible is None


# ---------------------------------------------------------------------------
# PARSING
# ---------------------------------------------------------------------------

def resolve_value(prop: str, raw, *, box: tuple, resolution: tuple,
                  path: str = "") -> float:
    """Converte um valor de JSON para a unidade interna da propriedade.

    - `x`: `"%"` = fração da LARGURA DA CAIXA, `"vw"`/`"vh"` = fração da tela
    - `y`: `"%"` = fração da ALTURA DA CAIXA, idem para viewport
    - `scale`/`zoom`/`opacity`: número puro; `"%"` é só /100
    - número puro em `x`/`y`/`rotation`: px (ou graus)
    """
    _, _, box_w, box_h = (box or (0, 0, 0, 0))
    res_w, res_h = (resolution or (0, 0))

    if isinstance(raw, bool):
        raise ValidationError(f"valor booleano inválido para '{prop}'", path)
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        raise ValidationError(f"valor inválido para '{prop}': {raw!r}", path)

    text = raw.strip().lower()
    try:
        if text.endswith("%"):
            frac = float(text[:-1]) / 100.0
            if prop in _SCALAR_PROPS:
                return frac
            ref = box_w if prop == "x" else (box_h if prop == "y" else 1.0)
            return frac * float(ref)
        if text.endswith("vw"):
            return float(text[:-2]) / 100.0 * float(res_w)
        if text.endswith("vh"):
            return float(text[:-2]) / 100.0 * float(res_h)
        if text.endswith("px"):
            return float(text[:-2])
        return float(text)
    except ValueError:
        raise ValidationError(f"valor não numérico para '{prop}': {raw!r}", path,
                              hint="use número, \"12px\", \"30%\", \"5vw\" ou \"5vh\"")


def resolve_time(raw, *, duration: float, path: str = "") -> float:
    """Tempo RELATIVO dentro de uma ação → segundos.

    `0..1` = fração da duração da ação; `"0.2s"` = segundos; `"40%"` = fração.
    Número > 1 também é lido como segundos (um `duration` de 2 s com keyframe em
    `1.4` só pode querer dizer 1,4 s).
    """
    if isinstance(raw, bool):
        raise ValidationError(f"tempo booleano inválido: {raw!r}", path)
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value * duration if 0.0 <= value <= 1.0 else value
    if isinstance(raw, str):
        text = raw.strip().lower()
        try:
            if text.endswith("%"):
                return float(text[:-1]) / 100.0 * duration
            if text.endswith("s"):
                return float(text[:-1])
            value = float(text)
            return value * duration if 0.0 <= value <= 1.0 else value
        except ValueError:
            pass
    raise ValidationError(f"tempo inválido: {raw!r}", path,
                          hint="use 0..1 (fração da duração), \"40%\" ou \"0.2s\"")


def parse_track(prop: str, raw, *, duration: float, action_start: float,
                box: tuple, resolution: tuple, default_ease: str,
                path: str = "") -> list:
    """Uma das 4 formas da §2.4 do plano → `list[Keyframe]` em tempo ABSOLUTO.

        [de, para]                      dois valores na duração da ação
        [v0, v1, v2, …]                 N valores igualmente espaçados
        [[t, v], …]                     keyframes explícitos
        [[t, v, ease], …]               keyframe com easing próprio
        v                               valor constante durante a ação
    """
    def kf(t_rel: float, value, ease: str) -> Keyframe:
        return Keyframe(
            action_start + t_rel,
            resolve_value(prop, value, box=box, resolution=resolution, path=path),
            ease,
        )

    if raw is None:
        raise ValidationError(f"track '{prop}' vazia", path)

    # Valor único: constante na janela da ação (útil com `visible`/`hold`).
    if not isinstance(raw, (list, tuple)):
        return [kf(0.0, raw, default_ease), kf(duration, raw, default_ease)]

    if len(raw) == 0:
        raise ValidationError(f"track '{prop}' vazia", path)

    explicit = all(isinstance(item, (list, tuple)) for item in raw)

    if explicit:
        keys = []
        for i, item in enumerate(raw):
            item_path = f"{path}[{i}]"
            if len(item) not in (2, 3):
                raise ValidationError(
                    f"keyframe de '{prop}' precisa de [t, valor] ou [t, valor, ease]",
                    item_path)
            t_rel = resolve_time(item[0], duration=duration, path=item_path)
            ease = default_ease if len(item) == 2 else str(item[2])
            if ease not in easing.EASINGS:
                raise ValidationError(f"easing desconhecido: {ease!r}", item_path,
                                      hint=_ease_hint(ease))
            keys.append(kf(t_rel, item[1], ease))
        keys.sort(key=lambda k: k.t)
        return keys

    if any(isinstance(item, (list, tuple)) for item in raw):
        raise ValidationError(
            f"track '{prop}' mistura valores soltos com keyframes", path,
            hint="use [de, para] OU [[t, valor], …], não os dois")

    if len(raw) == 1:
        return [kf(0.0, raw[0], default_ease), kf(duration, raw[0], default_ease)]

    step = duration / (len(raw) - 1)
    return [kf(i * step, value, default_ease) for i, value in enumerate(raw)]
