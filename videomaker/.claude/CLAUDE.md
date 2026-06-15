# CLAUDE.md

Este arquivo fornece orientações ao Claude Code (claude.ai/code) ao trabalhar com o código deste repositório.

## O que este projeto faz

Automated Python Video Maker: gera vídeos curtos/longos para o YouTube a partir de uma especificação JSON. Cada JSON descreve cenas com narração (TTS), visuais de fundo, legendas, transições e upload opcional para o YouTube.

## Executando o projeto

```bash
# Gera um vídeo a partir de um arquivo JSON (pode ser uma lista de objetos de vídeo)
python main.py jsons/hacker_patriota.json

# Modo debug (pula o upload para o YouTube e abre o vídeo localmente)
DEBUG=1 python main.py jsons/myjson.json

# Controla o paralelismo (padrão: 2 workers)
MAX_PARALLEL_SCENES=4 python main.py jsons/myjson.json
```

Não há suítes de testes. Os testes são feitos manualmente executando `main.py` com um arquivo JSON.

## Estrutura do JSON

Cada objeto de vídeo possui:
- `slug` — nome do arquivo de saída e da pasta dentro de `output/`
- `channel_name` — carrega `channels_config/{channel_name}.json` como configuração base (mesclado via `deep_merge`)
- `output` — objeto raiz da saída: `{ "ratio": ..., "quality": ... }` (ver abaixo).
  Retrocompat: `output_ratio` solto na raiz ainda é aceito (equivale a `output.ratio`).
- `global_settings` — sobrescreve os padrões do canal: `tts`, `subtitle`, `background`, `transitions`, `padding_*`, `remote_assets`
- `scenes` (lista plana) OU `chapters` (agrupado; cada capítulo pode sobrescrever `global_settings` e `background.audio`)
- `youtube` — title, description, tags, `token_file_name`, `privacy_status`, `publish_at`

**Convenção de comentário no JSON**: qualquer chave terminada com `/` (ex: `"tts/"`) é silenciosamente ignorada por `_filter_comment_keys`. Use isso para manter configurações desabilitadas ou alternativas no arquivo.

### Saída (`output`)

```jsonc
"output": {
  "ratio": "16:9-2k",   // "9:16" | "16:9" | "16:9-2k" (2560×1440) | "9:16-2k" (1440×2560)
  "quality": "high"      // preset OU objeto de override fino (ver abaixo)
}
```

`output.quality` controla o encoding x264 (resolvido por `resolve_output_quality` em `libs/utils.py`)
e é aplicado em **todos** os pontos de render: cenas (paralelo/sequencial), mixagem de áudio e
re-encodes de concatenação (via `_ffmpeg_video_args`). Aceita:

- **Preset nomeado** (string): `"draft"` (crf 26/veryfast), `"balanced"` (crf 20/medium),
  `"high"` (crf 18/slow — **default** quando ausente), `"max"` (crf 16/slower).
- **Objeto de override**: parte de um preset e sobrescreve campos —
  `{ "preset": "high", "crf": 16, "fps": 30, "pix_fmt": "yuv420p" }`. O campo `preset` pode ser
  um preset nomeado (base) OU um preset x264 cru (`slow`, `medium`, …). `crf` 0–51 (menor = melhor).

> Para vídeos longos em 2K, use `"16:9-2k"` + `"high"`. CRF menor = mais qualidade e arquivo maior.
> A qualidade é definida já na render de cena; a concatenação re-encoda por cima, então use a mesma
> config nos dois (é o que o pipeline faz automaticamente).

### Campos de cena
```json
{
  "id": "cena_01",
  "narration": { "text": "..." },
  "duration": 5.0,          // opcional; padrão é a duração do TTS
  "background": { "visual": {...}, "audio": {...} },
  "visual_elements": [...], // imagens/vídeos sobrepostos posicionados pelo LayoutEngine
  "transitions": { "enabled": false },  // sobrescreve transições globais por cena
  "tts": { "provider": "edge" },        // sobrescreve o provider TTS por cena
  "subtitle": { "enabled": true, "font_size": 90 }  // liga/desliga + estilo das legendas por cena
}
```

### Tipos de visual de fundo
- `"type": "directory"` — escolhe um arquivo aleatório de uma pasta
- `"type": "file"` — caminho para um arquivo único
- `"type": "remote_asset"` — resolve um slug via `RemoteAssetManager` (lê `cache/remote_assets.json`)
- `"type": "ai"` — gera uma imagem/vídeo via `libs/AIProviders` (Pollinations)

### Posicionamento unificado (`placement`)

Tanto `visual_elements[]` quanto `subtitle` aceitam um bloco **`placement`** que
ancora o elemento dentro da **área segura** (margem definida pelos paddings):

```jsonc
"placement": {
  "anchor": ["right", "center"],  // x: left|center|right|"70%"|px • y: top|center|bottom|"50%"|px
  "width":  "70%",                // SÓ visual: largura (fração da área segura ou px)
  "region": "30%"                 // SÓ subtitle: confina o texto a uma faixa dessa largura
}
```

- `placement` é **opt-in**. Ausente → comportamento legado (visual em stack;
  legenda via `subtitle_position` + paddings). Zero regressão nos canais 9:16.
- No visual, `width ≤ 1` ou `"x%"` = fração; `> 1` = pixels (ver `LayoutEngine.calculate_dimension`).
  O `width` é um **teto**: se a altura resultante (mantendo o aspect ratio) estourar a
  área segura, o elemento é reduzido proporcionalmente — a proporção nunca é distorcida.
  Logo, imagem vertical em tela 16:9 com `width:"70%"` pode acabar ocupando menos largura.
- Na legenda, `region` define a largura da faixa e `anchor[0]` onde ela começa
  (ex.: visual 70% à direita + legenda `anchor:["left","center"], region:"30%"` =
  legenda nos 30% que sobraram à esquerda, sem sobreposição). No karaokê, a
  largura da faixa também encolhe o tamanho da fonte (`fit_font_size`).
- Núcleo: `LayoutEngine.resolve_anchor` (visual) e `SubtitleUtils.resolve_subtitle_box`
  (legenda, usado por `ClassicSubtitle` e `KaraokeSubtitle`).

**Paddings = área segura.** Significam margem uniforme onde tudo é ancorado. Os
defaults dependem da orientação (`_default_safe_paddings`): 9:16 mantém os
históricos (top 100 / bottom 850); 16:9 usa ~5% simétrico (side 96, top/bottom 54
em 1920×1080). Sobrescrevíveis em `global_settings` (`padding_top/bottom/side`).

> `visual_elements` com `type: "ai"` NÃO é suportado — só `image`, `video`,
> `text_box`. AI só vale para `background.visual`. Veja `jsons/teste_placement_16x9.json`.

### Providers de TTS
- `"edge"` — Microsoft Edge TTS (gratuito, sem credenciais)
- `"google"` — Google Cloud TTS (requer `credentials_file`)
- `"polly"` — AWS Polly
- `"kokoro"` — Kokoro TTS, modelo local de 82M (gratuito, sem credenciais). Roda num
  subprocesso isolado no `venv-whisper` (numpy>=2, incompatível com o numpy 1.22 do
  pipeline principal). Vozes PT-BR: `pf_dora` (F), `pm_alex`/`pm_santa` (M); `lang_code: "p"`.
  Legendas (word boundaries) vêm do Whisper, como no provider `google`. Veja
  `libs/Audio/tts/TTS_Kokoro.py` (wrapper) e `libs/Whisper/kokoro_runner.py` (síntese isolada).
  Instalação: `libs/Whisper/venv-whisper/bin/python -m pip install 'kokoro>=0.9.4' soundfile`.
- `"local_file"` — usa um arquivo de áudio pré-gravado (aciona segmentação via Whisper)

### Legendas (`subtitle`)

Tudo sobre legenda vive no objeto `subtitle` (em `channels_config`, `global_settings` ou na cena),
mesclado na cadeia **canal < global < cena** via `deep_merge`. O liga/desliga é `subtitle.enabled`
(default desligado quando ausente). **Não existe mais `narration.subtitles`** — foi removido.

`SubtitleEngine` (`libs/Subtitle/SubtitleEngine.py`) despacha por `subtitle.type`:

- `"classic"` (padrão / `type` ausente) — uma frase por entrada de SRT, cor/stroke/sombra únicos.
- `"karaoke"` — palavras surgem uma a uma no tempo da fala e se acumulam; limpa a cada
  `words_per_group`. Cada palavra recebe em rotação um item de `palette` (`fill`, `stroke`,
  `stroke_width`, `shadow`, `font_path`); a rotação reinicia por grupo. O tamanho da fonte é
  calculado para preencher a largura disponível (não vem da paleta). `layout`: `"one_per_line"`
  ou `"fill_line"`.

O karaokê tem **dois modos de agrupamento**, escolhidos pela presença dos campos:

- **Modo LEGADO** (default): paleta rotaciona **por palavra**, fonte dimensionada **por palavra**,
  tela limpa a cada `words_per_group`. É o que descrito acima.
- **Modo LINHAS** (opt-in — ativo se `min_chars_per_line` E/OU `line_fill_ratio` estiverem setados):
  as palavras são agrupadas em **linhas**, a paleta rotaciona **por linha** e a fonte é **uniforme
  por linha** (fit da linha inteira). Resolve o problema de palavra curta órfã/gigante.
  - `min_chars_per_line` — piso anti-órfã: a linha não fecha enquanto não atingir esse total de
    caracteres (palavra curta nunca fica sozinha).
  - `line_fill_ratio` — teto de largura (0–1): a linha fecha quando a próxima palavra faria a
    linha passar dessa fração da faixa.
  - Com os dois: fecha quando `min_chars` foi atingido **E** a próxima palavra estouraria o ratio.
  - A última linha órfã (abaixo do `min_chars`) é **grudada na linha anterior**.
  - `lines_per_group` (default 3) — quantas linhas por tela antes de limpar (substitui o papel
    do `words_per_group` neste modo).

```json
// Karaokê — modo LEGADO (paleta/fonte por palavra)
"subtitle": {
  "enabled": true,
  "type": "karaoke",
  "words_per_group": 4,
  "layout": "one_per_line",
  "palette": [
    { "fill": "#FFFFFF", "stroke": "#000000", "stroke_width": 3,
      "shadow": { "color": "#000000", "opacity": 0.85, "blur": 6, "offset": [4, 4] },
      "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf" },
    { "fill": "#1beb0c", "font_path": "./assets/fonts/Montserrat/Montserrat-BlackItalic.ttf" }
  ]
}

// Karaokê — modo LINHAS (paleta/fonte por linha)
"subtitle": {
  "enabled": true,
  "type": "karaoke",
  "min_chars_per_line": 5,     // piso anti-órfã (opcional)
  "line_fill_ratio": 0.85,     // teto de largura por linha (opcional)
  "lines_per_group": 3,        // linhas por tela antes de limpar
  "palette": [ /* 1 estilo por LINHA, em rotação */ ]
}
```

Em ambos os modos o timing é **word-by-word**: cada palavra aparece no seu `start` do SRT e some
quando o bloco limpa.

`palette` é lista → o `deep_merge` **substitui** a lista inteira (a paleta da cena vence a global,
não funde). Exemplo de teste: `jsons/teste_karaoke.json`.

## Arquitetura

```
main.py
  └── UnifiedVideoEngine          # orquestra todo o pipeline
        ├── NarrationEngine       # síntese TTS + alinhamento de legendas via Whisper
        │     ├── TTS_Edge / TTS_GoogleCloud / TTS_Polly
        │     ├── SilenceRemover  # remoção de silêncios via pydub
        │     └── AudioSegmenter  # divide arquivos de áudio locais longos
        ├── BackgroundEngine      # monta o clipe de fundo (vídeo/imagem/IA)
        │     ├── DirectoryType   # escolhe arquivo aleatório do diretório
        │     └── FiltersEngine   # animações zoom e contain-blur
        ├── VisualClip            # processa overlays de visual_elements
        ├── LayoutEngine          # posiciona/redimensiona elementos visuais (stack ou explícito)
        ├── SubtitleEngine        # despacha por subtitle.type → ClassicSubtitle | KaraokeSubtitle
        ├── TransitionEngine      # transições fade/zoom nas cenas
        │     ├── Fade / Zoom
        │     └── TransitionUtils
        ├── RemoteAssetManager    # resolve slug→URL e faz cache em disco
        │     └── Storage/        # JSONAssetStorage, RemoteAssetStorage
        ├── AIProviders           # geração de imagens (Pollinations)
        │     └── AICache         # faz cache das imagens geradas em cache/ai_generated/
        ├── MediaDownloader       # baixa vídeos/imagens remotos para temp/
        └── YouTube               # faz upload do MP4 final e define a thumbnail
```

**Processamento de cenas**: cada cena é processada de forma independente (sequencial ou em paralelo via `ProcessPoolExecutor`). Após todas as cenas renderizarem em MP4s individuais, elas são concatenadas via FFmpeg e o áudio de fundo é misturado.

**Ordem de mesclagem de configurações** (itens abaixo sobrescrevem os acima):
1. Config do canal (`channels_config/{channel_name}.json`)
2. `global_settings` do vídeo
3. `global_settings` do capítulo (se usar chapters)
4. Sobrescritas por cena (`tts`, `subtitle`, `transitions`)

Todas as mesclagens usam `deep_merge` de `libs/utils.py` — dicts aninhados são mesclados recursivamente, não substituídos.

## Detalhes importantes

- **Saída**: os arquivos renderizados vão para `output/{slug}/`. Após uma execução bem-sucedida fora do modo debug, os arquivos intermediários são removidos; se o upload para o YouTube estiver configurado, a pasta de saída inteira é deletada após o upload.
- **Whisper**: fica em `libs/Whisper/` com seu próprio virtualenv (`venv-whisper`). Usado apenas com o provider `local_file` para alinhamento de legendas.
- **Cache de remote assets**: `cache/remote_assets.json` mapeia slugs para URLs de mídia. `RemoteAssetManager` valida as URLs e as marca como válidas/inválidas.
- **Credenciais**: tokens OAuth do YouTube em `tokens/`, chave JSON do Google Cloud TTS também em `tokens/`. O arquivo `.env` pode conter segredos adicionais.
- **Paralelismo**: a variável de ambiente `MAX_PARALLEL_SCENES` controla os workers; cai automaticamente para 1 se a RAM disponível for menor que 4 GB.
