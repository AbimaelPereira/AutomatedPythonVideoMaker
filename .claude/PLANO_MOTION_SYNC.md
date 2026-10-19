# Plano de implementação — Motion Engine + sincronia com narração

Repositório: `AbimaelPereira/AutomatedPythonVideoMaker`
Módulo alvo: `videomaker/`
Branch sugerida: `feat/motion-engine`
Destino deste arquivo: `videomaker/docs/PLANO_MOTION_SYNC.md`

> **Para o agente executor:** este plano é normativo. Cada fase tem *arquivos*,
> *assinaturas*, *critério de aceite* e *comando de verificação*. Não pule a
> Fase 0 — o projeto não tem testes automatizados e todo o resto depende da rede
> de segurança criada nela. Não refatore o que está fora do escopo listado.
> Commits: um por fase, mensagem `motion: fase N — <título>`.

---

## 0. Diagnóstico — o que existe hoje

### 0.1 Animação

Todo o vocabulário de animação do projeto são **5 tipos**, declarados em
`visual_elements[].animation.type`:

| tipo | o que faz | onde |
|---|---|---|
| `fade_in` | `crossfadein(duration)` | `VisualClip._apply_animation` ([VisualClip.py:721](../libs/VisualClip.py#L721)) |
| `zoom_in` / `zoom_out` | `resize(lambda t: lerp)` linear | `VisualClip._make_zoom_clip` ([:674](../libs/VisualClip.py#L674)) |
| `zoom_pulse` | `1 + i*sin(pi*t/T)` | idem |
| `fade_zoom_in` | zoom + `crossfadein` | idem |

Limitações estruturais:

1. **Só escala e opacidade.** Não existe translação (slide), rotação animada
   (`layout.rotation` é estático), recorte animado, blur, cor.
2. **Sempre linear.** Nenhum easing. `zoom_pulse` é a única curva não-linear e é
   fixa.
3. **Sempre do início ao fim da cena.** `total = clip.duration`; `start_at`
   apenas atrasa o clipe inteiro. Não há como animar de 2,1 s a 2,7 s.
4. **Uma animação por elemento.** O campo é um dict único, não uma lista. Não dá
   para "entra, segura, pulsa, sai".
5. **Sem keyframes.** Só `start_scale` → `end_scale`.

### 0.2 Sincronia com a fala

Os tempos palavra-a-palavra **já existem** e são de boa qualidade:

- `NarrationEngine.process_scene_narration` ([NarrationEngine.py:111](../libs/Audio/NarrationEngine.py#L111))
  devolve `(audio_clip, duration, subtitle_path)`.
- `word_boundaries` vêm do provider (`edge`, `polly`) ou do Whisper
  (`google`, `kokoro`), passam por `_apply_silence_removal` (que **remapeia** os
  tempos após o corte de silêncio) e são gravados em
  `{scene_dir}/{scene_id}.srt`, uma palavra por entrada
  (`_write_srt`, [:359](../libs/Audio/NarrationEngine.py#L359)).
- `SubtitleUtils.parse_srt_words(path, uppercase=False)`
  ([SubtitleUtils.py:475](../libs/Subtitle/SubtitleUtils.py#L475)) já lê esse SRT
  para `[{word, start, end}]`, com pontuação removida.

**Quem consome isso hoje: apenas a legenda.** `KaraokeSubtitle` e o
`AssBuilder`. Os `visual_elements` nunca veem o SRT — o worker tem a variável
`subtitle_file` em mãos ([UnifiedVideoEngine.py:527](../libs/UnifiedVideoEngine.py#L527))
e só a repassa para `_create_subtitle_clip_worker` e para `_try_ffmpeg_scene`
**quando a legenda está ligada**.

> É exatamente essa a lacuna: o dado de sincronia existe, está correto, e não
> chega na camada de animação.

### 0.3 Os dois backends de render

| | caminho rápido | caminho legado |
|---|---|---|
| módulo | `libs/Render/FFmpegSceneRenderer.py` | `libs/UnifiedVideoEngine._process_scene_worker` |
| composição | um `filter_complex` | MoviePy frame a frame |
| gate | `FFmpegSceneRenderer.can_handle()` | fallback de tudo que o gate recusa |
| custo medido | **2,0 s** (cena 5 s, 1080p) | **47,6 s** |

Ponto de entrada único: `_try_ffmpeg_scene`
([UnifiedVideoEngine.py:319](../libs/UnifiedVideoEngine.py#L319)), controlado por
`RENDER_BACKEND=auto|ffmpeg|moviepy`.

**Consequência de projeto:** toda animação nova precisa de implementação nos
**dois** backends, ou precisa ser declarada em `_SUPPORTED_ANIMATIONS` como não
suportada (e aí a cena cai no MoviePy — 23x mais lenta). Animar é justamente o
caso em que a lentidão do MoviePy explode. **Prioridade absoluta ao backend
ffmpeg.**

### 0.4 Onde a animação é aplicada (ordem exata, não mexer)

Modo cover (`placement.width` **e** `height`):

```
resize(_resize_to) → crop(focus) → animation (janela fixa) → border_radius → filters → opacity → position
```

- MoviePy: `_create_visual_elements_clip_worker` ([:764-795](../libs/UnifiedVideoEngine.py#L764))
- ffmpeg: `FFmpegSceneRenderer.render`, laço de elementos ([:290-337](../libs/Render/FFmpegSceneRenderer.py#L290))
- A decisão de adiar vem de `LayoutEngine.process_stack_layout` →
  `deferred_animation` ([LayoutEngine.py:303](../libs/LayoutEngine.py#L303)).

---

## 1. Objetivo e princípios

**Objetivo:** permitir que um JSON gerado por IA descreva movimento rico e
ancorado na fala, sem perder o caminho rápido de render.

**Princípios inegociáveis:**

| # | princípio | consequência prática |
|---|---|---|
| P1 | **Retrocompatibilidade total** | nenhum JSON existente muda um pixel. Verificado por SSIM na Fase 0. |
| P2 | **ffmpeg-first** | toda propriedade animável nasce com expressão de filtro. MoviePy é paridade, não referência. |
| P3 | **Falhar cedo e alto** | JSON inválido aborta com erro apontando o caminho (`scenes[2].visual_elements[0].motion.actions[1].ease`). Nunca ignorar silenciosamente. |
| P4 | **Âncora que não quebra** | se a palavra não existir no SRT, política explícita de fallback + log. Render nunca morre por isso. |
| P5 | **Ergonomia para IA** | atalhos (`[de, para]`), presets nomeados, vocabulário fechado e enumerável. O schema é a documentação. |
| P6 | **Determinismo** | mesmo JSON + mesmo SRT = mesmos frames. Nenhum `random` sem seed. |

---

## 2. Superfície JSON nova

### 2.1 Chave: `motion`

Nova chave em `visual_elements[]`, irmã de `animation` (legado). Também aceita em
`background.visual` (Fase 7) e em `subtitle` (fora de escopo).

```jsonc
{
  "type": "image",
  "source": "./assets/image/x.png",
  "placement": { "anchor": ["right", "center"], "width": "45%" },

  "motion": {
    "on_missing": "proportional",
    "visible": { "from": { "word": "agora" }, "to": { "word": "porém" } },
    "actions": [
      {
        "name": "entrada",
        "at": { "word": "dinheiro", "offset": -0.12 },
        "duration": 0.55,
        "ease": "out_back",
        "preset": "slide_in_right"
      },
      {
        "at": { "after": "entrada", "offset": 0.2 },
        "duration": 0.3,
        "ease": "out_quad",
        "tracks": { "scale": [1.0, 1.08, 1.0] }
      },
      {
        "at": { "word": "porém", "align": "start" },
        "duration": 0.35,
        "preset": "fade_out"
      }
    ]
  }
}
```

Forma curta aceita: `"motion": [ {action}, ... ]` ≡ `{"actions": [...]}`.

### 2.2 Âncoras (`at`, `until`, `from`, `to`)

| forma | significado |
|---|---|
| `0.8` | segundos absolutos na cena |
| `"42%"` | fração da duração da cena |
| `"end"` / `"start"` | extremos da cena |
| `{"word": "lucro"}` | 1ª ocorrência da palavra no SRT da cena |
| `{"word": "lucro", "nth": 2}` | n-ésima ocorrência (1-based) |
| `{"word_index": 14}` | palavra nº 14 (1-based) |
| `{"phrase": "mais de um milhão"}` | sequência de palavras |
| `{"sentence": 2}` | 2ª frase do `narration.text` |
| `{"after": "<name>"}` | fim da ação chamada `<name>` no mesmo elemento |
| `{"at_end_of": "<name>"}` | alias de `after` |

Modificadores combináveis em qualquer forma de objeto:

- `"offset": -0.15` — segundos somados (pode ser negativo)
- `"align": "start" | "end" | "center"` — qual borda da palavra/frase usar (default `start`)

### 2.3 Propriedades animáveis (`tracks`)

| propriedade | unidade | base | ffmpeg | MoviePy |
|---|---|---|---|---|
| `x` | px, `"%"` (da largura da caixa), `"vw"` | delta sobre `box.x` | `overlay=x='…'` | `set_position(lambda t)` |
| `y` | px, `"%"` (da altura da caixa), `"vh"` | delta sobre `box.y` | `overlay=y='…'` | idem |
| `scale` | multiplicador | 1.0 | `scale=eval=frame` + compensação no overlay | `resize(lambda t)` |
| `opacity` | 0–1 | 1.0 | segmentos `fade` ou `geq` | máscara `fl` |
| `zoom` | multiplicador | 1.0 | `zoompan` (janela fixa, = comportamento legado) | `apply_animation_in_window` |
| `rotation` | graus | 0 | `rotate=a='…':c=none` (Fase 7) | `vfx.rotate(lambda t)` (Fase 7) |

> `scale` **transborda** a caixa (motion de UI: pop, punch).
> `zoom` **fica dentro** da caixa, recortando (ken burns). São propriedades
> distintas de propósito; nunca unifique.

### 2.4 Formas de um track

```jsonc
"tracks": {
  "opacity": [0, 1],                                  // [de, para] na duração da ação
  "scale":   [1.0, 1.08, 1.0],                        // N valores igualmente espaçados
  "y":       [["0%", 40], ["100%", 0]],               // [t_relativo, valor]
  "x":       [[0, "-30%", "out_cubic"], [1, 0]]       // [t_relativo, valor, ease próprio]
}
```

- `t_relativo`: `0..1` (fração da `duration` da ação) ou `"0.2s"` (segundos).
- Easing: `ease` da ação é o default; o 3º item do keyframe sobrescreve o trecho
  que **começa** nele.
- Antes do 1º keyframe: segura o 1º valor. Depois do último: segura o último
  (`"hold": false` na ação faz voltar à base).

### 2.5 Easings suportados

`linear`, `in_sine`, `out_sine`, `in_out_sine`, `in_quad`, `out_quad`,
`in_out_quad`, `in_cubic`, `out_cubic`, `in_out_cubic`, `in_quart`, `out_quart`,
`in_out_quart`, `in_expo`, `out_expo`, `in_out_expo`, `in_back`, `out_back`,
`in_out_back`, `out_elastic`, `out_bounce`.

Vocabulário **fechado**: qualquer outro nome é erro de validação (P3).

### 2.6 Presets

Preset = conjunto nomeado de tracks + ease + duração default. `tracks`
declarado na ação **sobrescreve** o do preset, propriedade a propriedade.

| preset | tracks |
|---|---|
| `fade_in` / `fade_out` | `opacity` |
| `slide_in_left/right/up/down` | `x` ou `y` (±`"60%"`) + `opacity` |
| `slide_out_left/right/up/down` | inverso |
| `pop_in` | `scale` `0.82→1` (`out_back`) + `opacity` |
| `pop_out` | `scale` `1→0.86` + `opacity` |
| `rise` | `y` `+40px→0` + `opacity` (`out_cubic`) |
| `punch` | `scale` `1→1.08→1` (`out_quad`) |
| `shake` | `x` senoide amortecida (6 keyframes) |
| `ken_burns_in` / `ken_burns_out` | `zoom` |
| `float` | `y` senoide lenta, `"loop": true` |

### 2.7 Nível de cena e global

```jsonc
"global_settings": {
  "motion": {
    "enabled": true,
    "on_missing": "proportional",   // strict | proportional | start | skip
    "default_ease": "out_cubic",
    "default_duration": 0.5,
    "fps_hint": 30
  }
}
```

Mescla pela cadeia canal < global < capítulo < cena, via `deep_merge` existente.

### 2.8 Política `on_missing`

Quando uma âncora de palavra/frase não é encontrada no SRT:

| valor | comportamento |
|---|---|
| `strict` | levanta `MotionError` e aborta o vídeo |
| `proportional` | **(default)** distribui as ações não resolvidas uniformemente na duração da cena, preservando a ordem declarada |
| `start` | ancora em `t=0` |
| `skip` | a ação é descartada (elemento fica na base) |

Sempre emite `[Motion] ⚠️ âncora não resolvida: ...` com as 5 palavras mais
próximas por similaridade, para diagnóstico.

---

## 3. Arquitetura — `libs/Motion/`

Pacote novo, sem dependência de MoviePy nem de ffmpeg (puro Python + stdlib +
`thefuzz`, já no `requirements.txt`). Isso o torna testável em milissegundos.

```
libs/Motion/
├── __init__.py          # API pública: resolve_motion(), MotionError
├── errors.py            # MotionError, AnchorNotFound (com .path JSON)
├── schema.py            # validação declarativa + mensagens
├── easing.py            # curvas: Python (float→float) e expressão ffmpeg
├── keyframes.py         # Track, Keyframe, normalização, amostragem, merge
├── presets.py           # tabela de presets → tracks
├── anchors.py           # SRT/texto → segundos
├── timeline.py          # actions → Timeline (tracks absolutos em seg.)
├── compile_ffmpeg.py    # Timeline → expressões de filtro
├── compile_moviepy.py   # Timeline → callables
└── inspect.py           # impressão da timeline resolvida (debug/CLI)
```

### 3.1 Modelo de dados

```python
# keyframes.py
@dataclass(frozen=True)
class Keyframe:
    t: float          # segundos absolutos na cena
    value: float      # já convertido para px / multiplicador / 0-1
    ease: str         # easing do trecho que COMEÇA aqui

@dataclass
class Track:
    prop: str                 # "x" | "y" | "scale" | "opacity" | "zoom" | "rotation"
    keys: list[Keyframe]      # ordenado por t, sem duplicatas
    base: float               # valor de repouso (0 para x/y/rotation, 1 para scale/zoom/opacity)

    def is_static(self) -> bool: ...
    def sample(self, t: float) -> float: ...
    def bounds(self) -> tuple[float, float]: ...

@dataclass
class Timeline:
    tracks: dict[str, Track]
    visible: tuple[float, float] | None   # janela de `enable`
    duration: float
```

### 3.2 API pública

```python
# libs/Motion/__init__.py
def resolve_motion(
    *,
    element: dict,            # o visual_element cru do JSON
    box: tuple,               # (x, y, w, h) já resolvido pelo LayoutEngine
    resolution: tuple,        # (W, H) da saída
    scene_duration: float,
    words: list | None,       # [{word, start, end}] do SRT, ou None
    narration_text: str = "",
    defaults: dict | None = None,   # global_settings.motion efetivo
    json_path: str = "",            # p/ mensagens de erro
) -> Timeline | None:
    """None = elemento sem motion novo (segue o caminho legado)."""
```

Essa é a **única** função que os dois backends chamam. Toda a complexidade fica
atrás dela.

---

## 4. Fases

### Fase 0 — Rede de segurança (bloqueante)

**Por que primeiro:** o projeto não tem testes. Sem baseline, o P1 é
inverificável.

**Arquivos novos:**

```
videomaker/tests/
├── fixtures/make_fixtures.py     # gera assets sintéticos determinísticos
├── golden/*.json                 # 6 JSONs que cobrem os caminhos atuais
├── golden_render.py              # renderiza e grava hashes/amostras
└── compare_ssim.py               # compara dois diretórios de saída
```

1. `make_fixtures.py` gera, com seed fixa, em `tests/fixtures/assets/`:
   - 3 PNGs sólidos 1920×1080, 1080×1920, 800×800
   - 1 PNG com alpha (círculo)
   - 2 MP4s de 4 s (`ffmpeg -f lavfi -i testsrc2`, `-i smptebars`)
   - pasta `b_roll/` com 4 MP4s de 2 s para `type: "directory"`
2. Os 6 golden JSONs cobrem: fundo cor; fundo imagem cover+focus; fundo
   directory; `visual_elements` com `zoom_in`, `fade_in`, `fade_zoom_in`,
   `zoom_pulse`; `placement` cover com `border_radius`; legenda classic;
   legenda karaokê; transição fade. **Sem narração TTS** (`duration` fixa +
   `narration` ausente) para serem offline e determinísticos.
3. `golden_render.py --save baseline/` renderiza com `RENDER_BACKEND=ffmpeg` e
   com `moviepy`, guardando os MP4s.
4. `compare_ssim.py a/ b/` roda, por par:
   `ffmpeg -i a.mp4 -i b.mp4 -lavfi "[0:v][1:v]ssim=stats_file=-" -f null -`
   e falha se `All < 0.995`.

**Aceite:** `python tests/golden_render.py --save baseline/` roda limpo, e
`python tests/compare_ssim.py baseline/ baseline/` passa (sanidade do
comparador).

**Comando:**
```bash
cd videomaker && python tests/fixtures/make_fixtures.py && \
  RENDER_BACKEND=ffmpeg python tests/golden_render.py --save tests/baseline/
```

---

### Fase 1 — Núcleo do Motion (sem render)

**Arquivos:** `libs/Motion/{__init__,errors,easing,keyframes,presets,schema,timeline}.py`

#### 1.1 `easing.py`

```python
EASINGS: dict[str, tuple[Callable[[float], float], str]]
# nome → (função Python, expressão ffmpeg em função de `p`)

def py(name: str) -> Callable[[float], float]
def expr(name: str, p_expr: str) -> str   # substitui `p` pela sub-expressão real
```

Expressões ffmpeg (a variável de progresso chega como string; `{p}` é
substituído literalmente). O avaliador do ffmpeg só tem
`+ - * / ^ lt lte gt gte eq if ifnot between min max clip sin cos pow exp
log sqrt abs floor ceil mod PI E` — **sem funções do usuário**, logo toda curva é
inline:

| nome | expressão |
|---|---|
| `linear` | `{p}` |
| `in_quad` | `pow({p},2)` |
| `out_quad` | `(1-pow(1-({p}),2))` |
| `in_out_quad` | `if(lt({p},0.5),2*pow({p},2),1-pow(-2*({p})+2,2)/2)` |
| `in_cubic` | `pow({p},3)` |
| `out_cubic` | `(1-pow(1-({p}),3))` |
| `in_out_cubic` | `if(lt({p},0.5),4*pow({p},3),1-pow(-2*({p})+2,3)/2)` |
| `out_quart` | `(1-pow(1-({p}),4))` |
| `in_sine` | `(1-cos(({p})*PI/2))` |
| `out_sine` | `sin(({p})*PI/2)` |
| `in_out_sine` | `(-(cos(PI*({p}))-1)/2)` |
| `out_expo` | `if(gte({p},1),1,1-pow(2,-10*({p})))` |
| `out_back` | `(1+2.70158*pow(({p})-1,3)+1.70158*pow(({p})-1,2))` |
| `in_back` | `(2.70158*pow({p},3)-1.70158*pow({p},2))` |
| `out_elastic` | `if(lte({p},0),0,if(gte({p},1),1,pow(2,-10*({p}))*sin((({p})*10-0.75)*2*PI/3)+1))` |
| `out_bounce` | 4 ramos aninhados com `if(lt(...))` e constantes `7.5625`, `2.75` |

> **Teste obrigatório:** para cada easing, amostrar 101 pontos com a função
> Python e com o avaliador do ffmpeg
> (`ffmpeg -f lavfi -i "nullsrc=s=2x2:d=1" -vf "drawtext=..."` é frágil; use
> `ffprobe -f lavfi -i "aevalsrc=EXPR:d=1" -show_frames` ou, mais simples,
> `ffmpeg -f lavfi -i "color=s=2x2:d=1,geq=lum='EXPR*255'" -f rawvideo -` e leia
> o byte). Tolerância: `|py - ff| < 0.004` (1/255). **Isso é o que impede
> divergência entre os dois backends.**

#### 1.2 `keyframes.py`

- `parse_track(prop, raw, *, duration, action_start, box, resolution, default_ease)`
  → `list[Keyframe]`. Resolve as 4 formas da §2.4 e as unidades (`"%"`, `"vw"`,
  `"vh"`, `"px"`, número puro).
- `merge_tracks(existing: Track, new_keys)` — ações posteriores escrevem por
  cima; entre o fim de uma ação e o início da próxima, **segura** o último valor
  (insere keyframe implícito no instante do início da próxima, com o valor
  retido). Isso evita interpolação fantasma.
- `Track.sample(t)` — busca binária + easing.
- `Track.is_static()` — todos os valores iguais à base (permite desligar o
  filtro e não pagar custo).

#### 1.3 `presets.py`

Tabela literal `PRESETS: dict[str, dict]`, cada entrada
`{"duration": 0.5, "ease": "out_cubic", "tracks": {...}}`. Nada de código.

#### 1.4 `schema.py`

Validador manual (sem nova dependência), retornando
`list[ValidationError(path, message, hint)]`:

- chaves desconhecidas em `motion`, `action`, `at` → erro com sugestão por
  `difflib.get_close_matches`
- `ease` fora do vocabulário → lista os 5 mais próximos
- `preset` inexistente → idem
- `duration` ≤ 0, `opacity` fora de 0–1, `scale` ≤ 0
- `{"after": "x"}` apontando para `name` inexistente ou posterior → erro
- ciclo em `after` → erro
- `tracks` vazio e sem `preset` → erro

#### 1.5 `timeline.py`

```python
def build_timeline(motion_cfg, *, box, resolution, scene_duration,
                   anchor_resolver, defaults) -> Timeline
```
Ordem: validar → expandir presets → resolver âncoras (via callback, para a
Fase 2 plugar) → converter unidades → montar tracks → mesclar → clampar em
`[0, scene_duration]`.

**Aceite:** `pytest videomaker/tests/test_motion_core.py` com ≥ 40 casos,
cobrindo cada easing, cada forma de track, cada erro de schema, e a paridade
Python↔ffmpeg das curvas. Zero dependência de ffmpeg para render nesses testes
(só o avaliador de expressão).

---

### Fase 2 — Âncoras de narração

**Arquivos:** `libs/Motion/anchors.py`, `libs/Motion/inspect.py`
**Edições:** `libs/UnifiedVideoEngine.py`

#### 2.1 `anchors.py`

```python
class AnchorResolver:
    def __init__(self, words: list | None, narration_text: str,
                 scene_duration: float, on_missing: str = "proportional"): ...
    def resolve(self, spec, *, align="start", context="") -> float | None
    @property
    def misses(self) -> list[str]
```

Regras de casamento:

1. **Normalização**: `lower()` → NFD → remover diacríticos → remover pontuação →
   colapsar espaços. Aplicar aos dois lados.
2. **Palavra**: igualdade exata na lista normalizada. Se não achar, tentar
   `thefuzz.fuzz.ratio ≥ 88` (já é dependência). Se ainda não achar, miss.
3. **Frase**: janela deslizante do tamanho em palavras da frase; score por
   `fuzz.ratio` do join; aceita o melhor acima de 85. `start` = início da 1ª
   palavra, `end` = fim da última.
4. **Sentence**: tokenizar `narration_text` por `[.!?…;]`, depois alinhar os
   tokens escritos com os tokens do SRT por `difflib.SequenceMatcher`
   (o TTS/Whisper muda pontuação e números). Mapear a frase *n* para o intervalo
   de palavras do SRT.
5. **`align`**: `start` → `w.start`; `end` → `w.end`; `center` → média.
6. **`offset`** somado por último; resultado clampado em `[0, scene_duration]`.

Sem SRT (`words is None`, ex.: cena sem narração): qualquer âncora de
palavra/frase é miss → aplica `on_missing`.

`on_missing="proportional"`: as ações que falharam recebem
`t = scene_duration * (i+1)/(n+1)` na ordem declarada, ignorando as já
resolvidas.

#### 2.2 Encanamento do SRT (3 edições cirúrgicas)

`libs/UnifiedVideoEngine.py`:

1. **`_try_ffmpeg_scene`** ([:319](../libs/UnifiedVideoEngine.py#L319)) —
   o parâmetro `subtitle_file` hoje só é usado dentro do `if
   _subtitles_enabled(...)`. Extrair, **antes** desse `if`:
   ```python
   motion_words = None
   if subtitle_file and os.path.exists(subtitle_file):
       from libs.Subtitle.SubtitleUtils import parse_srt_words
       motion_words = parse_srt_words(subtitle_file, uppercase=False)
   ```
   e repassar `motion_words` para `SceneBridge.resolve_visual_boxes` e para
   `renderer.render(...)`.

2. **`_process_scene_worker`** ([:488](../libs/UnifiedVideoEngine.py#L488)) —
   o caminho MoviePy chama `_create_visual_elements_clip_worker(scene,
   scene_duration, scene_dir, resolution_output, remote_asset_manager,
   layout_params)` ([:596](../libs/UnifiedVideoEngine.py#L596)). Acrescentar os
   parâmetros `motion_words=` e `narration_text=` (texto de
   `scene["narration"]["text"]`), com default `None`/`""` para não quebrar o
   caminho sequencial.

3. **Caminho sequencial** (`_render_scene` e vizinhança, [:1148](../libs/UnifiedVideoEngine.py#L1148)) —
   mesma injeção. Há 3 locais que montam `subtitle_narration_file`
   (`:347`, `:837`, `:1148`); todos devem passar a expor `words`.

> **Armadilha:** `_apply_silence_removal` remapeia os tempos **antes** de
> `_write_srt`, então o SRT já está no timeline final do áudio. Não aplicar
> nenhuma correção extra. Mas atenção: se `scene["duration"]` for **maior** que
> a narração, o áudio é completado com `apad`
> ([FFmpegSceneRenderer.py:370](../libs/Render/FFmpegSceneRenderer.py#L370)) —
> os tempos do SRT continuam válidos. Se for **menor**, a cena é cortada e
> âncoras além do corte devem ser clampadas (já previsto).

#### 2.3 `inspect.py` + CLI

```
python -m libs.Motion.inspect jsons/x.json --video 0 --scene cena_02
```
Roda **só a narração** (TTS) e imprime:

```
cena_02  dur=7.42s  palavras=23
  t=0.00  0.55  elemento[0] "entrada"   slide_in_right   ease=out_back
          ↳ at={word:"dinheiro"} → 1.84s (palavra #6, "dinheiro", 1.84–2.21)
  ...
  ⚠️ elemento[2] ação[1]: palavra "bilhao" não encontrada
     próximas: "bilhoes"(92) "milhao"(83) ...  → aplicando on_missing=proportional → t=4.95
```

Adicionar também `MOTION_DEBUG=1` que imprime essa mesma tabela durante o render
normal. **Este é o loop de iteração rápida** — use-o antes de renderizar.

Edição em `main.py`: novo argumento `--timeline-only` que executa a resolução e
sai sem renderizar, e `--validate` que só roda o schema (sem TTS).

**Aceite:** `tests/test_anchors.py` com SRTs sintéticos cobrindo acento,
pontuação, repetição (`nth`), frase, sentence com divergência TTS↔texto, e as
4 políticas de `on_missing`.

---

### Fase 3 — Backend ffmpeg

**Arquivos:** `libs/Motion/compile_ffmpeg.py`
**Edições:** `libs/Render/FilterGraphBuilder.py`, `libs/Render/FFmpegSceneRenderer.py`, `libs/Render/SceneBridge.py`

#### 3.1 Regra de escape (crítica)

O `filter_complex` é passado como **um único argv**
([FFmpegSceneRenderer.py:372](../libs/Render/FFmpegSceneRenderer.py#L372)). A
convenção já comprovada no código é **aspas simples + vírgula escapada**:

```python
f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)'..."   # z contém  min(...\,1)
```

`compile_ffmpeg.py` **deve** expor:

```python
def esc(expr: str) -> str:
    """Escapa uma expressão para uso dentro de '...' num filtro."""
    return expr.replace("\\", "\\\\").replace(",", "\\,").replace(":", "\\:").replace("'", "\\'")
```

e gerar a expressão **sem** vírgulas não escapadas. Teste unitário dedicado:
compilar uma timeline com 5 keyframes e conferir que `expr.count(",") == 0` fora
dos `\,`.

#### 3.2 Compilador de track → expressão

```python
def track_expr(track: Track, *, t_var: str = "t") -> str
```

Produz if aninhado:

```
if(lt(T,t0), v0,
 if(lt(T,t1), v0+(v1-v0)*EASE(clip((T-t0)/(t1-t0)\,0\,1)),
  if(lt(T,t2), ..., vN)))
```

- Profundidade máxima: avisar/recusar acima de **24 keyframes** por track
  (expressões gigantes degradam o parser). Acima disso: `Unsupported` → MoviePy.
- `t_var`: `"t"` em `overlay`/`scale`; `"(on/{fps})"` em `zoompan` (que não expõe
  `t` — ver `_ZOOM_T`, [FilterGraphBuilder.py:60](../libs/Render/FilterGraphBuilder.py#L60)).
- Track estático → devolver a constante, não a árvore.

#### 3.3 Mapeamento por propriedade

**`x` / `y`** — `FilterGraphBuilder.overlay()` passa a aceitar `str`:

```python
def overlay(self, base, top, x, y, enable=None, eval_frame=False):
    xs = x if isinstance(x, str) else str(int(x))
    ys = y if isinstance(y, str) else str(int(y))
    ev = ":eval=frame" if eval_frame else ""
    self.add_chain(f"[{base}][{top}]overlay=x='{xs}':y='{ys}'{ev}{enable_expr}[{out}]")
```

Expressão final para x (com compensação de escala, ver abaixo):
`BASE_X + DX(t) + (BASE_W - overlay_w)/2`

**`scale`** — novo método:

```python
def scale_anim(self, src, w_expr: str, h_expr: str) -> str:
    out = self._label("sa")
    self.add_chain(
        f"[{src}]scale=w='trunc(({w_expr})/2)*2':h='trunc(({h_expr})/2)*2'"
        f":eval=frame:flags=bilinear,setsar=1[{out}]"
    )
    return out
```
com `w_expr = BASE_W * SCALE(t)`. Dimensões ímpares quebram `yuv420p` — o
`trunc(/2)*2` é obrigatório. `flags=bilinear` (não bicubic) porque roda a cada
frame.

A compensação de âncora vai no `overlay`, usando `overlay_w`/`overlay_h`
(avaliados por frame):
- âncora centro: `x = BASE_X + (BASE_W-overlay_w)/2`
- âncora esquerda: `x = BASE_X`
- âncora direita: `x = BASE_X + BASE_W - overlay_w`

A âncora vem de `placement.anchor` do elemento. Default: centro.

**`opacity`** — duas estratégias, nessa ordem:
1. Se o track for **monotônico por trecho entre 0 e 1 com easing linear**:
   emitir cadeia de `fade=t=in|out:st=:d=:alpha=1` (barato, já existe
   `fade_in()`). Cobre fade-in, fade-out e piscadas.
2. Caso contrário: `format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='({A})*alpha(X,Y)'`
   onde `{A}` é a expressão 0–1. **Medir** — `geq` em 1080p pode custar mais que
   o resto do filtergraph. Se passar de 1,5x o tempo da cena sem geq, logar
   aviso e considerar reduzir o elemento antes do geq.

**`zoom`** — reusar `_zoom_expr`, trocando a expressão fixa pela compilada com
`t_var=self._ZOOM_T`. Manter `max(...,1.0)` e o `_ZOOM_SS=2`.

**`visible`** — `enable='between(t\,A\,B)'` no `overlay` (já suportado).

#### 3.4 Gate `can_handle`

Em `FFmpegSceneRenderer.can_handle`, para cada elemento com `motion`:

```python
ok, why = MotionFFmpegSupport.check(el)   # novo helper
```
Recusar (→ MoviePy) quando: `rotation` presente (até a Fase 7); mais de 24
keyframes num track; `type` do elemento fora de `_SUPPORTED_VISUAL_TYPES`.
**Aceitar** o resto. Manter a regra de ouro do módulo: *na dúvida, recusar*.

Importante: `_SUPPORTED_ANIMATIONS` continua governando a chave legada
`animation`. `motion` é um caminho paralelo. Um elemento que declare **as duas**
é erro de schema.

#### 3.5 Ordem no `render()`

Inserir no laço de elementos ([:290](../libs/Render/FFmpegSceneRenderer.py#L290)),
**preservando** a ordem existente:

```
resize/crop → [zoom legado OU zoom-track] → scale_anim → border_radius
            → opacity(static) → fade/geq(opacity-track) → overlay(x,y,enable)
```

`scale_anim` depois do `border_radius` deformaria a máscara; antes, a máscara é
aplicada no tamanho da caixa e escala junto — **é o comportamento desejado**.
Portanto: `scale_anim` **depois** do `rounded_mask`. Confirmar visualmente no
teste 4.

**Aceite:**
- `RENDER_BACKEND=ffmpeg python main.py tests/motion/teste_01.json` conclui.
- `tests/compare_ssim.py` contra o baseline da Fase 0 continua ≥ 0.995 (nenhum
  JSON legado mudou).
- Novo golden: render de `teste_01` (determinístico, sem TTS) vira baseline.

---

### Fase 4 — Backend MoviePy (paridade)

**Arquivo:** `libs/Motion/compile_moviepy.py`
**Edições:** `libs/VisualClip.py`, `libs/UnifiedVideoEngine._create_visual_elements_clip_worker`

```python
def apply_timeline(clip, timeline: Timeline, *, box, anchor="center"):
    # ordem idêntica à do ffmpeg
```

- `scale`: `clip.resize(lambda t: timeline.sample("scale", t))`
- `x/y`: `clip.set_position(lambda t: (bx + dx(t) + comp_x(t), by + dy(t) + comp_y(t)))`
- `opacity`: `clip = clip.add_mask()` e
  `clip.mask = clip.mask.fl(lambda gf, t: gf(t) * a(t))`
  — **não** usar `set_opacity`, que é estático.
- `zoom`: reusar `apply_animation_in_window`, passando um callable.
- `visible`: `clip.set_start(A).set_end(B)`.

**Armadilha conhecida (já documentada no código):** clips com máscara alpha não
podem receber `force_rgb` antes do blend, e `_wrap_visual_layer`
([:690](../libs/UnifiedVideoEngine.py#L690)) decide achatar ou não o composite
com base em `animation.type in ('fade_in','fade_zoom_in')`. **Atualizar essa
função** para também considerar "tem track de `opacity` não-estático" como
translúcido. Sem isso, o fade novo vai renderizar sobre preto.

**Aceite:** `tests/test_parity.py` renderiza `teste_01.json` nos dois backends e
exige SSIM ≥ **0.98** (tolerância maior que 0.995 porque reamostragem difere).

---

### Fase 5 — Presets, stagger e ergonomia

1. Implementar todos os presets da §2.6 em `presets.py`.
2. **Stagger**: `motion.stagger` no nível da **cena**:
   ```jsonc
   "motion": { "stagger": 0.08, "stagger_group": "cards" }
   ```
   e `"stagger_group": "cards"` nos elementos. Todas as ações dos elementos do
   grupo recebem `+ i*stagger` no `at`. Implementar em `timeline.py`, após a
   resolução de âncoras.
3. **`"loop": true`** numa ação: repete o bloco de keyframes até o fim da
   cena/`visible`. Em ffmpeg, compilar com `mod(t-t0, periodo)` em vez do if
   aninhado — caminho de código separado e mais barato.
4. `text_box` no caminho rápido: `VisualClip._create_text_box_clip` já grava um
   PNG temporário. Extrair para `SceneBridge.render_text_box_png(el, scene_dir)`
   e adicionar `"text_box"` a `_SUPPORTED_VISUAL_TYPES`. **Ganho grande**: texto
   é o elemento mais animado e hoje derruba a cena inteira para o MoviePy.

**Aceite:** `teste_03.json` renderiza pelo caminho ffmpeg (verificar que o log
**não** contém "usando MoviePy").

---

### Fase 6 — Documentação da skill (obrigatória)

A IA que gera o JSON lê `videomaker/.claude/skills/pyvideomaker/`. Sem isso, a
feature não existe na prática.

1. **Novo**: `reference/motion.md` — a §2 inteira deste plano, com 12 exemplos
   copiáveis e uma tabela "quero X → use Y".
2. **Novo**: `reference/sync_narracao.md` — como ancorar, como escolher palavras
   âncora (palavras raras e longas casam melhor), `on_missing`, e o loop
   `--timeline-only`.
3. **Editar** `SKILL.md`: incluir `motion.md` e `sync_narracao.md` na ordem de
   leitura; marcar `animation` como legado (manter documentado).
4. **Editar** `reference/visual_elements.md`: seção `## animation` ganha nota
   apontando para `motion.md`.
5. **Novos exemplos**: copiar os 4 JSONs de teste para
   `.claude/skills/pyvideomaker/examples/`.
6. **Editar** `videomaker/.claude/CLAUDE.md`: parágrafo sobre `libs/Motion/` no
   diagrama de arquitetura.

---

### Fase 7 — Extensões

- `rotation` nos dois backends (`rotate=a='…':c=none:ow=hypot(iw\,ih):oh=ow` +
  recálculo do overlay para compensar o canvas maior).
- `motion` em `background.visual` (ken burns com keyframes, pan direcional).
- `blur` animado (`gblur=sigma='EXPR':eval=frame`).
- Sincronia com **batida** da música: detecção de onsets no
  `background.audio` (via `librosa` ou análise de energia com `numpy`), expondo
  `{"beat": 8}` como âncora.
- `motion` em `subtitle` (entrada por palavra já existe no karaokê; faltaria
  movimento).

---

## 5. Riscos e mitigações

| risco | impacto | mitigação |
|---|---|---|
| Divergência numérica entre easing Python e expressão ffmpeg | vídeos diferentes por backend | teste de paridade das 21 curvas, tolerância 1/255 (Fase 1.1) |
| `geq` para opacidade arbitrária derruba a performance | perde o ganho de 23x | preferir cadeia de `fade`; medir e logar; recusar acima de um limiar |
| Expressão enorme quebra o parser do ffmpeg | render falha | teto de 24 keyframes/track → `Unsupported` → MoviePy |
| Vírgula não escapada no `filter_complex` | ffmpeg interpreta como novo filtro, erro críptico | `esc()` centralizado + teste que conta vírgulas |
| `scale=eval=frame` com dimensão ímpar | falha em `yuv420p` | `trunc(x/2)*2` obrigatório |
| Palavra âncora não casa (variação do TTS) | animação fora de hora | normalização + fuzzy 88 + `on_missing` + log com sugestões |
| Regressão silenciosa no legado | quebra 6 canais em produção | Fase 0 bloqueante; SSIM ≥ 0.995 em todo PR |
| `_wrap_visual_layer` não reconhece a nova transparência | fade sobre preto | item explícito na Fase 4 |
| Cena sem narração usando âncora de palavra | miss em massa | `words=None` → `on_missing` direto, sem erro |

---

## 6. Checklist de execução

```
[x] Fase 0  fixtures + 8 golden + compare_ssim + baseline gravado
[x] Fase 1  libs/Motion/{easing,keyframes,presets,schema,timeline,errors}
[x]         test_motion_core.py (106 casos), paridade das 21 curvas verde
[x] Fase 2  anchors.py + encanamento do SRT + inspect.py + CLI
[x]         test_anchors.py verde (32 casos)
[x] Fase 3  compile_ffmpeg.py + overlay/scale_anim no builder + gate
[x]         SSIM vs baseline = 1.00000  (nenhuma regressão)
[x] Fase 4  compile_moviepy.py + _wrap_visual_layer + paridade SSIM ≥ 0.98
[x] Fase 5  presets completos + stagger + loop + text_box no caminho rápido
[x] Fase 6  reference/motion.md, reference/sync_narracao.md, SKILL.md, exemplos
[~] Fase 7  rotation ✅, background motion ✅, blur ✅ (animado só no MoviePy),
            beat ⬜ (não implementado — ver nota abaixo)
```

## 7. O que a execução mudou em relação ao plano

Registrado porque contradiz o texto acima, que ficou como estava quando foi escrito.

| ponto do plano | o que se verificou na prática |
|---|---|
| §3.5: ordem `… → border_radius → scale_anim` | `scale_anim` teve de ir para **depois de todo `fade`**: o filtro `fade` não reconfigura quando o quadro muda de tamanho e CONGELA a saída no tamanho do primeiro frame (um `pop_in` renderizava 18% menor para sempre) |
| §4 Fase 7: `rotate=…:ow=hypot(iw\,ih)` | com saída maior que a entrada e `c=none`, o `rotate` do ffmpeg 4.x **não limpa a margem**: o elemento girando deixa um rastro em leque. Solução: `pad` transparente até a diagonal **antes** do `rotate`, com `ow=iw:oh=ih` |
| §4 Fase 7: `blur` animado (`gblur=sigma='EXPR':eval=frame`) | o `gblur` **não aceita expressão** em `sigma` (nem `eval`) no ffmpeg 4.x. Blur constante é filtro normal; blur **animado** é recusado pelo gate e vai para o MoviePy (PIL por frame) |
| §4 Fase 4: `visible` via `set_start`/`set_end` | dentro de um `CompositeVideoClip` isso passa a dar tempo LOCAL ao clipe e **atrasa toda a animação** pelo início da janela. Implementado por máscara, que preserva o tempo absoluto |
| §2.3: `rotation` previsto só para a Fase 7 | implementado nos dois backends; o gate não recusa mais |
| §4 Fase 7: âncora por batida da música (`{"beat": 8}`) | **não implementado** — exigiria detecção de onsets (`librosa`/energia) no `background.audio`, uma dependência e um pipeline de análise fora do escopo do resto |
| §4 Fase 0: 6 golden JSONs | viraram 8 (legenda classic e karaokê ganharam arquivos próprios, alimentados por um SRT sintético) |

Armadilha herdada, encontrada no caminho: `background.visual.type: "file"` só é
entendido pelo caminho ffmpeg — o `BackgroundEngine` (MoviePy) espera `"image"`
e cai no fundo preto. Não foi alterado (está fora do escopo deste plano), mas
qualquer JSON que precise valer nos dois caminhos deve usar `"image"`.

Comando de verificação completo:

```bash
cd videomaker
python tests/fixtures/make_fixtures.py
pytest tests/ -q
RENDER_BACKEND=ffmpeg python main.py tests/motion/testes_motion.json
python tests/compare_ssim.py tests/baseline/ output/
```
