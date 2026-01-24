# visual_elements — Tipos, propriedades e exemplos JSON

Resumo de propriedades comuns
- type: "image" | "video" | "text_box"
- source: caminho local ou URL (quando aplicável)
- layout: { width, height, position, margin, rotation }
  - width/height: "50%" ou 400 (px)
  - position: center | top_left | top_center | top_right | center_left | center_right | bottom_left | bottom_center | bottom_right
  - position também pode ser objeto: { "type":"custom", "x":0.1, "y":0.2 }
- animation: { type, duration, start_at } — exemplos: fade_in, zoom_in, slide_left, slide_right
- filters: { remove_bg, blur, brightness, contrast }
- layer/order: menor index fica por baixo

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

3) Video — overlay visual de arquivo
```json
{
  "type": "video",
  "source": "./assets/overlays/particle_loop.mp4",
  "layout": { "width": "100%", "position": "center" },
  "animation": { "type": "full", "duration": "full" },
  "filters": { "opacity": 0.6 }
}
```

4) Text box — título
```json
{
  "type": "text_box",
  "content": "TÍTULO",
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