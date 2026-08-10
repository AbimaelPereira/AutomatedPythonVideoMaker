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

Alvo: **~5–8x**, poucos dias, risco baixo, cada item isolado e reversível.

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

## Fase 1 — composição via filtergraph ffmpeg

Alvo: **~5x adicional**. A ideia: **Python deixa de tocar frames e passa a compilar
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

Ordem sugerida de cobertura (mais simples/comum primeiro):
`background` sólido/imagem → `visual_elements` estáticos → zoom/fade → `border_radius`
→ legendas ASS → transições `xfade`.

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

## Resumo e expectativa

| | hoje | Fase 0 | Fase 0+1 |
|---|---|---|---|
| passes de encode 1440p | 3–4 | 1 | 1 |
| preset de cena | `slow` | `ultrafast` crf12 | n/a (sem cena intermediária) |
| composição | Python, ~4x overhead | Python, ~2x | C, streaming |
| ganho acumulado | — | **~5–8x** | **~20–30x** |

Se a Fase 0 entregar ~6x, 6 min sai de ~4,5 h para ~45 min, e 45 min fica na ordem de
5–6 h. Isso já torna o pipeline utilizável. A Fase 1 é o que traz 45 min para a faixa
de ~1 h.

**Duas decisões que valem mais que qualquer otimização de código:**

1. **1080p em vez de 1440p** corta ~44% dos pixels (benchmark: 7,3 s vs 12,8 s no mesmo
   encode). O YouTube re-encoda tudo de qualquer forma; a diferença percebida é pequena.
   Os JSONs atuais já estão em `16:9` (1080p) — vale confirmar se 1440p é requisito real.
2. **Se houver orçamento**, uma GPU NVIDIA ou uma VM com NVENC muda a equação de encode
   por completo. O hardware atual não oferece nada nessa frente — e o `setup.sh` sugere
   que isso já foi assumido como disponível quando não é.
