# Plano de performance de render — Fases 0 e 1

Branch: `perf/ffmpeg-filtergraph-render`
Local: `videomaker/docs/` (`development/` é gitignored)
Objetivo: viabilizar vídeos de 45+ min. Hoje 6 min leva 4–5 h (~45x realtime).

---

## Correções ao diagnóstico inicial (medido nesta máquina)

Duas premissas da minha análise inicial estavam erradas e mudam as prioridades:

**1. Não é 4K, é 1440p.** `resolve_output_resolution` ([utils.py:46-48](../libs/utils.py#L46-L48))
tem no máximo `16:9-2k` = 2560×1440. Os JSONs em uso estão em `"ratio": "16:9"` = 1920×1080.
O custo por pixel é ~4x menor do que eu assumi — o que torna o encode uma fatia *menor*
do problema e o MoviePy uma fatia *maior*.

**2. Não há encoder de hardware utilizável.** A GPU é **AMD Vega integrada** (`1002:15d8`),
não NVIDIA. `h264_nvenc` falha (`Cannot load libcuda.so.1`), `h264_qsv` falha (sem Intel).
VAAPI funciona apenas em `/dev/dri/renderD129`, e **é mais lento que x264 `veryfast`**
(13,5 s vs 11,9 s). O `setup.sh` instalando PyTorch CUDA não reflete este hardware.

> **A Fase 2 (encoder de hardware) do meu plano original está cancelada.** Não há ganho
> a extrair aqui. Todo o ganho vem de Fase 0 + Fase 1.

### Ambiente medido

| Item | Valor |
|---|---|
| CPU | 8 threads |
| RAM | 17 GB total, ~5–8 GB disponível |
| Disco | 185G/234G usados — **37 GB livres** (era 1,5 GB; liberado em 10/08/2026) |
| GPU | AMD Vega integrada — sem encode útil |
| moviepy | 1.0.3 (no Python do sistema, `~/.local`, sem venv em `videomaker/`) |

### Benchmarks (1440p, fonte real `testsrc2`, 15 s de vídeo, saída descartada)

Encoder isolado (ffmpeg puro, sem MoviePy):

| preset x264 | tempo | vs realtime |
|---|---|---|
| `slow` (= preset `high`, o default de hoje) | 60,3 s | 4,0x |
| `medium` | 23,8 s | 1,6x |
| `fast` | 19,3 s | 1,3x |
| `veryfast` | 11,9 s | 0,8x |
| `ultrafast` | 4,5 s | 0,3x |
| `h264_vaapi` (GPU) | 13,5 s | 0,9x |

MoviePy, mesmo encode (`veryfast`), medindo o overhead da composição em Python:

| cenário | tempo | overhead |
|---|---|---|
| A — encode puro via MoviePy, sem filtro | 17,6 s | baseline |
| B — composite + 3x `fl_image(force_rgb)` (**pipeline atual**) | 61,8 s | **3,5x** |
| C — composite + zoom animado `resize(lambda t)` | 72,1 s | **4,1x** |
| D — **mesmo resultado de C via filtergraph ffmpeg** | **14,8 s** | **4,9x mais rápido que C** |

**Leitura:** o custo está partido em dois, e ambos são atacáveis:
- **preset `slow`**: 60,3 s vs 11,9 s do `veryfast` → **5x** só de encoder.
- **composição em Python**: C=72,1 s vs D=14,8 s → **4,9x** no mesmo resultado visual.

Multiplicados, explicam a ordem de grandeza dos 45x realtime observados.

---

## Fase 0 — ganhos sem trocar a arquitetura

> **STATUS: IMPLEMENTADA** (commit `24d3c38`). Alvo era ~5–8x; **o ganho real foi ~3%.**
> A seção "Resultado medido" abaixo explica por quê e o que isso muda para a fase 1.

Alvo original: ~5–8x, poucos dias, risco baixo, cada item isolado e reversível.

### 0.1 — Parar de encodar cenas intermediárias em `slow`/crf18

**Onde:** [UnifiedVideoEngine.py:389-402](../libs/UnifiedVideoEngine.py#L389) (worker paralelo),
[:1117-1130](../libs/UnifiedVideoEngine.py#L1117) (`_render_scene` sequencial).

Cenas são artefato intermediário — vão ser **re-encodadas na concatenação**. Gastar
`slow`/crf18 nelas é desperdício puro: a qualidade é jogada fora no passe seguinte.

Trocar por um preset de *intermediário*: `ultrafast` + crf 12 (quase lossless, arquivo
maior, encode 13x mais rápido que `slow`). A qualidade final passa a ser decidida só
no encode de saída.

- Introduzir `INTERMEDIATE_QUALITY = {"crf": 12, "preset": "ultrafast", "pix_fmt": "yuv420p"}`
  em [utils.py](../libs/utils.py) ao lado de `QUALITY_PRESETS`.
- Usar nas 3 chamadas de cena; manter `self.output_quality` **apenas** no encode final.
- ⚠️ **Custo de disco:** crf 12 em 1440p gera ~8–10x mais bytes por cena. Com 37 GB
  livres há folga para vídeos curtos e médios, mas um render de 45 min precisa de
  estimativa antes — ver 0.5.

**Ganho esperado:** o maior item isolado da Fase 0.

### 0.2 — Eliminar o passe de re-encode do áudio de fundo

**Onde:** [`_apply_background_audio_simple`](../libs/UnifiedVideoEngine.py#L1055-L1094).

Hoje abre o vídeo final no MoviePy e **re-encoda o vídeo inteiro** só para mixar
música. O stream de vídeo é idêntico na entrada e na saída.

Substituir por ffmpeg com `-c:v copy`, mixando só áudio:

```
ffmpeg -y -i video.mp4 -stream_loop -1 -i bg.mp3 \
  -filter_complex "[1:a]volume=<vol>[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -movflags +faststart out.mp4
```

`-stream_loop -1` substitui o loop manual via `concatenate_audioclips`
([:1060-1063](../libs/UnifiedVideoEngine.py#L1060)).

**Ganho:** remove 1 encode 1440p completo do vídeo inteiro. Em 45 min, é enorme.

O caminho com ducking ([`_apply_background_audio_with_ducking`](../libs/UnifiedVideoEngine.py#L947))
**já faz** `-c:v copy` no merge ([:1015-1023](../libs/UnifiedVideoEngine.py#L1015)) — mas
chama `_ffmpeg_video_args()` junto, o que é contraditório. Verificar e remover essa
redundância (o `-c:v copy` vence, então provavelmente é só código morto confuso).

> **Nota:** o ducking calcula o envelope em Python via `AudioEffects.apply_ducking`.
> Se aparecer como gargalo na medição de 0.6, existe o `sidechaincompress` nativo
> (confirmado disponível). Fora do escopo da Fase 0 — só medir.

### 0.3 — Concatenação sem re-encode

**Onde:** [`_concat_and_apply_chapter_audio`](../libs/UnifiedVideoEngine.py#L1153) (2 passes:
`_concat_{chapter}` e `_concat_final`) e o concat simples em [:1577-1588](../libs/UnifiedVideoEngine.py#L1577).

Com 0.1, todas as cenas saem com parâmetros idênticos → o demuxer `concat` aceita
`-c copy`. Sem capítulos, cai para **1 único encode** (o final).

Cuidado: vídeos com capítulos hoje encodam por segmento *e* no final (2 passes). Com
`-c copy` no concat de capítulo e o encode de qualidade só no passe final, vira 1.

Manter `_ffmpeg_video_args()` **exclusivamente** para o encode final de saída.

### 0.4 — Deduplicar `fl_image(force_rgb)` e ajustar threads

`force_rgb` é aplicado em cada camada **e** no composto
([:346-357](../libs/UnifiedVideoEngine.py#L346)), e de novo dentro de
[VisualClip](../libs/VisualClip.py#L203) e [FilterEngine](../libs/Filters/FilterEngine.py#L78).
Cada aplicação é um passe Python sobre **todos os frames** (benchmark B: 3,5x de overhead).

Uma única aplicação no composto final é suficiente para o objetivo (garantir 3 canais).
Cuidado com a regressão de fade que acabei de corrigir: os clips com máscara alpha
**não** podem receber `force_rgb` antes do blend — a lógica de `skip` em
[:349-356](../libs/UnifiedVideoEngine.py#L349) precisa ser preservada.

Também: `threads=4` fixo nas 3 chamadas → `threads=0` (auto). Com `ProcessPoolExecutor`
de N workers × 4 threads em 8 CPUs há oversubscription; alinhar
`max_parallel_scenes` ([:635](../libs/UnifiedVideoEngine.py#L635)) a `cpu_count//2`.

### 0.5 — Disco e RAM

**Resolvido (10/08/2026): 37 GB livres.** Eram 1,5 GB — disco a 100%, o que degradava I/O
e impedia 0.1. O consumo não vinha do projeto (`assets` 547M, `output` 53M) e sim de
snaps antigos (`~/snap` estava em 83 GB, hoje 48 GB).

Sobra estrutural: 37 GB é folga, não abundância, para renders de 45 min em crf 12.
Itens que seguem valendo:

- Adicionar checagem de espaço livre no início de `run()`, falhando cedo com mensagem
  clara em vez de morrer no meio de um render de 45 min. Estimar a necessidade a partir
  da duração total × bitrate do preset intermediário.
- Limpar cenas intermediárias incrementalmente (após cada concat de capítulo), não só no fim.
- **Se faltar espaço no futuro:** o segundo disco (`sda`, Kingston 447G, hoje 100% NTFS do
  Windows) pode ceder uma partição. Encolher o NTFS **pelo Windows** (`diskmgmt.msc` →
  Shrink Volume — ele respeita `pagefile.sys`/`hiberfil.sys`, o `ntfsresize` não) e formatar
  a sobra como ext4. **Não** renderizar direto no NTFS: `ntfs-3g` (FUSE) é lento e consome
  CPU, que é justamente o recurso escasso aqui, e o Fast Startup do Windows deixa o volume
  sujo (risco de corrupção em escrita). Bônus: intermediários no `sda` + saída final no
  `nvme` distribui o I/O entre dois dispositivos.
- O guard de RAM ([:1358-1363](../libs/UnifiedVideoEngine.py#L1358)) força modo sequencial
  abaixo de 4 GB livres. Com 5–8 GB disponíveis (varia com o desktop aberto), **um vídeo
  de 45 min pode cair para sequencial** — sozinho explicaria uma piora não-linear com a
  duração. Continua valendo mesmo com o disco resolvido: é RAM, não disco. Registrar
  em log quando isso acontecer (hoje é silencioso demais para diagnóstico).

### 0.6 — Instrumentação (fazer **primeiro**)

Antes de otimizar, medir. Timing por etapa: TTS, Whisper, download de assets, composição,
encode de cena, concat, mix de áudio, upload. Um dict acumulado + resumo no fim de `run()`.

Sem isso, tudo acima é hipótese — inclusive minhas estimativas. É bem possível que TTS
ou Whisper sejam fatias relevantes em 45 min, e nenhuma delas é tocada pelas Fases 0/1.

### Ordem de execução

`0.6` (baseline) → `0.2` → `0.1` + `0.3` (juntos: só fazem sentido combinados) → `0.4`
→ medir de novo. O `0.5` deixou de ser bloqueante (disco liberado); resta só a checagem
de espaço em `run()`, que pode entrar junto com `0.1`.

---

## Resultado medido da Fase 0 — e por que ficou muito abaixo do previsto

Teste: 3 cenas reais do canal `the_touchline_record` (14,7 s de vídeo, 1080p, karaokê
ligado, zoom animado sobre fundo sólido), `DEBUG=1`.

| cenário | encode_cena | wall clock |
|---|---|---|
| `quality: draft`, sem otimização (`INTERMEDIATE_ENCODE=0`) | 3m30s | 5m01s |
| `quality: draft`, com otimização | 3m14s | 4m38s |
| `quality: high`, sem otimização (**produção hoje**) | 3m28s | 5m01s |
| `quality: high`, com otimização | 3m22s | 4m55s |

**~3% de ganho, não 5x.** A medição que explica tudo:

```
x264 puro (slow/crf18) re-encodando as MESMAS cenas:  ~1,9 s cada
encode_cena medido pelo profiler:                     ~67 s cada
```

**O encoder é ~3% do custo. Os outros ~97% são o MoviePy compondo frames em Python** —
e o `write_videofile` engloba as duas coisas, então o profiler atribui tudo a
`encode_cena`.

### Onde eu errei a estimativa

O benchmark que embasou o "~5x da fase 0" mediu **x264 isolado sobre conteúdo denso**
(`testsrc2`, 43 Mbps). O conteúdo real deste canal é quase estático: fundo de cor sólida
+ zoom lento + karaokê, com bitrate de **~220 kbps**. Para esse material o x264 é
praticamente de graça em qualquer preset — trocar `slow` por `ultrafast` economiza
segundos, não horas.

O gargalo real é o que o benchmark C→D já mostrava (72,1 s vs 14,8 s) e que eu subestimei
no peso relativo: **composição frame a frame em Python**. Neste canal ela é agravada por
dois multiplicadores que o teste expôs:

- **karaokê** — bitmap PIL renderizado e composto **por frame**;
- **zoom animado** (`resize(lambda t)`) — reamostragem do frame inteiro **por frame**.

### O que a Fase 0 entregou de fato

Ganho de tempo pequeno, mas os itens não são inúteis — mudam o custo estrutural:

- **Instrumentação** — foi o que permitiu descobrir o erro de diagnóstico acima.
  Sem ela, a fase 1 seria construída sobre a mesma premissa errada.
- **Passes de encode eliminados** (áudio de fundo, ducking, concat de capítulo) — o
  ganho não aparece neste teste porque ele **não tem** música de fundo nem capítulos.
  Em vídeos que usam esses caminhos, cada passe removido era um encode do vídeo inteiro
  — e isso escala com a duração, então tende a pesar mais em 45 min do que em 15 s.
- **Timeout proporcional à duração** — os 600 s fixos estourariam em cenas longas de
  vídeos de 45 min. Era um bug latente para o objetivo do projeto.
- **Pico de disco menor** e checagem de espaço antes de começar.
- **Bug do `debug`** — `"debug": true` no JSON era ignorado, e o vídeo subia pro YouTube.

### Consequência para a Fase 1

A fase 1 deixa de ser "mais 5x em cima da fase 0" e passa a ser **a fase que efetivamente
resolve o problema**. A projeção de ganho total praticamente não muda (o teto continua
sendo a composição), mas agora está claro que ~97% dele vem da fase 1.

Prioridade dentro da fase 1, revisada pela medição — atacar primeiro o que domina o custo:

1. **legendas → ASS/libass** (karaokê por frame é o item mais caro deste canal);
2. **zoom/animação → expressão de filtro** (elimina o `resize(lambda t)` por frame);
3. o resto da composição (`overlay`, `scale`, `crop`).

---

## Fase 1 — composição via filtergraph ffmpeg

> **STATUS: IMPLEMENTADA** (commit `1919098`). Alvo era ~5x; **o medido foi ~10x**
> nas cenas cobertas. Ver "Resultado medido da Fase 1".

Alvo original: ~5x adicional. A ideia: **Python deixa de tocar frames e passa a compilar
o JSON para um filtergraph**, que o ffmpeg executa em C, multi-thread, em streaming.

Benchmark D vs C já prova a ordem de grandeza (14,8 s vs 72,1 s) num caso real do pipeline.

### 1.1 — Mapeamento das primitivas

O pipeline já é declarativo, o que torna a tradução viável:

| hoje (MoviePy) | filtergraph |
|---|---|
| `resize` + crop cover | `scale` + `crop` |
| `resize(lambda t)` (zoom) | `scale` com expr em `t` + `eval=frame`, ou `zoompan` |
| `set_position` | `overlay=x=:y=` |
| fade / `opacity` | `fade`, `colorchannelmixer=aa=`, `blend` |
| `border_radius` (máscara PIL) | `alphamerge` com máscara PNG pré-gerada 1x |
| legendas (`TextClip`/PIL por frame) | **`ass`** — arquivo ASS + libass |
| transições ([Fade](../libs/Transitions/Fade.py)/[Zoom](../libs/Transitions/Zoom.py)) | `xfade` |
| `CompositeVideoClip` | cadeia de `overlay` |

Todos confirmados disponíveis no ffmpeg local.

**Legendas merecem destaque:** hoje são bitmaps PIL/ImageMagick compostos por frame — um
dos itens mais caros. ASS via libass é nativo, mais rápido e **mais nítido** (vetorial,
elimina a necessidade do supersampling que acabei de adicionar em `text_box`). O karaokê
tem suporte nativo em ASS (tags `\k`), o que casa bem com
[KaraokeSubtitle](../libs/Subtitle/types/KaraokeSubtitle.py).

### 1.2 — Arquitetura: `FilterGraphBuilder`

Novo módulo `libs/Render/FilterGraphBuilder.py`, sem tocar no MoviePy:

- entrada: mesmo dict de cena que `_process_scene_worker` recebe hoje;
- saída: `(lista_de_inputs, filter_complex_str, mapa_de_saída)`;
- `libs/Render/FFmpegSceneRenderer.py` monta e executa o comando.

Testável isoladamente: dado um JSON de cena, o filtergraph gerado é uma string —
comparável em teste sem renderizar nada.

### 1.3 — Estratégia de migração (incremental, com fallback)

O ponto crítico: **não é um rewrite big-bang.** Por cena, decidir o caminho:

1. `FilterGraphBuilder.can_handle(scene)` → todos os elementos têm equivalente em filtro?
2. Sim → caminho ffmpeg. Não → cai no `_process_scene_worker` atual, intacto.
3. Flag `RENDER_BACKEND=ffmpeg|moviepy|auto` (env var) para forçar comparação A/B.

Assim o pipeline nunca fica quebrado, e a cobertura cresce elemento por elemento.

Ordem de cobertura **revisada pela medição da fase 0** — por custo, não por simplicidade
(ver "Resultado medido"): **legendas ASS** → **zoom/animação** → `background` sólido/imagem
→ `visual_elements` estáticos → `border_radius` → transições `xfade`.

Legenda e zoom vêm primeiro porque são os dois multiplicadores por frame que dominam o
custo hoje. Cobri-los já deve render a maior parte do ganho, mesmo antes de o resto da
composição migrar.

### 1.4 — Ganho estrutural além da velocidade

O modelo de streaming do ffmpeg **não materializa frames em RAM**. Isso remove a causa
raiz do guard de RAM (0.5) e faz o custo escalar linearmente com a duração — que é
exatamente o requisito de 45+ min.

### 1.5 — Validação

- **Visual:** SSIM/PSNR entre saída MoviePy e ffmpeg da mesma cena (`ffmpeg -lavfi ssim`).
  Cenas com fade/opacity são as de maior risco de regressão (foi onde o bug do fade preto
  estava) — priorizar na validação.
- **Sincronia A/V:** duração e offset de áudio por cena; a concatenação é sensível a drift.
- **Perf:** tempo por cena nos dois backends, com o mesmo JSON.

---

## Resultado medido da Fase 1

No pipeline real (cena 1080p: fundo sólido com zoom, 2 imagens com `zoom_in` +
`border_radius`, karaokê):

| caminho | tempo por cena |
|---|---|
| MoviePy (`RENDER_BACKEND=moviepy`) | **76 s** |
| filtergraph (`auto`) | **7,7 s** |

Teste isolado equivalente: 47,1 s → 5,2 s (9x). Probe mínimo (fundo+zoom+ASS,
sem imagens): 47,6 s → 2,0 s (23x).

### Fidelidade visual (validada, não assumida)

Comparando o mesmo frame nos dois backends:

- **posicionamento idêntico** — bounding boxes iguais (`(96,158,941,815)` nos dois);
  1px de diferença num elemento, por arredondamento;
- **zoom equivalente** — largura do elemento animado ao longo do tempo:
  1501/1522/1545/1567 (ffmpeg) contra 1503/1523/1547/1570 (MoviePy) — no máximo
  3px em ~1500 (0,2%);
- os **3,6% de pixels divergentes** são antialiasing nas bordas de alto contraste,
  não erro de layout.

### Duas descobertas que exigiram solução

**1. PIL e libass dimensionam fonte diferente.** Com o mesmo `font_size`, o texto
ASS saía ~1,7x menor. Tentei derivar o fator de `unitsPerEm`/`hhea` — previa 1,22
contra 1,70 reais, porque o libass aplica normalização própria. Solução: calibrar
empiricamente por fonte (uma chamada de ffmpeg, ~0,2 s) e cachear em disco. Depois
da correção: largura 283 vs 292 px (3%), centros a 2px.

**2. Nome de família é ambíguo.** `Montserrat-Black.ttf` e `Montserrat-BlackItalic.ttf`
declaram a MESMA família. Por isso o estilo carrega o flag de itálico (lido do
nameID 17/2) e o filtro recebe `fontsdir` apontando para a pasta da fonte.

### Cobertura atual (commit `a7c69bc`)

Coberto: fundo `color`/`file`/`remote_asset` (imagem) com cover e `focus`,
zoom de fundo, `visual_elements` imagem/remote_asset, **modo cover
(`placement.width`+`height`)**, **`focus: "face"`**, `zoom_in`, `fade_in`,
`border_radius`, `opacity`, legendas classic e karaokê.

**Cai no MoviePy** (e continua funcionando): fundo de vídeo, `directory`, `ai`,
`contain-blur`, filtros (light_leak/partículas), transições, `text_box`,
`visual_element` de vídeo e legenda com `shadow.blur`.

Com isso o JSON de produção do `the_touchline_record` **passou a usar o caminho
rápido**: 2 de 3 cenas a 5,9 s/cena contra 53 s. A cena restante cai por causa do
`shadow.blur` no `palette` do canal.

#### Validação do crop com foco

O crop foi conferido número a número contra o MoviePy, inclusive num caso em que os
dois caminhos **divergem entre si** — o que prova que a detecção realmente decide:

| | `focus: "face"` | `focus: "center"` |
|---|---|---|
| crop_y ffmpeg | 0 | 449 |
| crop_y MoviePy | 0 | 449 |

(No caso `face`, o rosto está no alto e o offset bate no clamp de borda.)

#### Por que `shadow.blur` continua recusado

Cheguei a implementar via tag `\blur` e **revertí**: no ASS o `\blur` borra o
GLIFO junto com a sombra, enquanto o caminho PIL borra apenas a camada de sombra.
Pixels de branco sólido no miolo do texto (Montserrat Black 140):

| blur | 0 | 3 | 6 | 9 |
|---|---|---|---|---|
| núcleo branco | 13261 | 8062 | 2598 | **164** |

Com o `blur: 9` que o canal usa, o texto praticamente desaparece. Não há
equivalente fiel — a recusa é a decisão correta.

**Para colher o ganho na cena que falta**, a opção mais simples é editar o canal:
trocar `shadow: {blur: 9}` por um stroke ou por sombra sólida (`blur: 0`) deixa a
cena elegível. É uma decisão de estética, então fica com você.

### Cobertura ampliada — 91% (commits `34dee95`, `ed73ffe`)

Medido varrendo `jsons/` (327 cenas): **296 no caminho rápido (91%)**, contra ~50%
na primeira versão da fase 1. O que entrou:

| Item | Cenas | Como |
|---|---|---|
| `background type: "ai"` | 130 | Já termina como arquivo em disco; `_stretch` replica o resize puro do `_build_ai` (sem cover) |
| `zoom_out` / `zoom_pulse` / `fade_zoom_in` | 43 | `_zoom_expr` generaliza o zoom por expressão em `t` |
| Transição `fade` | 59 | Filtro `fade` com `c=` — as transições são **intra-cena**, não entre cenas |
| `visual_element type: "color"` | 3 | lavfi `color` no tamanho da caixa |

Validações (medidas, não presumidas):

- **zoom_out, zoom_pulse, zoom_in**: largura real do conteúdo por frame, **0px de
  diferença** contra o MoviePy em todos os pontos amostrados.
- **fade_zoom_in**: brilho 16→55→135→255 em 0,6 s, contra 0→43→126→255 do
  `crossfadein`.
- **transição fade**: brilho médio idêntico em brilho cheio e em t=0; máximo de
  5/255 (2%) no meio da transição.

> Uma correção de brinde: `_build_ai` consultava `ai_cache.get()` mas **ninguém no
> projeto chamava `store()`** — o cache de IA ficava sempre vazio e cada render
> regerava a imagem. O caminho rápido agora grava, e a segunda execução acusa
> `Cache hit`. Vale para os dois caminhos.

### O que ainda cai no MoviePy

**31 cenas, todas por `subtitle shadow.blur`** — e isso é decisão de estética, não
limitação técnica (ver a seção sobre `\blur` acima). Trocar por stroke ou sombra
sólida no `channels_config` levaria a cobertura a ~100%.

Sem ocorrências nos JSONs atuais, mas ainda descobertos: fundo de vídeo /
`directory`, `contain-blur`, filtros (light_leak/partículas), `text_box`,
`visual_element` de vídeo, transição `zoom` (shake amortecido, sem equivalente
fiel) e fade com sfx.

---

## Resumo e expectativa

| | hoje | Fase 0 (medido) | Fase 1 (medido) |
|---|---|---|---|
| passes de encode | 3–4 | 1 | 1 |
| preset de cena | `slow` | `ultrafast` crf12 | `ultrafast` crf12 |
| composição | Python, por frame | Python, por frame | **C, streaming** |
| tempo por cena | ~76 s | ~74 s | **~7,7 s** |
| ganho | — | ~3% | **~10x** (cenas cobertas) |

A fase 0 rendeu ~3% porque, no conteúdo real, o encoder já era ~3% do custo — o teto
estava inteiro na composição. A fase 1 atacou exatamente isso e entregou ~10x, acima
dos ~5x projetados.

**Ganho de ponta a ponta (atualizado no commit `a7c69bc`):** com modo cover e
`focus: "face"` cobertos, o JSON de produção já usa o caminho rápido — o wall clock
do teste de 3 cenas caiu de ~4m57s para ~2m40s, limitado pela única cena que ainda
cai no MoviePy (por `shadow.blur`). Ajustando esse detalhe no canal, o teste inteiro
roda em ~2 min.

Com cobertura completa, 45 min de vídeo sairia da ordem de ~15 h para ~1,5 h. Reduzir
mais depende de paralelismo (hoje limitado por RAM) ou máquina maior — e vale notar que,
com o ffmpeg em streaming, o consumo de RAM por cena cai muito, o que deve permitir
subir `MAX_PARALLEL_SCENES` sem bater no guard de 4 GB.

**Duas decisões que valem mais que otimização de código:**

1. **Manter 1080p.** Os JSONs atuais já usam `16:9` (1080p); 1440p custa ~44% mais pixels
   em todo o pipeline — inclusive na composição, que é o gargalo. Só subir para 2K se
   houver requisito real.
2. **Hardware.** Não há encoder de hardware utilizável nesta máquina (GPU AMD Vega, sem
   NVENC/QSV). Mas, dado que o gargalo é composição em Python e não encode, **uma GPU
   resolveria pouco** — o que ajuda aqui é mais CPU/RAM (mais workers em paralelo) ou a
   fase 1. O `setup.sh` instalar PyTorch CUDA sugere uma suposição de hardware que não
   corresponde a esta máquina.
