# visual_elements — Tipos, propriedades e muitos exemplos JSON

Resumo de propriedades comuns
- type: "image" | "video" | "text_box" | "overlay"
- source: caminho local ou URL (quando aplicável)
- layout: { width, height, position, margin, rotation }
  - width/height: "50%" ou 400 (px)
  - position: center | top_left | top_center | top_right | center_left | center_right | bottom_left | bottom_center | bottom_right
  - position também pode ser objeto: { "type":"custom", "x":0.1, "y":0.2 } (fração da tela)
- animation: { type, duration, start_at } — exemplos: fade_in, zoom_in, slide_left, slide_right
- filters: { remove_bg, blur, brightness, contrast }
- layer/order: menor index fica por baixo (defina a ordem no array)

Exemplos por tipo

1) Image — básico
```json
{
  "type": "image",
  "source": "./assets/images/logo.png",
  "layout": { "width": "30%", "position": "top_center", "margin": 50 },
  "animation": { "type": "fade_in", "duration": 0.8, "start_at": 0.2 }
}
```

2) Image — remover fundo + rotação
```json
{
  "type": "image",
  "source": "./assets/images/person.png",
  "filters": { "remove_bg": true },
  "layout": { "width": "50%", "position": "center", "rotation": 5 },
  "animation": { "type": "zoom_in", "duration": 1.2 }
}
```

3) Video overlay (loop/volume)
```json
{
  "type": "video",
  "source": "./assets/overlays/particle_loop.mp4",
  "layout": { "width": "100%", "position": "center" },
  "animation": { "type": "full", "duration": "full" },
  "filters": { "opacity": 0.6 }
}
```

4) Text box — título simples
```json
{
  "type": "text_box",
  "content": "5 DICAS RÁPIDAS",
  "style": {
    "font_family": "Poppins-Bold",
    "font_size": 86,
    "text_color": "#FFFFFF",
    "background_color": "transparent",
    "padding": [12, 30],
    "border_radius": 8
  },
  "layout": { "position": "bottom_center", "margin": 120 },
  "animation": { "type": "slide_up", "duration": 0.7, "start_at": 0.3 }
}
```

5) Text box — multi-linha com alinhamento
```json
{
  "type": "text_box",
  "content": "Line 1\nLine 2\nLine 3",
  "style": {
    "font_family": "Roboto-Bold",
    "font_size": 48,
    "text_color": "#000000",
    "background_color": "#FFD700",
    "padding": [16, 20],
    "align": "center"
  },
  "layout": { "position": "center", "width": "80%" },
  "animation": { "type": "fade_in", "duration": 0.6 }
}
```

6) Complex scene — várias camadas e tempos (exemplo de cena completa)
```json
{
  "id": "cena_completa",
  "duration": 6.0,
  "narration": { "text": "Exemplo de cena completa", "subtitles": true },
  "visual_elements": [
    {
      "type": "image",
      "source": "./assets/bg_blur.jpg",
      "layout": { "width": "100%", "position": "center" }
    },
    {
      "type": "video",
      "source": "./assets/videos/foreground_clip.mp4",
      "layout": { "width": "70%", "position": "center_left" },
      "animation": { "type": "slide_right", "duration": 1.0, "start_at": 0.2 }
    },
    {
      "type": "text_box",
      "content": "Headline",
      "style": { "font_family": "Montserrat-Bold", "font_size": 72, "text_color": "#FFFFFF" },
      "layout": { "position": "top_center", "margin": 120 },
      "animation": { "type": "fade_in", "duration": 0.6, "start_at": 0.1 }
    },
    {
      "type": "image",
      "source": "./assets/cta.png",
      "layout": { "width": 200, "position": { "type": "custom", "x": 0.82, "y": 0.85 } },
      "animation": { "type": "pop", "duration": 0.5, "start_at": 4.0 }
    }
  ]
}
```

7) Remote image with fallback and filters
```json
{
  "type": "image",
  "source": "https://cdn.example.com/img/banner.jpg",
  "fallback_source": "./assets/images/banner_local.jpg",
  "filters": { "blur": 2, "brightness": 1.05 },
  "layout": { "width": "100%", "position": "top_center" }
}
```

8) Overlay (logo + corner badge)
```json
{
  "type": "overlay",
  "elements": [
    { "type":"image", "source":"./assets/logo_small.png", "layout":{"width":80,"position":"top_left","margin":20} },
    { "type":"text_box", "content":"NEW", "style":{"font_size":28,"text_color":"#FFF","background_color":"#E60023"}, "layout":{"position":"top_right","margin":20} }
  ]
}
```

Boas práticas e observações técnicas
- Prefira assets locais para garantir previsibilidade; URLs aumentam latência.
- Width em % facilita responsividade entre 9:16 e 16:9.
- start_at/duration de animações são em segundos relativos à cena.
- Para performance, mantenha imagens com resolução adequada ao output.