"""FFmpegSceneRenderer — renderiza uma cena inteira via filtergraph.

Decide se a cena é traduzível (`can_handle`) e, se for, monta e executa um único
comando ffmpeg que faz fundo + visuais + legenda + áudio em streaming. Se não
for, quem chama continua no caminho MoviePy — nenhum recurso é perdido, só a
velocidade.

Regra de ouro deste módulo: **na dúvida, recusar**. Um falso positivo entrega um
vídeo visualmente errado; um falso negativo só perde performance.
"""

import os
import subprocess

from libs.Render.FilterGraphBuilder import FilterGraphBuilder, Unsupported
from libs.Subtitle.AssBuilder import AssBuilder


# Animações com equivalente fiel em filtro. Cada uma espelha uma cláusula de
# `_zoom_resize`/`apply_animation_in_window` do VisualClip.
_SUPPORTED_ANIMATIONS = {
    "none", None,
    "zoom_in", "zoom_out", "zoom_pulse", "fade_zoom_in",
    "fade_in",
}

# Tipos de elemento visual suportados.
_SUPPORTED_VISUAL_TYPES = {"image", "remote_asset", "color"}


def _anim_type(element: dict) -> str:
    return (element.get("animation") or {}).get("type") or "none"


class FFmpegSceneRenderer:
    def __init__(self, resolution: tuple, quality: dict, profiler=None):
        self.resolution = (int(resolution[0]), int(resolution[1]))
        self.quality = quality
        self.profiler = profiler

    # ------------------------------------------------------------------
    # ELEGIBILIDADE
    # ------------------------------------------------------------------

    @classmethod
    def can_handle(cls, scene: dict, effective_gs: dict, subtitle_cfg: dict = None) -> tuple:
        """(ok, motivo). `motivo` explica a recusa, para log de diagnóstico."""
        bg = (effective_gs.get("background") or {}).get("visual") or {}
        bg_scene = (scene.get("background") or {}).get("visual") or {}
        bg = {**bg, **bg_scene}

        bg_type = bg.get("type")
        if bg_type not in ("color", "file", "remote_asset", "image", "ai", None):
            return (False, f"background.visual.type '{bg_type}' não suportado")

        # IA de vídeo continua no MoviePy (loop/subclip de clipe); imagem é
        # arquivo em disco e entra como qualquer outra.
        if bg_type == "ai" and bg.get("content_type", "image") != "image":
            return (False, "background ai content_type 'video' não suportado")

        if bg.get("fit_mode") in ("contain-blur", "contain"):
            return (False, f"background fit_mode '{bg.get('fit_mode')}' não suportado")

        # `focus` só tem efeito em crop de mídia; num fundo de cor sólida é
        # inócuo. "center" é o default; "face" é suportado (detecção 1x na
        # imagem, fora do loop de frames).
        if bg_type != "color" and bg.get("focus") not in (None, "center", "face"):
            return (False, f"background.focus '{bg.get('focus')}' não suportado")

        # Filtros visuais (light_leak, partículas…) não têm equivalente.
        if effective_gs.get("filters") or scene.get("filters"):
            return (False, "filters (overlay/modifier) não suportados")

        # Transições exigem compor duas cenas — fora do escopo por-cena.
        trans = scene.get("transitions") or effective_gs.get("transitions") or {}
        if trans.get("enabled"):
            return (False, "transições não suportadas")

        for i, el in enumerate(scene.get("visual_elements") or []):
            el_type = el.get("type")
            if el_type not in _SUPPORTED_VISUAL_TYPES:
                return (False, f"visual_elements[{i}].type '{el_type}' não suportado")
            anim = _anim_type(el)
            if anim not in _SUPPORTED_ANIMATIONS:
                return (False, f"visual_elements[{i}].animation '{anim}' não suportado")
            focus = el.get("focus")
            if focus not in (None, "center", "face"):
                return (False, f"visual_elements[{i}].focus '{focus}' não suportado")

        if subtitle_cfg and subtitle_cfg.get("enabled"):
            sub_type = (subtitle_cfg.get("type") or "classic").lower()
            if sub_type not in ("classic", "karaoke"):
                return (False, f"subtitle.type '{sub_type}' não suportado")
            # `shadow.blur` borra o glifo em ASS, não só a sombra — recusa cedo
            # aqui para nem baixar mídia (o motivo está em AssBuilder).
            palette = subtitle_cfg.get("palette") or []
            for item in palette:
                shadow = item.get("shadow") or {}
                if isinstance(shadow, dict) and float(shadow.get("blur", 0) or 0) > 0:
                    return (False, "subtitle com shadow.blur não é fiel em ASS")
            shadow = subtitle_cfg.get("shadow") or {}
            if isinstance(shadow, dict) and float(shadow.get("blur", 0) or 0) > 0:
                return (False, "subtitle com shadow.blur não é fiel em ASS")

        return (True, "")

    # ------------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------------

    def render(self, *, scene: dict, effective_gs: dict, duration: float,
               out_path: str, audio_path: str = None, ass_path: str = None,
               fontsdir: str = None, bg_resolved: dict = None,
               visual_elements: list = None) -> str:
        """Monta e executa o comando. Devolve o caminho de saída.

        `bg_resolved` e `visual_elements` já vêm com os caminhos de mídia
        resolvidos (download/cache feitos por quem chama) — este módulo não
        baixa nada.
        """
        w, h = self.resolution
        fps = int(self.quality.get("fps", 30))
        g = FilterGraphBuilder(self.resolution, fps)

        bg = bg_resolved or {}
        bg_type = bg.get("type", "color")

        # --- fundo ---
        if bg_type == "color":
            cur = g.background_color(bg.get("source", "#000000"), duration)
            cur = g.cover(cur, duration)
        else:
            path = bg.get("_path")
            if not path or not os.path.exists(path):
                raise Unsupported(f"fundo sem arquivo resolvido: {path}")
            cur = g.background_image(path, duration)
            if bg.get("_stretch"):
                # `type: "ai"` no BackgroundEngine faz resize puro para a
                # resolução de saída, sem preservar aspect ratio — replica isso
                # em vez de aplicar cover, senão o enquadramento diverge.
                cur = g.scale_to(cur, w, h)
                cur = g.set_sar(cur)
                bg_crop = None
            else:
                bg_crop = bg.get("_crop")
            if bg_crop:
                # cover com focus point: escala cobrindo a tela e recorta
                rw, rh, cx, cy = bg_crop
                cur = g.scale_to(cur, rw, rh)
                cur = g.crop_to(cur, cx, cy, w, h)
                cur = g.set_sar(cur)
            else:
                cur = g.cover(cur, duration)

        anim = (bg.get("animation") or {})
        if anim.get("type") == "zoom":
            intensity = float(anim.get("intensity", 0.1))
            anim_dur = float(anim.get("duration", duration)) or duration
            # O zoom global do BackgroundEngine percorre `intensity` ao longo de
            # `duration` do filtro (não da cena) — replica a mesma proporção.
            end = 1.0 + intensity * min(1.0, duration / anim_dur)
            cur = g.zoom(cur, 1.0, end, duration)

        # --- elementos visuais ---
        for el in (visual_elements or []):
            box = el.get("_box")          # (x, y, w, h) já calculado pelo layout
            if not box:
                raise Unsupported("visual_element sem caixa de layout")
            bx, by, bw, bh = box

            if el.get("type") == "color":
                # Cor sólida: gerada por lavfi no tamanho da caixa, sem arquivo.
                color = el.get("color", "#000000")
                color = color if str(color).startswith("#") else f"#{color}"
                idx = g.add_input([
                    "-f", "lavfi", "-t", f"{duration:.3f}",
                    "-i", f"color=c={color.replace('#', '0x')}:s={bw}x{bh}:r={fps}",
                ])
                lbl = g.set_sar(f"{idx}:v")
            else:
                path = el.get("_path")
                if not path or not os.path.exists(path):
                    raise Unsupported("visual_element sem arquivo resolvido")

                idx = g.add_input(["-loop", "1", "-t", f"{duration:.3f}",
                                   "-r", str(fps), "-i", path])

                # Modo cover: redimensiona cobrindo a caixa e recorta o excesso a
                # partir do focus point (mesma ordem do worker MoviePy:
                # resize → crop → animation → border_radius).
                resize_to = el.get("_resize_to") or (bw, bh)
                lbl = g.scale_to(f"{idx}:v", resize_to[0], resize_to[1])

                crop = el.get("_crop")
                if crop:
                    cx, cy, cw, ch = crop
                    lbl = g.crop_to(lbl, cx, cy, cw, ch)

            el_anim = _anim_type(el)
            a = el.get("animation") or {}
            # Zoom em janela fixa: transborda e volta ao tamanho da caixa,
            # preservando o layout quadro a quadro. Os defaults abaixo são os
            # mesmos de `_zoom_resize` (VisualClip), para não divergir.
            if el_anim == "zoom_in":
                lbl = g.zoom(lbl, float(a.get("start_scale", 1.0)),
                             float(a.get("end_scale", 1.15)), duration, bw, bh)
            elif el_anim == "zoom_out":
                lbl = g.zoom(lbl, float(a.get("start_scale", 1.15)),
                             float(a.get("end_scale", 1.0)), duration, bw, bh)
            elif el_anim == "zoom_pulse":
                lbl = g.zoom_pulse(lbl, float(a.get("intensity", 0.06)),
                                   duration, bw, bh)
            elif el_anim == "fade_zoom_in":
                lbl = g.zoom(lbl, float(a.get("start_scale", 1.0)),
                             float(a.get("end_scale", 1.12)), duration, bw, bh)

            radius = int(el.get("border_radius") or 0)
            if radius > 0:
                mask = el.get("_mask_png")
                if not mask or not os.path.exists(mask):
                    raise Unsupported("border_radius sem máscara gerada")
                lbl = g.rounded_mask(lbl, mask, bw, bh)

            opacity = el.get("opacity")
            if opacity is not None and float(opacity) < 1.0:
                lbl = g.opacity(lbl, float(opacity))

            if el_anim == "fade_in":
                lbl = g.fade_in(lbl, float(a.get("duration", 1.0)),
                                float(a.get("start_at", 0.0)))
            elif el_anim == "fade_zoom_in":
                # crossfadein(fade_duration) no MoviePy — o zoom já foi aplicado.
                lbl = g.fade_in(lbl, float(a.get("fade_duration", 0.6)),
                                float(a.get("start_at", 0.0)))

            cur = g.overlay(cur, lbl, bx, by)

        # --- legendas ---
        if ass_path and os.path.exists(ass_path):
            cur = g.subtitles(cur, ass_path, fontsdir)

        cur = g.to_yuv(cur)

        input_args, filter_complex, final = g.build_args(cur)

        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        cmd += input_args

        # O índice do áudio é o próximo após os inputs de vídeo já registrados.
        audio_idx = len(g.inputs)
        if audio_path and os.path.exists(audio_path):
            cmd += ["-i", audio_path]
        else:
            # Cena sem narração: trilha silenciosa, p/ o concat ficar consistente
            # (mesma garantia que _ensure_audio_stream dá no caminho MoviePy).
            cmd += ["-f", "lavfi", "-t", f"{duration:.3f}",
                    "-i", "anullsrc=r=44100:cl=stereo"]

        cmd += ["-filter_complex", filter_complex,
                "-map", f"[{final}]", "-map", f"{audio_idx}:a"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]

        cmd += [
            "-c:v", "libx264",
            "-preset", self.quality.get("preset", "ultrafast"),
            "-crf", str(self.quality.get("crf", 12)),
            "-pix_fmt", self.quality.get("pix_fmt", "yuv420p"),
            "-r", str(fps), "-vsync", "cfr", "-g", "60", "-bf", "2",
            "-t", f"{duration:.3f}",
            "-shortest", "-movflags", "+faststart",
            out_path,
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise Unsupported(f"ffmpeg falhou: {(e.stderr or '')[-800:]}") from e

        return out_path
