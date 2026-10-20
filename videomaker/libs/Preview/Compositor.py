"""Composição dos `visual_elements` de um quadro (preview de cena e thumbnail).

Espelha `UnifiedVideoEngine._create_visual_elements_clip_worker`, mas sem
importá-lo. O motivo é puramente de tempo de import: o `UnifiedVideoEngine`
carrega NarrationEngine (TTS + Whisper), TransitionEngine e FaceDetector, o que
custa ~9s antes de qualquer trabalho — para uma thumbnail, que não tem áudio nem
transição, é tudo desperdício. Aqui os imports pesados ficam nas funções que
realmente precisam deles.

A ORDEM das operações é a mesma do worker de cena (resize → crop → animação →
border_radius → filtros → opacidade → posição); quem mexer aqui deve manter o
paralelo, senão preview e vídeo final divergem.
"""

import os
from types import SimpleNamespace

from moviepy.editor import CompositeVideoClip

from libs.LayoutEngine import LayoutEngine


def _cover_crop_offset(clip, axis_size: int, crop_size: int, focus: str, axis: str) -> int:
    """Início do crop cover num eixo. `focus="face"` centra no maior rosto.

    Mesma regra de `UnifiedVideoEngine._cover_crop_offset`. O `FaceDetector`
    (que puxa cv2) é importado só quando `focus="face"` — o caso raro.
    """
    center = axis_size / 2
    if focus == "face":
        try:
            from libs.FaceDetector import detect_focus_point

            point = detect_focus_point(clip.get_frame(0))
            if point:
                center = point[0] if axis == "x" else point[1]
        except Exception as e:
            print(f"[Thumbnail] Falha na detecção de rosto, usando centro: {e}")
    offset = int(center - crop_size / 2)
    return min(max(offset, 0), axis_size - crop_size)


def build_visual_layer(elements: list, duration: float, work_dir: str,
                       resolution: tuple, layout_params: dict,
                       remote_asset_manager=None, rest_pose: bool = False):
    """Lista de clips posicionados, prontos para entrar no composite da cena.

    Devolve sempre uma LISTA (possivelmente vazia). Diferente do worker de cena,
    não achata os clips num CompositeVideoClip intermediário: numa imagem
    estática não há ganho, e achatar sobre preto quebraria a transparência de
    degradês e textos sem fundo.
    """
    if not elements:
        return []

    from libs.VisualClip import (VisualClip, apply_border_radius_clip,
                                 apply_animation_in_window, apply_visual_filters)

    print(f"[Compositor] Processando {len(elements)} elementos visuais...")

    clips = []
    data_for_layout = []

    for i, element_data in enumerate(elements):
        try:
            processor = VisualClip({
                "element_data": element_data,
                "resolution_output": resolution,
                "temp_dir": work_dir,
                "duration": duration,
                "remote_asset_manager": remote_asset_manager,
            })
            raw_clip = processor.generate()
            if raw_clip:
                item = dict(element_data)
                item["original_size"] = raw_clip.size
                clips.append(raw_clip)
                data_for_layout.append(item)
        except Exception as e:
            print(f"[Thumbnail] Erro no elemento {i + 1}: {e}")

    if not clips:
        return []

    try:
        layouts = LayoutEngine.process_stack_layout(
            data_for_layout, SimpleNamespace(**layout_params))
    except Exception as e:
        # Sem layout resolvido, centralizar é melhor que perder o elemento.
        print(f"[Thumbnail] Falha no LayoutEngine: {e}")
        return [c.set_position("center") for c in clips]

    final_clips = []
    for i, clip in enumerate(clips):
        if i >= len(layouts):
            break
        layout = layouts[i]
        data = data_for_layout[i]
        try:
            clip = clip.resize(newsize=layout.get("_resize_to") or layout["final_size"])

            focus = data.get("focus", "center")
            crop_h, crop_w = layout.get("crop_height"), layout.get("crop_width")
            if crop_h and crop_h < clip.h:
                y1 = _cover_crop_offset(clip, clip.h, crop_h, focus, "y")
                clip = clip.crop(y1=y1, y2=y1 + crop_h)
            if crop_w and crop_w < clip.w:
                x1 = _cover_crop_offset(clip, clip.w, crop_w, focus, "x")
                clip = clip.crop(x1=x1, x2=x1 + crop_w)

            # No modo cover a animação foi adiada para depois do crop.
            # Pose de repouso: sem animação, elemento já no estado final.
            deferred = None if rest_pose else layout.get("deferred_animation")
            if deferred:
                clip = apply_animation_in_window(clip, deferred)

            radius = layout.get("border_radius", 0)
            if radius and radius > 0:
                clip = apply_border_radius_clip(clip, int(radius))

            clip = apply_visual_filters(clip, data.get("filters"))

            opacity = data.get("opacity")
            if opacity is not None and float(opacity) < 1.0:
                clip = clip.set_opacity(float(opacity))

            final_clips.append(clip.set_position(layout["final_position"]))
        except Exception as e:
            print(f"[Thumbnail] Falha ao posicionar elemento {i + 1}: {e}")

    return final_clips


def compose(background_clip, visual_clips: list, resolution: tuple, duration: float):
    """Compõe fundo + elementos num único clip."""
    return CompositeVideoClip([background_clip] + list(visual_clips),
                              size=resolution).set_duration(duration)
