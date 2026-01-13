# Arquitetura Modular - UnifiedVideoEngine

## Diagrama de Fluxo

```
┌─────────────────────────────────────────────────────────────────────┐
│                       UnifiedVideoEngine (API)                       │
│                          74 linhas (wrapper)                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ delega para
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      VideoOrchestrator (Core)                        │
│                    425 linhas (orquestração)                         │
│                                                                       │
│  Coordena todo o fluxo end-to-end:                                  │
│  1. Configuração        → ConfigManager                             │
│  2. Para cada cena:                                                 │
│     ├─ Narração         → SpeechService                             │
│     ├─ Background       → AssetManager                              │
│     ├─ Elementos        → SceneRenderer                             │
│     ├─ Áudio            → AudioEngine                               │
│     └─ Renderizar cena                                              │
│  3. Concatenação        → ExportPipeline                            │
│  4. Áudio de fundo      → AudioEngine                               │
│  5. Entrega             → DeliveryService                           │
└───┬────┬────┬────┬────┬────┬────────────────────────────────────────┘
    │    │    │    │    │    │
    │    │    │    │    │    └──────────────────┐
    │    │    │    │    │                       │
    ▼    ▼    ▼    ▼    ▼                       ▼
┌────────────────────────────────────────┐  ┌──────────────────────┐
│         Services (Serviços)            │  │  Pipeline & Delivery │
├────────────────────────────────────────┤  ├──────────────────────┤
│                                        │  │                      │
│  ┌──────────────────────────────────┐ │  │  ┌────────────────┐ │
│  │     SpeechService (179 linhas)   │ │  │  │ ExportPipeline │ │
│  │  • TTS (Edge TTS)                │ │  │  │   (96 linhas)  │ │
│  │  • Geração de legendas (SRT)     │ │  │  │  • Concatenar  │ │
│  │  • Sincronização de áudio        │ │  │  │  • FFmpeg      │ │
│  └──────────────────────────────────┘ │  │  └────────────────┘ │
│                                        │  │                      │
│  ┌──────────────────────────────────┐ │  │  ┌────────────────┐ │
│  │     AssetManager (532 linhas)    │ │  │  │DeliveryService │ │
│  │  • Backgrounds (cor/img/vídeo)   │ │  │  │   (71 linhas)  │ │
│  │  • IA (Pollinations)             │ │  │  │  • YouTube     │ │
│  │  • Cache de assets               │ │  │  │  • Debug       │ │
│  │  • Seleção sem repetição         │ │  │  └────────────────┘ │
│  └──────────────────────────────────┘ │  │                      │
│                                        │  └──────────────────────┘
│  ┌──────────────────────────────────┐ │
│  │    SceneRenderer (216 linhas)    │ │
│  │  • Elementos visuais             │ │
│  │  • LayoutEngine                  │ │
│  │  • Overlays                      │ │
│  └──────────────────────────────────┘ │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │     AudioEngine (205 linhas)     │ │
│  │  • Mixagem de áudio              │ │
│  │  • Efeitos de transição          │ │
│  │  • Música de fundo               │ │
│  └──────────────────────────────────┘ │
│                                        │
└────────────────────────────────────────┘

         ┌───────────────────────────────┐
         │   ConfigManager (67 linhas)   │
         │  • Centraliza configurações   │
         │  • Resolução, paddings, etc   │
         └───────────────────────────────┘
```

## Fluxo de Processamento

```
1. main.py
   │
   ├─> Config (carrega configurações)
   │
   └─> UnifiedVideoEngine
       │
       └─> VideoOrchestrator
           │
           ├─> [SETUP]
           │   └─> ConfigManager (inicializa config)
           │
           ├─> [PARA CADA CENA]
           │   │
           │   ├─> SpeechService.generate_narration()
           │   │   └─> Edge TTS → áudio + SRT
           │   │
           │   ├─> AssetManager.create_background()
           │   │   ├─> Cor sólida
           │   │   ├─> Imagem
           │   │   ├─> Vídeo único
           │   │   ├─> Diretório (seleção aleatória)
           │   │   └─> IA (Pollinations + cache)
           │   │
           │   ├─> SceneRenderer.create_visuals()
           │   │   └─> VisualClip + LayoutEngine
           │   │
           │   ├─> SceneRenderer.apply_overlays()
           │   │   └─> OverlayEngine
           │   │
           │   ├─> SpeechService.create_subtitles()
           │   │   └─> Subtitle (SRT → clip)
           │   │
           │   ├─> [COMPOSIÇÃO]
           │   │   └─> Background + Visuals + Legendas
           │   │
           │   ├─> AudioEngine.mix_scene_audio()
           │   │   └─> Narração + Efeito de transição
           │   │
           │   └─> [RENDERIZAR CENA]
           │       └─> scene_0001.mp4, scene_0002.mp4, ...
           │
           ├─> [CONCATENAÇÃO]
           │   └─> ExportPipeline.concatenate_scenes()
           │       └─> FFmpeg concat → intermediate.mp4
           │
           ├─> [ÁUDIO DE FUNDO]
           │   └─> AudioEngine.apply_background_music()
           │       └─> intermediate.mp4 + música → final.mp4
           │
           └─> [ENTREGA]
               └─> DeliveryService
                   ├─> upload_to_youtube() (se configurado)
                   └─> open_video_in_player() (se debug)
```

## Comparação: Antes vs Depois

### Antes (Monolítico)
```
UnifiedVideoEngine.py
├─ 950 linhas
├─ Todas as responsabilidades misturadas
├─ Difícil de testar
├─ Difícil de manter
└─ Difícil de estender
```

### Depois (Modular)
```
libs/
├─ UnifiedVideoEngine.py (74 linhas - wrapper)
├─ services/ (4 serviços especializados)
│  ├─ SpeechService.py (179 linhas)
│  ├─ AssetManager.py (532 linhas)
│  ├─ SceneRenderer.py (216 linhas)
│  └─ AudioEngine.py (205 linhas)
├─ pipeline/ (exportação)
│  └─ ExportPipeline.py (96 linhas)
├─ delivery/ (entrega)
│  └─ DeliveryService.py (71 linhas)
└─ core/ (orquestração)
   ├─ ConfigManager.py (67 linhas)
   └─ VideoOrchestrator.py (425 linhas)

Vantagens:
✅ Separação clara de responsabilidades
✅ Fácil de testar cada componente
✅ Fácil de manter (arquivos menores)
✅ Fácil de estender (adicionar novos serviços)
✅ API pública mantida (compatibilidade total)
```

## Dependências Entre Módulos

```
UnifiedVideoEngine
    ↓
VideoOrchestrator
    ├──→ ConfigManager
    ├──→ SpeechService ──→ EdgeTTS, Subtitle
    ├──→ AssetManager ──→ BackgroundVideo, MediaDownloader, AIProviders
    ├──→ SceneRenderer ──→ VisualClip, LayoutEngine, OverlayEngine
    ├──→ AudioEngine ──→ SceneAudioManager
    ├──→ ExportPipeline ──→ FFmpeg (subprocess)
    └──→ DeliveryService ──→ YouTube

Legenda:
──→ : usa/importa
```

## Métricas

| Métrica | Antes | Depois | Melhoria |
|---------|-------|--------|----------|
| Linhas no arquivo principal | 950 | 74 | 92% ↓ |
| Número de arquivos | 1 | 12 | 12x ↑ |
| Tamanho médio dos arquivos | 950 | ~150 | 84% ↓ |
| Testabilidade | Baixa | Alta | 100% ↑ |
| Manutenibilidade | Baixa | Alta | 100% ↑ |
| Compatibilidade API | 100% | 100% | Mantida |

## Resumo de Linhas de Código

```
Categoria           | Arquivo                    | Linhas
--------------------|----------------------------|--------
API Pública         | UnifiedVideoEngine.py      |     74
Core                | ConfigManager.py           |     67
Core                | VideoOrchestrator.py       |    425
Serviços            | SpeechService.py           |    179
Serviços            | AssetManager.py            |    532
Serviços            | SceneRenderer.py           |    216
Serviços            | AudioEngine.py             |    205
Pipeline            | ExportPipeline.py          |     96
Entrega             | DeliveryService.py         |     71
__init__.py         | 4 arquivos                 |     40
--------------------|----------------------------|--------
TOTAL               |                            |  1,905
```
