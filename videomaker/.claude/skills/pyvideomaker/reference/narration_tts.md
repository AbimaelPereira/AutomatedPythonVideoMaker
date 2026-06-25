# Narração e TTS (`narration` / `tts`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

`narration.text` é o texto a sintetizar; `tts` controla o provider e seus
parâmetros. O `NarrationEngine`
([NarrationEngine.py](../../../../libs/Audio/NarrationEngine.py)) gera o
áudio, aplica remoção de silêncio opcional e grava o SRT palavra-a-palavra
usado pelas legendas.

## Fluxo por cena

1. Provider TTS sintetiza áudio bruto + `word_boundaries`.
2. `SilenceRemover` detecta e remove silêncios no waveform (se `silence_removal`
   estiver habilitado) — não usa o SRT como guia, o SRT é regravado depois.
3. `word_boundaries` são remapeados para o novo timeline.
4. SRT final é gravado com os timestamps ajustados.

## Providers (`tts.provider`)

| Provider | Credenciais | Observação |
|----------|-------------|------------|
| `"edge"` (default) | nenhuma | Microsoft Edge TTS, gratuito. |
| `"google"` | `credentials_file` | Chirp3-HD/Neural2/WaveNet/Standard — modelo inferido pelo nome da voz. |
| `"polly"` | credenciais AWS (env/role) | AWS Polly. |
| `"kokoro"` | nenhuma | Modelo local 82M, roda em subprocesso isolado (`venv-whisper`) por conflito de numpy. Legendas vêm do Whisper. |
| `"local_file"` | — | Usa um áudio pré-gravado; aciona segmentação via Whisper (`AudioSegmenter`). |

### `edge`

```jsonc
"tts": {
  "provider": "edge",
  "voice": "pt-BR-AntonioNeural",
  "rate": "+15%",    // default
  "pitch": "+0Hz"    // default
}
```

### `google`

```jsonc
"tts": {
  "provider": "google",
  "credentials_file": "./tokens/credentials.json",
  "voice": "pt-BR-Chirp3-HD-Charon",
  "model": "Chirp3-HD",     // opcional — inferido da voz (Neural2/WaveNet/Standard detectados pelo nome)
  "speaking_rate": 1.15,    // ignorado pelo Chirp3-HD
  "pitch": 0.0,             // ignorado pelo Chirp3-HD
  "volume_gain_db": 0.0
}
```

### `kokoro`

```jsonc
"tts": {
  "provider": "kokoro",
  "voice": "pf_dora",       // pf_dora (F), pm_alex / pm_santa (M)
  "lang_code": "p",         // p = português brasileiro
  "speed": 1.0,
  "whisper_model": "base"
}
```

### `local_file`

```jsonc
"tts": { "provider": "local_file", "audio_file": "./temp/narracao.wav", "whisper_model": "base" }
```

Pré-processado por `NarrationEngine.preprocess_scenes` antes do pipeline
principal: transcreve via Whisper, gera SRT, segmenta o áudio por cena
(`AudioSegmenter`) e injeta `narration.audio_file`/`subtitle_file` em cada cena.

## Override por cena

`tts` na cena sobrescreve o `tts` global campo a campo (não é troca completa
de provider automática — se a cena define só `voice`, o `provider` ainda vem
do global, a menos que a cena também declare `provider`):

```jsonc
"scenes": [
  { "id": "c1", "narration": {"text": "..."}, "tts": { "voice": "pt-BR-Chirp3-HD-Aoede" } }
]
```

## Remoção de silêncio (`tts.silence_removal`)

```jsonc
// Preset
"silence_removal": { "enabled": true, "preset": "normal" }  // "tight" | "normal" | "relaxed"

// Parâmetros manuais
"silence_removal": {
  "enabled": true,
  "silence_thresh": -50,
  "min_silence_len": 1000,
  "keep_silence": 100
}
```

`silence_removal` da cena vence o global por completo se presente (não funde
parâmetro a parâmetro — é um dict só, então `deep_merge` cobre, mas na prática
normalmente se define o bloco inteiro de uma vez).

## Armadilhas frequentes

- **Cena sem `narration.text`** → duração fixa (default 4.0s); use `duration`
  explícito na cena. Ver [scenes.md](scenes.md).
- **`google` falhando silenciosamente** → confira `credentials_file` (ou
  `GOOGLE_APPLICATION_CREDENTIALS`); `validate_config` levanta erro explícito
  se o arquivo não existir.
- **Parâmetros numéricos do Google ignorados** → se vierem em formato Edge
  (`"+0Hz"`, `"+15%"`) do `tts_config` global, são descartados silenciosamente
  pelo parser `_safe_float` — use valores numéricos puros para `google`.
- **`kokoro` lento na primeira execução** → roda num venv isolado
  (`libs/Whisper/venv-whisper`); confira se `kokoro>=0.9.4` e `soundfile` estão
  instalados nesse venv, não no principal.

---

Próximos passos: [subtitle.md](subtitle.md) · [scenes.md](scenes.md).
