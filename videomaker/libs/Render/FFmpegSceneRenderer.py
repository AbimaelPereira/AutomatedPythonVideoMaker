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


# Animações com equivalente fiel em filtro.
_SUPPORTED_ANIMATIONS = {"none", None, "zoom_in", "fade_in"}

# Tipos de elemento visual suportados.
_SUPPORTED_VISUAL_TYPES = {"image", "remote_asset"}


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
        if bg_type not in ("color", "file", "remote_asset", "image", None):
            return (False, f"background.visual.type '{bg_type}' não suportado")

        if bg.get("fit_mode") in ("contain-blur", "contain"):
            return (False, f"background fit_mode '{bg.get('fit_mode')}' não suportado")

        # `focus` só tem efeito em crop de mídia; num fundo de cor sólida é
        # inócuo. "center" é o default e também não muda nada.
        if bg_type != "color" and bg.get("focus") not in (None, "center"):
            return (False, f"background.focus '{bg.get('focus')}' não suportado (crop por detecção)")

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
            if el.get("focus") == "face":
                return (False, f"visual_elements[{i}].focus 'face' não suportado")

        if subtitle_cfg and subtitle_cfg.get("enabled"):
            sub_type = (subtitle_cfg.get("type") or "classic").lower()
            if sub_type not in ("classic", "karaoke"):
                return (False, f"subtitle.type '{sub_type}' não suportado")
            # Sombra borrada não existe em ASS.
            palette = subtitle_cfg.get("palette") or []
            for item in palette:
                shadow = item.get("shadow") or {}
                if float(shadow.get("blur", 0) or 0) > 0:
                    return (False, "subtitle com shadow.blur não é fiel em ASS")
            shadow = subtitle_cfg.get("shadow") or {}
            if float(shadow.get("blur", 0) or 0) > 0:
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
            path = el.get("_path")
            if not path or not os.path.exists(path):
                raise Unsupported("visual_element sem arquivo resolvido")

            box = el.get("_box")          # (x, y, w, h) já calculado pelo layout
            if not box:
                raise Unsupported("visual_element sem caixa de layout")
            bx, by, bw, bh = box

            idx = g.add_input(["-loop", "1", "-t", f"{duration:.3f}",
                               "-r", str(fps), "-i", path])
            lbl = g.scale_to(f"{idx}:v", bw, bh)

            el_anim = _anim_type(el)
            if el_anim == "zoom_in":
                a = el.get("animation") or {}
                lbl = g.zoom(lbl, float(a.get("start_scale", 1.0)),
                             float(a.get("end_scale", 1.1)), duration, bw, bh)

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
                a = el.get("animation") or {}
                lbl = g.fade_in(lbl, float(a.get("duration", 1.0)),
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
