# Configuração JSON Completa - AutomatedPythonVideoMaker

Este documento apresenta **todas as opções possíveis** de configuração JSON para geração automatizada de vídeos, baseado na análise completa do código-fonte.

## 📋 Estrutura Principal do Vídeo

```json
[
    {
        "slug": "identificador-unico",
        "channel_name": "nome_do_canal", 
        "output_ratio": "9:16",
        "global_settings": {},
        "scenes": [],
        "youtube": {},
        "debug": false,
        "debug_layout": false
    }
]
```

## 🎯 Propriedades Principais

### `slug` (string, obrigatório)
Identificador único usado para nomear arquivos de saída e organizar diretórios. 
```json
"slug":  "video_exemplo_001"
```

### `channel_name` (string, opcional)
Nome do canal para carregar configurações específicas de `channels_config/{nome}. json`.
```json
"channel_name": "meu_canal_youtube"
```

### `output_ratio` (string)
Proporção do vídeo de saída. 
```json
"output_ratio": "9:16"    // Vertical (1080x1920) - TikTok, Instagram Stories
"output_ratio": "16:9"    // Horizontal (1920x1080) - YouTube tradicional
```

## ⚙️ Configurações Globais (`global_settings`)

### 🗣️ Text-to-Speech (`tts`)
```json
"global_settings": {
    "tts":  {
        "voice": "pt-BR-AntonioNeural",
        "rate": "0%",
        "pitch": "0%",
        "volume": "0%"
    }
}
```

**Vozes disponíveis:**
- `"pt-BR-AntonioNeural"` - Masculina brasileira
- `"pt-BR-FranciscaNeural"` - Feminina brasileira  
- `"en-US-JennyNeural"` - Feminina americana
- `"en-US-GuyNeural"` - Masculina americana

### 📝 Legendas (`subtitle`)
```json
"global_settings":  {
    "subtitle": {
        "font_path": "./assets/fonts/Poppins/Poppins-Bold.ttf",
        "font_size": 110,
        "color": "#FFFFFF",
        "stroke_color": "#000000", 
        "stroke_width": 3
    }
}
```

### 🎬 Fundo (`background`)

#### Fundo Visual
```json
"background": {
    "visual": {
        "type": "image",              // Imagem única
        "source": "./assets/image/bg.jpg"
    }
}

// OU

"background":  {
    "visual": {
        "type": "video",              // Vídeo único
        "source":  "./assets/video/background.mp4"
    }
}

// OU

"background": {
    "visual": {
        "type": "directory",          // Múltiplos arquivos aleatórios
        "source": "./assets/video/backgrounds/"
    }
}
```

#### Fundo de Áudio
```json
"background": {
    "audio": {
        "type": "directory",
        "source": "./assets/audio/background/",
        "volume": 0.3
    }
}
```

### 🎨 Layout e Espaçamento
```json
"global_settings": {
    "padding_bottom": 850,
    "padding_top": 100,
    "padding_side": 50,
    "stack_gap_percent": 0.02
}
```

### 🔧 Configurações de Controle
```json
"global_settings":  {
    "shuffle_clips": true,           // Embaralhar clipes de fundo
    "max_clips":  10,                 // Máximo de clipes por vídeo
    "crossfade_duration":  0.8,       // Duração do crossfade entre clipes
    "enable_crossfade": true,        // Habilitar crossfade
    "loop_background":  true          // Loop do fundo se necessário
}
```

## 🎬 Estrutura de Cenas (`scenes`)

### Cena Básica
```json
"scenes": [
    {
        "id": "cena_001",
        "narration": {
            "text":  "Texto a ser narrado pela IA",
            "subtitles": true
        },
        "duration": 5.0
    }
]
```

### Cena com Configurações Personalizadas
```json
"scenes": [
    {
        "id": "introducao",
        "narration": {
            "text": "Bem-vindos ao canal! ",
            "subtitles": true
        },
        "tts": {
            "voice": "pt-BR-FranciscaNeural"
        },
        "background": {
            "visual": {
                "type": "image",
                "source": "./assets/intro.jpg"
            }
        },
        "visual_elements": [],
        "duration":  3.0
    }
]
```

### 📝 Propriedades de Narração
```json
"narration": {
    "text":  "Texto completo a ser convertido em áudio",
    "subtitles": true,          // Exibir legendas
    "duration": 5.0             // Duração fixa (sobrescreve duração calculada)
}
```

## 🎨 Elementos Visuais (`visual_elements`)

### Imagem
```json
"visual_elements": [
    {
        "type": "image",
        "source": "./assets/images/logo.png",
        "layout": {
            "width":  "50%",
            "position": "center",
            "margin": 20,
            "rotation":  0
        },
        "animation": {
            "type": "fade_in",
            "duration": 1.0,
            "start_at": 0.5
        },
        "filters": {
            "remove_bg": true
        }
    }
]
```

### Vídeo
```json
"visual_elements": [
    {
        "type": "video",
        "source": "./assets/videos/overlay.mp4",
        "layout": {
            "width":  "80%",
            "position": "top_center"
        },
        "animation": {
            "type": "zoom_in",
            "duration": "full"
        }
    }
]
```

### Caixa de Texto
```json
"visual_elements": [
    {
        "type": "text_box",
        "content": "Texto do elemento",
        "style": {
            "font_family": "Poppins-Bold",
            "font_size": 60,
            "text_color": "#FFFFFF",
            "background_color": "#FF6B6B",
            "padding": [15, 25],
            "border_radius": 10,
            "strikethrough": false
        },
        "layout": {
            "position": "bottom_center",
            "margin": 50
        }
    }
]
```

### 🎭 Animações Disponíveis
```json
"animation": {
    "type": "fade_in",           // Fade de entrada
    "duration": 1.0,             // Duração da animação
    "start_at": 0.5              // Início da animação (segundos)
}

"animation": {
    "type": "zoom_in",           // Zoom de entrada
    "duration": "full"           // Duração toda da cena
}
```

### 📍 Posições Disponíveis
```json
"layout": {
    "position": "center",        // Centro
    "position": "top_left",      // Canto superior esquerdo
    "position": "top_center",    // Centro superior
    "position":  "top_right",     // Canto superior direito
    "position": "center_left",   // Centro esquerda
    "position":  "center_right",  // Centro direita
    "position":  "bottom_left",   // Canto inferior esquerdo
    "position": "bottom_center", // Centro inferior
    "position": "bottom_right",  // Canto inferior direito
    "width": "50%",              // Largura em % ou pixels
    "margin": 20,                // Margem em pixels
    "rotation": 15               // Rotação em graus
}
```

### 🎨 Filtros de Imagem
```json
"filters": {
    "remove_bg": true            // Remove fundo automaticamente
}
```

## 📺 Configuração do YouTube (`youtube`)

```json
"youtube":  {
    "token_file_name": "canal. json",
    "title": "Título do Vídeo",
    "description": "Descrição completa do vídeo com quebras\nde linha suportadas.",
    "tags":  ["tag1", "tag2", "tag3"],
    "category_id": "22",
    "privacy_status": "private",
    "publish_at": "2024-12-25 10:00:00",
    "timezone": "America/Sao_Paulo"
}
```

**Categorias do YouTube:**
- `"1"` - Film & Animation
- `"2"` - Autos & Vehicles  
- `"10"` - Music
- `"15"` - Pets & Animals
- `"17"` - Sports
- `"19"` - Travel & Events
- `"20"` - Gaming
- `"22"` - People & Blogs
- `"23"` - Comedy
- `"24"` - Entertainment
- `"25"` - News & Politics
- `"26"` - Howto & Style
- `"27"` - Education
- `"28"` - Science & Technology

**Status de Privacidade:**
- `"private"` - Privado
- `"unlisted"` - Não listado  
- `"public"` - Público

## 🔧 Configurações de Debug

```json
{
    "debug":  true,               // Mostra configurações finais no console
    "debug_layout": true         // Mostra área de layout visual no vídeo
}
```

## 📁 Arquivo de Configuração de Canal

Arquivo `channels_config/{channel_name}.json`:
```json
{
    "output_ratio": "9:16",
    "global_settings": {
        "tts": {
            "voice": "pt-BR-AntonioNeural"
        },
        "subtitle": {
            "font_path": "./assets/fonts/Roboto/Roboto-Bold.ttf",
            "font_size": 90,
            "color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width": 2
        },
        "background":  {
            "visual": {
                "type": "directory",
                "source": "./assets/video/canal_backgrounds"
            },
            "audio":  {
                "type": "directory", 
                "source": "./assets/audio/canal_music"
            }
        },
        "padding_bottom": 700,
        "padding_top": 150
    },
    "youtube": {
        "token_file_name": "meu_canal.json",
        "privacy_status": "unlisted",
        "category_id": "24"
    }
}
```

## 🔄 Hierarquia de Configuração

O sistema utiliza herança de configurações na seguinte ordem de prioridade: 

1. **Padrões do Sistema** (código)
2. **Variáveis de Ambiente** (. env)
3. **Configuração do Canal** (`channels_config/`)
4. **Configuração do Vídeo** (JSON principal)
5. **Configuração da Cena** (scene-specific)

## 📋 Exemplo Completo Avançado

```json
[
    {
        "slug": "video_completo_exemplo",
        "channel_name": "meu_canal_premium",
        "output_ratio": "9:16",
        "debug": false,
        "global_settings": {
            "tts":  {
                "voice": "pt-BR-AntonioNeural"
            },
            "subtitle":  {
                "font_path": "./assets/fonts/Montserrat/Montserrat-Bold. ttf",
                "font_size":  85,
                "color": "#F0F0F0",
                "stroke_color": "#1A1A1A",
                "stroke_width": 2
            },
            "background": {
                "visual": {
                    "type": "directory",
                    "source": "./assets/video/premium_backgrounds"
                },
                "audio": {
                    "type": "directory",
                    "source":  "./assets/audio/cinematic"
                }
            },
            "padding_bottom": 800,
            "padding_top": 120,
            "padding_side": 60,
            "shuffle_clips": true,
            "crossfade_duration":  1.2
        },
        "scenes": [
            {
                "id": "abertura_impactante",
                "narration": {
                    "text": "Prepare-se para descobrir o segredo que vai mudar sua vida! ",
                    "subtitles": true
                },
                "visual_elements": [
                    {
                        "type":  "image",
                        "source": "./assets/logos/canal_logo.png",
                        "layout": {
                            "position": "top_center",
                            "width": "40%",
                            "margin": 80
                        },
                        "animation": {
                            "type": "fade_in",
                            "duration": 1.5,
                            "start_at": 0.2
                        },
                        "filters": {
                            "remove_bg": true
                        }
                    },
                    {
                        "type": "text_box",
                        "content": "EXCLUSIVO",
                        "style": {
                            "font_family":  "Montserrat-Bold",
                            "font_size": 45,
                            "text_color": "#FFD700",
                            "background_color": "#FF4444",
                            "padding": [12, 20],
                            "border_radius": 25
                        },
                        "layout": {
                            "position": "bottom_right",
                            "margin": 100
                        },
                        "animation": {
                            "type": "zoom_in",
                            "duration": 0.8,
                            "start_at": 1.0
                        }
                    }
                ],
                "duration":  4.0
            },
            {
                "id":  "conteudo_principal",
                "narration": {
                    "text": "Hoje vamos revelar as 3 estratégias que ninguém te conta sobre...",
                    "subtitles": true
                },
                "tts": {
                    "voice": "pt-BR-FranciscaNeural"
                },
                "background": {
                    "visual":  {
                        "type": "video",
                        "source": "./assets/video/conteudo_especifico.mp4"
                    }
                },
                "visual_elements":  [
                    {
                        "type": "image",
                        "source":  "https://example.com/imagem-online.jpg",
                        "layout": {
                            "position": "center",
                            "width":  "70%"
                        },
                        "animation":  {
                            "type": "fade_in",
                            "duration": 2.0
                        }
                    }
                ]
            },
            {
                "id": "call_to_action",
                "narration": {
                    "text": "Se você gostou, deixe seu like e se inscreva no canal!",
                    "subtitles":  true
                },
                "visual_elements": [
                    {
                        "type": "text_box",
                        "content":  "👍 LIKE\n📢 INSCREVA-SE",
                        "style": {
                            "font_family": "Roboto-Bold",
                            "font_size": 50,
                            "text_color": "#FFFFFF",
                            "background_color":  "transparent"
                        },
                        "layout":  {
                            "position": "center"
                        },
                        "animation":  {
                            "type": "zoom_in",
                            "duration": "full"
                        }
                    }
                ]
            }
        ],
        "youtube": {
            "token_file_name": "meu_canal_premium.json",
            "title": "O SEGREDO que VAI MUDAR SUA VIDA! 🔥",
            "description": "Neste vídeo exclusivo, revelamos as 3 estratégias mais poderosas para.. .\n\n🎯 TIMESTAMPS:\n00:00 - Introdução\n00:30 - Primeira estratégia\n02:15 - Segunda estratégia\n\n📢 INSCREVA-SE para mais conteúdos como este! ",
            "tags": ["desenvolvimento pessoal", "motivação", "sucesso", "estratégias"],
            "category_id":  "22",
            "privacy_status": "public",
            "publish_at": "2024-12-25 18:00:00",
            "timezone":  "America/Sao_Paulo"
        }
    }
]
```

## 🚀 Dicas Avançadas

### 📱 Otimizações por Formato
- **9:16 (Vertical)**: `font_size` 80-120, `padding_bottom` 700-900
- **16:9 (Horizontal)**: `font_size` 60-80, `padding_bottom` 400-600

### 🎨 Fontes Recomendadas
- **Roboto**:  Boa legibilidade geral
- **Montserrat**:  Moderna e impactante
- **Poppins**:  Amigável e clean
- **CormorantGaramond**: Elegante e clássica

### 🔗 URLs Suportadas
- URLs diretas de imagens/vídeos
- Links do YouTube (convertidos automaticamente)
- Caminhos locais relativos
- Caminhos locais absolutos

### 📊 Formatos Suportados
- **Vídeo**:  mp4, mkv, avi, mov, flv, webm
- **Imagem**: jpg, jpeg, png, gif, bmp, tiff
- **Áudio**: mp3, wav, aac, m4a, ogg

---

*Este documento apresenta TODAS as configurações disponíveis no AutomatedPythonVideoMaker. Use-o como referência completa para criar vídeos personalizados e profissionais.*