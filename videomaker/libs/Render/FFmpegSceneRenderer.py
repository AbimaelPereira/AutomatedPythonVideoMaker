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
_SUPPORTED_VISUAL_TYPES = {"image", "remote_asset", "color", "video", "directory"}


def _anim_type(element: dict) -> str:
    return (element.get("animation") or {}).get("type") or "none"


def _has_filters(d) -> bool:
    """True se o dict declara `filters` não-vazio. Tolera None/não-dict."""
    return bool(isinstance(d, dict) and d.get("filters"))


def _resolve_transitions(effective_gs: dict, scene: dict):
    """Config de transição efetiva — reusa o resolvedor do engine (import local
    para evitar ciclo, já que o engine importa este módulo)."""
    from libs.UnifiedVideoEngine import _resolve_scene_transitions
    return _resolve_scene_transitions(effective_gs, scene)


def _fade_params(trans: dict) -> tuple:
    """(fade_in, fade_out, cor) da transição fade, com os defaults do Fade.py."""
    visual = (trans or {}).get("visual") or {}
    fi = float(visual.get("fade_in_duration", 0.5))
    fo = float(visual.get("fade_out_duration", 0.5))
    color = visual.get("color", [0, 0, 0])
    if isinstance(color, str):
        hexv = color.lstrip("#")
        if len(hexv) == 6:
            color = [int(hexv[i:i + 2], 16) for i in (0, 2, 4)]
        else:
            color = [0, 0, 0]
    try:
        r, g, b = (int(c) for c in list(color)[:3])
    except Exception:
        r, g, b = 0, 0, 0
    return (fi, fo, f"0x{r:02x}{g:02x}{b:02x}")


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
        if bg_type not in ("color", "file", "remote_asset", "image", "ai",
                           "video", "directory", None):
            return (False, f"background.visual.type '{bg_type}' não suportado")

        # IA de vídeo continua no MoviePy (loop/subclip de clipe); imagem é
        # arquivo em disco e entra como qualquer outra.
        if bg_type == "ai" and bg.get("content_type", "image") != "image":
            return (False, "background ai content_type 'video' não suportado")

        # `contain` com cor sólida é `scale`+`pad` (ver FilterGraphBuilder.contain).
        # `contain-blur` compõe a própria imagem desfocada por trás — sem
        # equivalente fiel. Vídeo/pasta com contain: o MoviePy faz resize puro
        # (`_fit_video`), então também fica lá para não divergir.
        fit_mode = bg.get("fit_mode")
        if fit_mode == "contain-blur":
            return (False, "background fit_mode 'contain-blur' não suportado")
        if fit_mode == "contain" and bg_type in ("video", "directory"):
            return (False, f"background fit_mode 'contain' em type '{bg_type}' não suportado")

        # `focus` só tem efeito em crop de mídia; num fundo de cor sólida é
        # inócuo. "center" é o default; "face" é suportado (detecção 1x na
        # imagem, fora do loop de frames).
        if bg_type != "color" and bg.get("focus") not in (None, "center", "face"):
            return (False, f"background.focus '{bg.get('focus')}' não suportado")

        # Filtros visuais (light_leak, partículas…) não têm equivalente.
        # Precisa cobrir os MESMOS lugares que o BackgroundEngine mescla
        # (global/cena, raiz e dentro de `background`) — senão a cena vem pra
        # cá, o BackgroundEngine nunca roda e o filtro some silenciosamente.
        scene_bg = scene.get("background") if isinstance(scene.get("background"), dict) else {}
        if (_has_filters(effective_gs) or _has_filters(scene)
                or _has_filters(effective_gs.get("background"))
                or _has_filters(scene_bg)):
            return (False, "filters (overlay/modifier) não suportados")

        # Transições aqui são INTRA-cena (aplicadas ao clipe da própria cena),
        # não entre cenas. `fade` é mistura linear com uma cor → filtro `fade`.
        # `zoom` faz zoom + shake amortecido com física própria (amplitude,
        # frequência, decay) e não tem equivalente fiel.
        trans = _resolve_transitions(effective_gs, scene)
        if trans and trans.get("enabled"):
            t_type = (trans.get("type") or "zoom").lower()
            if t_type != "fade":
                return (False, f"transição '{t_type}' não suportada")
            if trans.get("audio"):
                return (False, "transição com áudio (sfx) não suportada")

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
            if _has_filters(el):
                return (False, f"visual_elements[{i}].filters não suportado")

        if subtitle_cfg and subtitle_cfg.get("enabled"):
            sub_type = (subtitle_cfg.get("type") or "classic").lower()
            if sub_type not in ("classic", "karaoke"):
                return (False, f"subtitle.type '{sub_type}' não suportado")
            # `shadow.blur` é suportado via camada de sombra separada — ver
            # AssBuilder._shadow_style_name.

        return (True, "")

    # ------------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------------

    @staticmethod
    def _build_segments(g, segments: list, duration: float,
                        size: tuple = None) -> str:
        """Materializa um plano do DirectorySelector como uma stream única.

        Cada segmento vira um input (imagem em loop ou trecho de vídeo),
        normalizado para tamanho/SAR/fps comuns, e todos são concatenados.
        Um único segmento dispensa o `concat`, mas ainda passa pela
        normalização — é ela que aplica o cover.

        `size` define o alvo do cover: a tela (fundo) ou a caixa do elemento
        (visual_element). Ausente = resolução de saída.
        """
        labels = []
        for seg in segments:
            seg_duration = float(seg.get("duration") or 0)
            if seg_duration <= 0:
                continue

            if seg.get("is_video"):
                src = g.background_video(
                    seg["path"], float(seg.get("start") or 0.0),
                    seg_duration, bool(seg.get("loop")),
                )
            else:
                src = g.background_image(seg["path"], seg_duration)

            labels.append(g.normalize_segment(src, seg_duration, size=size))

        if not labels:
            raise Unsupported("plano de diretório sem segmentos utilizáveis")
        return g.concat(labels)

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
        elif bg.get("_segments"):
            # Pasta (ou vídeo único): o plano de segmentos já vem resolvido pelo
            # DirectorySelector — mesmo plano que o caminho MoviePy usaria.
            if bg.get("fit_mode") == "contain":
                # remote_asset que resolveu para vídeo: o MoviePy faz resize puro.
                raise Unsupported("fit_mode 'contain' em fundo de vídeo")
            cur = self._build_segments(g, bg["_segments"], duration)
        else:
            path = bg.get("_path")
            if not path or not os.path.exists(path):
                raise Unsupported(f"fundo sem arquivo resolvido: {path}")
            cur = g.background_image(path, duration)
            if bg.get("_contain"):
                # fit_mode contain: imagem inteira, sobra em `fill_color`. O
                # tamanho nativo entra nas mesmas contas do _fit_image do MoviePy.
                from PIL import Image
                with Image.open(path) as im:
                    img_w, img_h = im.size
                cur = g.contain(cur, img_w, img_h, bg.get("fill_color", "#000000"))
                bg_crop = None
            elif bg.get("_stretch"):
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
            elif not bg.get("_contain"):
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
            elif el.get("_segments"):
                # Pasta/vídeo: os segmentos são concatenados no tamanho da CAIXA
                # do elemento (não da tela), e o resultado já sai recortado —
                # por isso não passa pelo resize/crop de imagem abaixo.
                lbl = self._build_segments(g, el["_segments"], duration,
                                           size=(bw, bh))
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

        # --- transição da cena ---
        # No MoviePy o TransitionEngine embrulha a cena JÁ COMPOSTA (fundo +
        # visuais + legenda), então o fade escurece tudo junto. Mesma ordem aqui.
        trans = _resolve_transitions(effective_gs, scene)
        if trans and trans.get("enabled") and (trans.get("type") or "").lower() == "fade":
            fi, fo, color = _fade_params(trans)
            cur = g.scene_fade(cur, duration, fi, fo, color)

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

        # A narração costuma ser mais curta que a cena (o JSON pode fixar
        # `duration` maior). O caminho MoviePy resolve isso com
        # `set_duration(scene_duration)` no composite: o vídeo manda e o áudio
        # simplesmente acaba antes. Aqui o equivalente é completar o áudio com
        # silêncio — sem isso, `-shortest` cortaria o VÍDEO no fim da narração.
        audio_filter = f"[{audio_idx}:a]apad,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[aout]"
        cmd += ["-filter_complex", f"{filter_complex};{audio_filter}",
                "-map", f"[{final}]", "-map", "[aout]"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]

        cmd += [
            "-c:v", "libx264",
            "-preset", self.quality.get("preset", "ultrafast"),
            "-crf", str(self.quality.get("crf", 12)),
            "-pix_fmt", self.quality.get("pix_fmt", "yuv420p"),
            "-r", str(fps), "-vsync", "cfr", "-g", "60", "-bf", "2",
            "-t", f"{duration:.3f}",
            "-movflags", "+faststart",
            out_path,
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise Unsupported(f"ffmpeg falhou: {(e.stderr or '')[-800:]}") from e

        return out_path
