import os
import json
import numpy as np
import random
from moviepy.editor import *
import subprocess
import shutil
import gc
import hashlib
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from types import SimpleNamespace

from libs.utils import deep_merge, load_channel_config, resolve_output_resolution, resolve_output_quality
from libs.VisualClip import VisualClip, force_rgb, apply_border_radius_clip, apply_animation_in_window, apply_visual_filters
from libs.Subtitle.SubtitleEngine import SubtitleEngine
from libs.MediaDownloader import MediaDownloader
from libs.LayoutEngine import LayoutEngine
from libs.YouTube import YouTube
from libs.TikTok import TikTok
from libs.Background.BackgroundEngine import BackgroundEngine
from libs.Audio.NarrationEngine import NarrationEngine
from libs.Transitions.TransitionEngine import TransitionEngine
from libs.RemoteAssetManager import RemoteAssetManager

try:
    from libs.AIProviders import ai_manager
    from libs.AIProviders.AICache import AICache
    AI_AVAILABLE = True
    print("[UVE] Sistema de IA carregado")
except ImportError as e:
    AI_AVAILABLE = False
    print(f"[UVE] Sistema de IA não disponível: {e}")

MAX_PARALLEL_SCENES_DEFAULT = int(os.getenv("MAX_PARALLEL_SCENES", 2))


def hex_to_rgb(hex_value):
    if not isinstance(hex_value, str):
        return hex_value
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i+2], 16) for i in (0, 2, 4))
        else:
            return (0, 0, 0)
    except ValueError:
        return (0, 0, 0)


def _probe_has_audio(video_path: str) -> bool:
    """Verifica via ffprobe se o arquivo de vídeo contém stream de áudio."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return bool(result.stdout.strip())
    except Exception:
        return False


def _probe_duration(video_path: str) -> float:
    """Retorna duração do vídeo em segundos via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def _add_silent_audio_track(video_path: str, output_path: str) -> str:
    """
    Adiciona uma faixa de áudio silenciosa a um vídeo que não tem stream de áudio.
    Isso garante que todos os clipes tenham streams consistentes para o FFmpeg concat.

    Args:
        video_path:  Caminho do vídeo sem áudio
        output_path: Caminho de saída com faixa silenciosa

    Returns:
        output_path se bem-sucedido, video_path como fallback
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-shortest",
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[UVE] ✅ Faixa de silêncio adicionada: {os.path.basename(output_path)}")
        return output_path
    except subprocess.CalledProcessError as e:
        stderr = e.stderr if isinstance(e.stderr, str) else e.stderr.decode(errors="replace")
        print(f"[UVE] ❌ Falha ao adicionar faixa silenciosa: {stderr}")
        return video_path


def _ensure_audio_stream(video_path: str, scene_dir: str, scene_id: str) -> str:
    """
    Garante que o vídeo tenha stream de áudio.
    Se não tiver, cria uma versão com faixa de silêncio e retorna o novo caminho.
    O arquivo original não é removido pois pode ser necessário para debug.

    Args:
        video_path: Caminho do vídeo renderizado
        scene_dir:  Diretório da cena (para salvar o arquivo com silêncio)
        scene_id:   ID da cena (para nomear o arquivo)

    Returns:
        Caminho do vídeo garantidamente com stream de áudio
    """
    if _probe_has_audio(video_path):
        return video_path

    print(f"[UVE] ⚠️  Cena '{scene_id}' sem áudio — adicionando faixa de silêncio...")
    silent_path = os.path.join(scene_dir, f"{scene_id}_silent_audio.mp4")
    result = _add_silent_audio_track(video_path, silent_path)

    if result != video_path and os.path.exists(result):
        return result

    # Fallback: retorna o original mesmo sem áudio (concat pode falhar, mas já logamos)
    print(f"[UVE] ⚠️  Não foi possível adicionar silêncio — usando vídeo original sem áudio")
    return video_path


def _resolve_scene_transitions(effective_gs: dict, scene: dict) -> dict | None:
    """
    Resolve a config de transição efetiva para uma cena.

    Prioridade: scene.transitions > effective_gs.transitions

    A cena pode:
      - Não ter "transitions" → usa o global (comportamento anterior)
      - Ter "transitions": {"enabled": false} → desativa mesmo que o global ative
      - Ter "transitions": {"enabled": true, ...} → ativa/sobrescreve parâmetros
    """
    gs_transitions = effective_gs.get("transitions")
    scene_transitions = scene.get("transitions")

    if scene_transitions is None:
        # Cena não define nada → respeita o global
        return gs_transitions

    if gs_transitions is None:
        # Global não define nada, mas cena define → usa cena
        return scene_transitions

    # Ambos definem → deep merge (cena vence em conflitos)
    return deep_merge(gs_transitions, scene_transitions)


def _resolve_scene_tts(effective_gs_tts: dict, scene: dict) -> dict:
    """
    Resolve a config de TTS efetiva para uma cena.

    Prioridade: scene.tts > effective_gs.tts
    """
    scene_tts = scene.get("tts", {})
    if not scene_tts:
        return effective_gs_tts
    return deep_merge(effective_gs_tts, scene_tts)


def _default_safe_paddings(resolution: tuple) -> dict:
    """Paddings padrão de "área segura" conforme a orientação da tela.

    Paddings significam apenas margem segura (a faixa onde visuais e legendas
    podem ser ancorados via `placement`). Verticais: 9:16 mantém os históricos
    (top 100 / bottom 850, calibrados para a legenda legada); 16:9 usa margens
    simétricas de ~5% por não ter zona de legenda dedicada.
    """
    w, h = resolution
    if w >= h:  # paisagem (16:9 etc.) — margens simétricas de ~5%
        return {
            "padding_side":   int(w * 0.05),   # 1920 → 96
            "padding_top":    int(h * 0.05),   # 1080 → 54
            "padding_bottom": int(h * 0.05),   # 1080 → 54
        }
    # retrato (9:16) — preserva os defaults históricos
    return {
        "padding_side":   50,
        "padding_top":    100,
        "padding_bottom": 850,
    }


def _resolve_scene_subtitle(base_subtitle_config: dict, effective_gs: dict, scene: dict) -> dict:
    """
    Resolve a config de legenda efetiva para uma cena.

    Prioridade: scene.subtitle > effective_gs.subtitle > base defaults
    """
    merged = deep_merge(base_subtitle_config, effective_gs.get("subtitle", {}))
    scene_subtitle = scene.get("subtitle", {})
    if scene_subtitle:
        merged = deep_merge(merged, scene_subtitle)
    return merged


def _subtitles_enabled(effective_gs: dict, scene: dict) -> bool:
    """
    Decide se a legenda deve ser renderizada para a cena.

    Controlado por `subtitle.enabled`, resolvido na cadeia canal < global < cena
    (mesmo merge de `_resolve_scene_subtitle`). Default: desligado.
    """
    merged = deep_merge(effective_gs.get("subtitle", {}), scene.get("subtitle", {}))
    return bool(merged.get("enabled", False))


def _resolve_scene_layout_params(layout_params: dict, scene: dict) -> dict:
    """Permite que uma cena sobrescreva os paddings (área segura) só para ela.

    Os `padding_top/bottom/side` da raiz do JSON viram o `layout_params` global
    (resolvido uma vez no __init__). Se a CENA declarar qualquer `padding_*`, ele
    vence apenas para essa cena — visuais e legenda usam a versão sobrescrita.
    Sem override na cena, retorna o `layout_params` original inalterado.
    """
    overrides = {k: scene[k] for k in ("padding_top", "padding_bottom", "padding_side")
                 if k in scene}
    if not overrides:
        return layout_params
    merged = dict(layout_params)
    merged.update(overrides)
    return merged


def _process_scene_worker(scene_data_bundle):
    """Worker isolado para processar uma cena em paralelo."""
    scene_index = scene_data_bundle["scene_index"]
    scene = scene_data_bundle["scene"]
    total_scenes = scene_data_bundle["total_scenes"]
    output_dir = scene_data_bundle["output_dir"]
    resolution_output = scene_data_bundle["resolution_output"]
    output_quality = scene_data_bundle["output_quality"]
    tts_config = scene_data_bundle["tts_config"]
    effective_gs = scene_data_bundle["effective_gs"]
    layout_params = scene_data_bundle["layout_params"]
    remote_assets_config = scene_data_bundle["remote_assets_config"]
    # A cena pode zerar/ajustar os paddings só para ela (visuais + legenda).
    layout_params = _resolve_scene_layout_params(layout_params, scene)
    ai_cache_dir = scene_data_bundle["ai_cache_dir"]

    try:
        scene_id = scene.get("id", f"cena_{scene_index}")
        print(f"\n[Worker-{scene_index}] Processando cena {scene_index + 1}/{total_scenes}: {scene_id}")

        scene_dir = os.path.join(output_dir, scene_id)
        os.makedirs(scene_dir, exist_ok=True)

        remote_asset_manager = RemoteAssetManager(config=remote_assets_config)

        if AI_AVAILABLE and ai_cache_dir:
            ai_cache = AICache(ai_cache_dir)
        else:
            ai_cache = None

        # 1. TTS — merge cena > global
        scene_tts_config = _resolve_scene_tts(tts_config, scene)

        # 2. Narração
        narration_engine = NarrationEngine(scene_tts_config, output_dir)
        narration_clip, duration_from_tts, subtitle_file = narration_engine.process_scene_narration(scene, scene_dir)

        if narration_clip is None:
            print(f"[Worker-{scene_index}] ⚠️ Narração não gerada para cena '{scene_id}'")
        else:
            print(f"[Worker-{scene_index}] ✅ Narração gerada: {duration_from_tts:.2f}s")

        # 3. Duração
        scene_duration = scene.get("duration", duration_from_tts)
        if not scene_duration or scene_duration < 0.1:
            scene_duration = 4.0
            print(f"[Worker-{scene_index}] Usando duração padrão: {scene_duration}s")
        else:
            print(f"[Worker-{scene_index}] Duração da cena: {scene_duration}s")

        # 4. Componentes
        bg_engine = BackgroundEngine(
            resolution_output=resolution_output,
            dir_clips_cache={},
            ai_cache=ai_cache,
            remote_asset_manager=remote_asset_manager,
        )
        background_clip = bg_engine.build_scene_background(
            effective_gs, scene, float(scene_duration), scene_dir, output_dir
        )

        visual_clip = _create_visual_elements_clip_worker(
            scene, scene_duration, scene_dir, resolution_output,
            remote_asset_manager, layout_params
        )

        subtitle_clip = None
        if _subtitles_enabled(effective_gs, scene):
            subtitle_clip = _create_subtitle_clip_worker(
                scene_duration, subtitle_file, layout_params,
                resolution_output, effective_gs, scene_data=scene
            )

        # 5. Composição
        final_scene_clip = [background_clip]
        if visual_clip:
            final_scene_clip.append(visual_clip)
        if subtitle_clip:
            final_scene_clip.append(subtitle_clip)

        # 6. force_rgb
        safe_clips = []
        for c in final_scene_clip:
            try:
                c = c.fl_image(force_rgb)
                safe_clips.append(c)
            except Exception as e:
                print(f"[Worker-{scene_index}] Falha ao aplicar force_rgb: {e}")
                safe_clips.append(c)

        # 7. Compor cena final
        composed_clip = CompositeVideoClip(safe_clips, size=resolution_output).set_duration(scene_duration)
        composed_clip = composed_clip.fl_image(force_rgb)

        # 8. Narração
        if narration_clip:
            composed_clip = composed_clip.set_audio(narration_clip)
        else:
            print(f"[Worker-{scene_index}] ⚠️ Cena '{scene_id}' sem narração — será renderizada com silêncio")

        # 9. Transições — merge cena > global (FIX: respeita scene.transitions.enabled: false)
        transitions_config = _resolve_scene_transitions(effective_gs, scene)
        if transitions_config and transitions_config.get("enabled", False):
            print(f"[Worker-{scene_index}] Aplicando transição...")
            try:
                transition_engine = TransitionEngine({
                    "clip": composed_clip,
                    "transitions_settings": transitions_config,
                    "resolution": resolution_output
                })
                composed_clip = transition_engine.apply_transition()
                print(f"[Worker-{scene_index}] Transição aplicada")
            except Exception as e:
                print(f"[Worker-{scene_index}] Falha ao aplicar transição: {e}")
        else:
            print(f"[Worker-{scene_index}] Transições desabilitadas para esta cena")

        # 10. Renderizar cena
        scene_clip_path = os.path.join(scene_dir, f"{scene_id}.mp4")
        temp_audiofile = os.path.join(scene_dir, f"{scene_id}.m4a")

        print(f"[Worker-{scene_index}] Renderizando cena {scene_index + 1}/{total_scenes}...")

        composed_clip.write_videofile(
            scene_clip_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=temp_audiofile,
            remove_temp=True,
            fps=output_quality["fps"],
            preset=output_quality["preset"],
            threads=4,
            verbose=False,
            logger=None,
            ffmpeg_params=['-crf', str(output_quality["crf"]), '-pix_fmt', output_quality["pix_fmt"],
                           '-vsync', 'cfr', '-g', '60', '-bf', '2']
        )

        print(f"[Worker-{scene_index}] Cena renderizada: {os.path.basename(scene_clip_path)}")

        # 11. FIX: Garante stream de áudio para concatenação consistente
        scene_clip_path = _ensure_audio_stream(scene_clip_path, scene_dir, scene_id)

        try:
            composed_clip.close()
            if narration_clip:
                narration_clip.close()
        except:
            pass

        del composed_clip
        gc.collect()

        return (scene_index, scene_clip_path)

    except Exception as e:
        print(f"[Worker-{scene_index}] Erro ao processar cena: {e}")
        import traceback
        traceback.print_exc()
        return (scene_index, None)


def _create_visual_elements_clip_worker(scene_data, scene_duration, scene_dir,
                                        resolution_output, remote_asset_manager, layout_params):
    """Versão worker de _create_visual_elements_clip."""
    elements = scene_data.get("visual_elements", [])
    if not elements:
        return None

    print(f"[Worker] Processando {len(elements)} elementos visuais...")

    valid_clips_info = []
    valid_element_data_for_layout = []

    for i, element_data in enumerate(elements):
        try:
            config = {
                "element_data": element_data,
                "resolution_output": resolution_output,
                "temp_dir": scene_dir,
                "duration": scene_duration,
                "remote_asset_manager": remote_asset_manager,
            }

            processor = VisualClip(config)
            raw_clip = processor.generate()

            if raw_clip:
                w, h = raw_clip.size
                element_data_copy = element_data.copy()
                element_data_copy['original_size'] = (w, h)
                valid_clips_info.append(raw_clip)
                valid_element_data_for_layout.append(element_data_copy)

        except Exception as e:
            print(f"[Worker] Erro no elemento {i + 1}: {e}")

    if not valid_clips_info:
        return None

    layout_config = SimpleNamespace(**layout_params)

    try:
        layout_results = LayoutEngine.process_stack_layout(valid_element_data_for_layout, layout_config)

        final_clips = []
        for i, clip in enumerate(valid_clips_info):
            if i >= len(layout_results):
                break
            layout = layout_results[i]
            try:
                resize_to = layout.get('_resize_to') or layout['final_size']
                clip_resized = clip.resize(newsize=resize_to)
                # Cover crop centralizado (horizontal e/ou vertical)
                crop_h = layout.get('crop_height')
                crop_w = layout.get('crop_width')
                if crop_h and crop_h < clip_resized.h:
                    y1 = (clip_resized.h - crop_h) // 2
                    clip_resized = clip_resized.crop(y1=y1, y2=y1 + crop_h)
                if crop_w and crop_w < clip_resized.w:
                    x1 = (clip_resized.w - crop_w) // 2
                    clip_resized = clip_resized.crop(x1=x1, x2=x1 + crop_w)
                # Ordem no modo cover: animation (janela fixa) → border_radius
                deferred_anim = layout.get('deferred_animation')
                if deferred_anim:
                    clip_resized = apply_animation_in_window(clip_resized, deferred_anim)
                border_radius = layout.get('border_radius', 0)
                if border_radius and border_radius > 0:
                    clip_resized = apply_border_radius_clip(clip_resized, int(border_radius))
                clip_resized = apply_visual_filters(
                    clip_resized, valid_element_data_for_layout[i].get('filters'))
                clip_positioned = clip_resized.set_position(layout['final_position'])
                final_clips.append(clip_positioned)
            except Exception as e:
                print(f"[Worker] Falha ao posicionar elemento {i + 1}: {e}")

        if not final_clips:
            return None

        return CompositeVideoClip(final_clips, size=resolution_output).set_duration(
            scene_duration).fl_image(force_rgb)

    except Exception as e:
        print(f"[Worker] Falha no LayoutEngine: {e}")
        centered_clips = []
        for clip in valid_clips_info:
            try:
                centered_clips.append(clip.set_position('center'))
            except:
                pass

        if centered_clips:
            return CompositeVideoClip(centered_clips, size=resolution_output).set_duration(
                scene_duration).fl_image(force_rgb)

        return None


def _create_subtitle_clip_worker(scene_duration, subtitle_file, layout_params,
                                 resolution_output, effective_gs, scene_data=None):
    """Versão worker de _create_subtitle_clip."""
    try:
        if not subtitle_file or not os.path.exists(subtitle_file):
            return None

        base_subtitle_config = {
            "subtitle_narration_file": subtitle_file,
            "resolution_output": resolution_output,
            "padding_bottom": layout_params.get('padding_bottom', 200),
            "padding_side":   layout_params.get('padding_side', 50),
            "padding_top":    layout_params.get('padding_top', 200),
            "has_visual_elements": True,
        }

        # FIX: merge correto — base < global < cena
        subtitle_config = _resolve_scene_subtitle(base_subtitle_config, effective_gs, scene_data or {})

        subtitle_generator = SubtitleEngine(params=subtitle_config)
        subtitle_clip = subtitle_generator.generate()

        if subtitle_clip:
            subtitle_clip = subtitle_clip.set_duration(scene_duration)
            return subtitle_clip

        return None

    except Exception as e:
        print(f"[Worker] Falha ao criar legendas: {e}")
        return None


class UnifiedVideoEngine:
    VALID_AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]

    def __init__(self, video_data: dict):
        self.video_data = video_data

        self.video_data["debug"] = os.getenv("DEBUG", "0").lower() in ("true", "1", "t")

        # 1. Carrega channel_config e faz merge de global_settings
        channel_name = video_data.get("channel_name")
        channel_config = load_channel_config(channel_name) if channel_name else {}

        channel_gs = channel_config.get("global_settings", {})
        video_gs   = video_data.get("global_settings", {})
        self.global_settings = deep_merge(channel_gs, video_gs)

        # 2. Merge youtube
        self.youtube_config = deep_merge(
            channel_config.get("youtube", {}),
            video_data.get("youtube", {})
        )

        # 3. Resolução + qualidade
        # Novo formato: objeto raiz "output" = {"ratio": ..., "quality": ...}.
        # Retrocompat: "output_ratio" solto na raiz ainda funciona.
        output_cfg = video_data.get("output", {}) or {}
        output_ratio = output_cfg.get("ratio") or video_data.get("output_ratio", "9:16")
        self.resolution_output = resolve_output_resolution(output_ratio)
        self.output_quality = resolve_output_quality(output_cfg.get("quality"))

        # 4. tts_config
        self.tts_config = self.global_settings.get("tts", {})

        # 5. Layout params
        # Defaults de área segura dependem da orientação (9:16 mantém históricos,
        # 16:9 usa margens simétricas). global_settings/env sobrescrevem.
        pad_defaults = _default_safe_paddings(self.resolution_output)
        self.layout_params = {
            "width":             self.resolution_output[0],
            "height":            self.resolution_output[1],
            "padding_bottom":    self.global_settings.get("padding_bottom", int(os.getenv("PADDING_BOTTOM", pad_defaults["padding_bottom"]))),
            "padding_top":       self.global_settings.get("padding_top",    int(os.getenv("PADDING_TOP", pad_defaults["padding_top"]))),
            "padding_side":      self.global_settings.get("padding_side",   int(os.getenv("PADDING_SIDE", pad_defaults["padding_side"]))),
            "stack_gap_percent": self.global_settings.get("stack_gap_percent", float(os.getenv("STACK_GAP_PERCENT", 0.02))),
        }
        self.layout_config = SimpleNamespace(**self.layout_params)

        # 6. Caches e outros
        self.dir_media_index = {}
        self.max_parallel_scenes = int(os.getenv("MAX_PARALLEL_SCENES", MAX_PARALLEL_SCENES_DEFAULT))

        if AI_AVAILABLE:
            cache_dir = os.path.join(os.getcwd(), "cache", "ai_generated")
            self.ai_cache = AICache(cache_dir)
            self.ai_cache_dir = cache_dir
        else:
            self.ai_cache = None
            self.ai_cache_dir = None

        print("[UVE] Inicializando Remote Asset Manager...")
        remote_assets_config = self.global_settings.get("remote_assets", {})
        self.remote_asset_manager = RemoteAssetManager(config=remote_assets_config)
        self.remote_assets_config = remote_assets_config
        print("[UVE] Remote Asset Manager inicializado")

        stats = self.remote_asset_manager.get_stats()
        if stats["total_slugs"] > 0:
            print(f"[UVE] Remote Assets: {stats['total_slugs']} slugs, {stats['valid_media']} URLs válidas")

        slug = video_data.get("slug", "video_sem_slug")
        base_output_dir = os.path.join(os.getcwd(), "output")
        self.output_dir = os.path.join(base_output_dir, slug)
        os.makedirs(self.output_dir, exist_ok=True)

        self.final_clips = []
        self.total_duration = 0.0

    # ------------------------------------------------------------------
    # CHAPTERS / NORMALIZAÇÃO
    # ------------------------------------------------------------------

    def _normalize_scenes(self) -> list:
        self.scene_chapter_map = {}
        self.chapter_audio_map = {}

        video_data = self.video_data

        if "scenes" in video_data and "chapters" not in video_data:
            scenes = video_data["scenes"]
            for scene in scenes:
                scene["_chapter_gs"] = {}
                scene_id = scene.get("id", "")
                self.scene_chapter_map[scene_id] = "__root__"
            self.chapter_audio_map["__root__"] = (
                self.global_settings.get("background", {}).get("audio", {})
            )
            return scenes

        if "chapters" in video_data:
            flat_scenes = []
            for chapter in video_data["chapters"]:
                chapter_id = chapter.get("id", f"chapter_{len(self.chapter_audio_map)}")
                chapter_gs = chapter.get("global_settings", {})
                chapter_audio = deep_merge(
                    self.global_settings.get("background", {}).get("audio", {}),
                    chapter_gs.get("background", {}).get("audio", {})
                )
                self.chapter_audio_map[chapter_id] = chapter_audio

                for scene in chapter.get("scenes", []):
                    scene = dict(scene)
                    scene["_chapter_gs"] = chapter_gs
                    scene_id = scene.get("id", "")
                    self.scene_chapter_map[scene_id] = chapter_id
                    flat_scenes.append(scene)
            return flat_scenes

        return []

    def _resolve_scene_gs(self, scene: dict) -> dict:
        chapter_gs = scene.pop("_chapter_gs", {})
        return deep_merge(self.global_settings, chapter_gs)

    # ------------------------------------------------------------------
    # VISUAL ELEMENTS
    # ------------------------------------------------------------------

    def _create_visual_elements_clip(self, scene_data, scene_duration, scene_dir, layout_config=None):
        layout_config = layout_config or self.layout_config
        elements = scene_data.get("visual_elements", [])
        if not elements:
            return None

        print(f"[UVE] Processando {len(elements)} elementos visuais...")

        valid_clips_info = []
        valid_element_data_for_layout = []

        for i, element_data in enumerate(elements):
            try:
                config = {
                    "element_data": element_data,
                    "resolution_output": self.resolution_output,
                    "temp_dir": scene_dir,
                    "duration": scene_duration,
                    "remote_asset_manager": self.remote_asset_manager,
                }

                processor = VisualClip(config)
                raw_clip = processor.generate()

                if raw_clip:
                    w, h = raw_clip.size
                    element_data_copy = element_data.copy()
                    element_data_copy['original_size'] = (w, h)
                    valid_clips_info.append(raw_clip)
                    valid_element_data_for_layout.append(element_data_copy)
                    print(f"[UVE] Elemento {i + 1} gerado: {w}x{h}")
                else:
                    print(f"[UVE] Falha ao gerar elemento {i + 1}")

            except Exception as e:
                print(f"[UVE] Erro no elemento {i + 1}: {e}")

        if not valid_clips_info:
            print("[UVE] Nenhum elemento visual gerado com sucesso")
            return None

        try:
            layout_results = LayoutEngine.process_stack_layout(
                valid_element_data_for_layout, layout_config
            )

            final_clips = []
            for i, clip in enumerate(valid_clips_info):
                if i >= len(layout_results):
                    break
                layout = layout_results[i]
                try:
                    resize_to = layout.get('_resize_to') or layout['final_size']
                    clip_resized = clip.resize(newsize=resize_to)
                    # Cover crop centralizado (horizontal e/ou vertical)
                    crop_h = layout.get('crop_height')
                    crop_w = layout.get('crop_width')
                    if crop_h and crop_h < clip_resized.h:
                        y1 = (clip_resized.h - crop_h) // 2
                        clip_resized = clip_resized.crop(y1=y1, y2=y1 + crop_h)
                    if crop_w and crop_w < clip_resized.w:
                        x1 = (clip_resized.w - crop_w) // 2
                        clip_resized = clip_resized.crop(x1=x1, x2=x1 + crop_w)
                    # Ordem no modo cover: animation (janela fixa) → border_radius
                    deferred_anim = layout.get('deferred_animation')
                    if deferred_anim:
                        clip_resized = apply_animation_in_window(clip_resized, deferred_anim)
                    border_radius = layout.get('border_radius', 0)
                    if border_radius and border_radius > 0:
                        clip_resized = apply_border_radius_clip(clip_resized, int(border_radius))
                    clip_resized = apply_visual_filters(
                        clip_resized, valid_element_data_for_layout[i].get('filters'))
                    clip_positioned = clip_resized.set_position(layout['final_position'])
                    final_clips.append(clip_positioned)
                    print(f"[UVE] Elemento {i + 1} posicionado: {layout['final_size']} @ {layout['final_position']}")
                except Exception as e:
                    print(f"[UVE] Falha ao posicionar elemento {i + 1}: {e}")

            if not final_clips:
                print("[UVE] Nenhum elemento posicionado corretamente")
                return None

            return CompositeVideoClip(final_clips, size=self.resolution_output).set_duration(
                scene_duration).fl_image(force_rgb)

        except Exception as e:
            print(f"[UVE] Falha no LayoutEngine: {e}")
            print("[UVE] Usando posicionamento centralizado como fallback")

            centered_clips = []
            for clip in valid_clips_info:
                try:
                    centered_clips.append(clip.set_position('center'))
                except Exception as e:
                    print(f"[UVE] Falha no fallback: {e}")

            if centered_clips:
                return CompositeVideoClip(centered_clips, size=self.resolution_output).set_duration(
                    scene_duration).fl_image(force_rgb)

            return None

    def _create_subtitle_clip(self, scene_duration, subtitle_file, effective_gs,
                               has_visual_elements=False, scene_data=None, layout_params=None):
        try:
            layout_params = layout_params or self.layout_params
            if not subtitle_file or not os.path.exists(subtitle_file):
                print("[UVE] Arquivo de legenda não encontrado")
                return None

            print(f"[UVE] Gerando legendas do arquivo: {subtitle_file}")

            base_subtitle_config = {
                "subtitle_narration_file": subtitle_file,
                "resolution_output": self.resolution_output,
                "padding_bottom": layout_params.get('padding_bottom', 200),
                "padding_side":   layout_params.get('padding_side', 50),
                "padding_top":    layout_params.get('padding_top', 200),
                "has_visual_elements": True,
            }

            # FIX: merge correto — base < global < cena
            subtitle_config = _resolve_scene_subtitle(base_subtitle_config, effective_gs, scene_data or {})

            subtitle_generator = SubtitleEngine(params=subtitle_config)
            subtitle_clip = subtitle_generator.generate()

            if subtitle_clip:
                subtitle_clip = subtitle_clip.set_duration(scene_duration)
                print("[UVE] Legendas geradas com sucesso")
                return subtitle_clip
            else:
                print("[UVE] Falha na geração das legendas")
                return None

        except Exception as e:
            print(f"[UVE] Falha ao criar legendas: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ------------------------------------------------------------------
    # BACKGROUND AUDIO
    # ------------------------------------------------------------------

    def _has_per_chapter_audio(self) -> bool:
        if not hasattr(self, 'chapter_audio_map'):
            return False
        root_audio = self.chapter_audio_map.get("__root__", {})
        for ch_id, audio_cfg in self.chapter_audio_map.items():
            if ch_id == "__root__":
                continue
            if audio_cfg != root_audio and audio_cfg.get("source"):
                return True
        return False

    def _apply_background_audio_to_video(self, video_path: str, output_path: str,
                                          audio_config: dict = None) -> str:
        """
        Aplica áudio de fundo ao vídeo.
        audio_config: se None, usa self.global_settings.background.audio
        """
        bg_audio_config = audio_config if audio_config is not None else \
            self.global_settings.get("background", {}).get("audio", {})

        if not bg_audio_config:
            print("[UVE] Sem configuração de áudio de fundo")
            return video_path

        audio_type = bg_audio_config.get("type", "file")
        source     = bg_audio_config.get("source")
        volume     = bg_audio_config.get("volume", 0.2)

        if not source:
            print("[UVE] Áudio de fundo sem source configurado")
            return video_path

        try:
            if audio_type == "directory":
                if not os.path.isdir(source):
                    print(f"[UVE] Diretório de áudio não encontrado: {source}")
                    return video_path

                valid_extensions = ('.mp3', '.wav', '.ogg', '.m4a')
                audio_files = [
                    f for f in os.listdir(source)
                    if f.lower().endswith(valid_extensions)
                ]
                if not audio_files:
                    print(f"[UVE] Nenhum arquivo de áudio válido em: {source}")
                    return video_path

                audio_path = os.path.join(source, random.choice(audio_files))
            else:
                audio_path = source

            if not audio_path or not os.path.exists(audio_path):
                print(f"[UVE] Áudio de fundo não encontrado: {audio_path}")
                return video_path

            ducking_config  = bg_audio_config.get("ducking", {})
            ducking_enabled = ducking_config.get("enabled", False)

            if ducking_enabled:
                print("[UVE] Ducking habilitado — processando via AudioEffects...")
                return self._apply_background_audio_with_ducking(
                    video_path=video_path,
                    output_path=output_path,
                    audio_path=audio_path,
                    volume=volume,
                    ducking_config=ducking_config,
                )
            else:
                print(f"[UVE] Aplicando áudio de fundo sem ducking: {os.path.basename(audio_path)}")
                return self._apply_background_audio_simple(
                    video_path=video_path,
                    output_path=output_path,
                    audio_path=audio_path,
                    volume=volume,
                )

        except Exception as e:
            print(f"[UVE] Erro ao aplicar áudio de fundo: {e}")
            import traceback
            traceback.print_exc()
            return video_path

    def _apply_background_audio_with_ducking(self, video_path, output_path, audio_path, volume, ducking_config):
        from pydub import AudioSegment
        from libs.Audio.AudioEffects import AudioEffects

        temp_narration = os.path.join(self.output_dir, "_temp_narration_for_ducking.mp3")
        temp_mixed     = os.path.join(self.output_dir, "_temp_ducked_mix.mp3")

        try:
            # 1. Duração do vídeo
            video_duration_s  = _probe_duration(video_path)
            video_duration_ms = int(video_duration_s * 1000)
            print(f"[UVE] Duração do vídeo: {video_duration_s:.2f}s")

            # 2. Verifica se há stream de áudio no vídeo
            has_audio = _probe_has_audio(video_path)

            if not has_audio:
                print("[UVE] ⚠️ Vídeo sem stream de áudio (narração ausente).")
                print("[UVE]    Aplicando música de fundo em volume cheio (ducking ignorado)...")
                return self._apply_background_audio_simple(
                    video_path=video_path,
                    output_path=output_path,
                    audio_path=audio_path,
                    volume=volume,
                )

            # 3. Extrai narração do vídeo para calcular ducking
            cmd_extract = [
                "ffmpeg", "-y", "-i", video_path, "-vn",
                "-acodec", "libmp3lame", "-b:a", "192k",
                "-ar", "44100", "-ac", "2", temp_narration
            ]
            subprocess.run(cmd_extract, check=True, capture_output=True)
            print("[UVE] Narração extraída")

            # 4. Carrega e prepara os segmentos de áudio
            narration_seg  = AudioSegment.from_file(temp_narration)
            background_seg = AudioSegment.from_file(audio_path)

            if len(background_seg) < video_duration_ms:
                loops_needed   = (video_duration_ms // len(background_seg)) + 1
                background_seg = background_seg * loops_needed

            background_seg = background_seg[:video_duration_ms]

            if volume != 1.0:
                import math
                volume_db      = 20 * math.log10(max(volume, 1e-6))
                background_seg = background_seg.apply_gain(volume_db)

            # 5. Aplica ducking
            duck_params = {
                "ducking_db":   ducking_config.get("ducking_db",   -18.0),
                "threshold_db": ducking_config.get("threshold_db", -40.0),
                "attack_ms":    ducking_config.get("attack_ms",      50),
                "release_ms":   ducking_config.get("release_ms",    300),
                "chunk_ms":     ducking_config.get("chunk_ms",       10),
            }

            mixed_seg = AudioEffects.apply_ducking(
                narration=narration_seg, background=background_seg, **duck_params
            )

            mixed_seg = mixed_seg[:video_duration_ms]
            mixed_seg.export(temp_mixed, format="mp3", bitrate="192k")

            # 6. Mescla áudio processado de volta ao vídeo
            cmd_merge = [
                "ffmpeg", "-y",
                "-i", video_path, "-i", temp_mixed,
                "-map", "0:v:0", "-map", "1:a:0",
                *self._ffmpeg_video_args(),
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-shortest", "-movflags", "+faststart",
                output_path
            ]
            subprocess.run(cmd_merge, check=True, capture_output=True)
            print(f"[UVE] Vídeo final com ducking: {os.path.basename(output_path)}")

            return output_path

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace") if e.stderr else "N/A"
            print(f"[UVE] Erro FFmpeg no ducking:\n{stderr}")
            print("[UVE] Tentando fallback: aplicar música de fundo sem ducking...")
            try:
                return self._apply_background_audio_simple(
                    video_path=video_path,
                    output_path=output_path,
                    audio_path=audio_path,
                    volume=volume,
                )
            except Exception as fallback_e:
                print(f"[UVE] Fallback também falhou: {fallback_e}")
                return video_path
        except Exception as e:
            print(f"[UVE] Erro inesperado no ducking: {e}")
            import traceback
            traceback.print_exc()
            return video_path
        finally:
            for tmp in [temp_narration, temp_mixed]:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

    def _apply_background_audio_simple(self, video_path, output_path, audio_path, volume):
        video_clip = VideoFileClip(video_path)
        video_duration = video_clip.duration

        bg_audio = AudioFileClip(audio_path)

        if bg_audio.duration < video_duration:
            loops_needed = int(video_duration / bg_audio.duration) + 1
            bg_audio = concatenate_audioclips([bg_audio] * loops_needed)

        bg_audio = bg_audio.subclip(0, video_duration)
        bg_audio = bg_audio.volumex(volume)

        if video_clip.audio:
            final_audio = CompositeAudioClip([video_clip.audio, bg_audio])
        else:
            final_audio = bg_audio

        final_video = video_clip.set_audio(final_audio)

        print(f"[UVE] Renderizando vídeo com áudio de fundo...")

        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=self.output_quality["fps"],
            preset=self.output_quality["preset"],
            threads=4,
            verbose=False,
            logger=None,
            ffmpeg_params=['-crf', str(self.output_quality["crf"]), '-pix_fmt', self.output_quality["pix_fmt"],
                           '-vsync', 'cfr']
        )

        video_clip.close()
        bg_audio.close()
        final_video.close()

        print(f"[UVE] Áudio de fundo aplicado: {os.path.basename(output_path)}")
        return output_path

    def _ffmpeg_video_args(self):
        """Args de encoding de vídeo (x264) derivados de self.output_quality,
        usados nos re-encodes de concatenação via ffmpeg."""
        q = self.output_quality
        return [
            "-c:v", "libx264", "-preset", q["preset"], "-crf", str(q["crf"]),
            "-r", str(q["fps"]), "-vsync", "cfr", "-g", "60", "-bf", "2",
            "-pix_fmt", q["pix_fmt"],
        ]

    # ------------------------------------------------------------------
    # RENDER SCENE
    # ------------------------------------------------------------------

    def _render_scene(self, scene_index, scene_id, total_scenes, composed_clip, narration_clip, scene_dir):
        scene_clip_path = os.path.join(scene_dir, f"{scene_id}.mp4")
        temp_audiofile = os.path.join(scene_dir, f"{scene_id}.m4a")

        print(f"[UVE] Renderizando cena {scene_index + 1}/{total_scenes}...")

        composed_clip.write_videofile(
            scene_clip_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=temp_audiofile,
            remove_temp=True,
            fps=self.output_quality["fps"],
            preset=self.output_quality["preset"],
            threads=4,
            verbose=False,
            logger=None,
            ffmpeg_params=['-crf', str(self.output_quality["crf"]), '-pix_fmt', self.output_quality["pix_fmt"],
                           '-vsync', 'cfr', '-g', '60', '-bf', '2']
        )

        print(f"[UVE] Cena {scene_index + 1} renderizada: {os.path.basename(scene_clip_path)}")

        # FIX: Garante stream de áudio para concatenação consistente
        scene_clip_path = _ensure_audio_stream(scene_clip_path, scene_dir, scene_id)

        try:
            composed_clip.close()
            if narration_clip:
                narration_clip.close()
        except:
            pass

        del composed_clip
        gc.collect()

        return scene_clip_path

    # ------------------------------------------------------------------
    # CONCATENAÇÃO POR CHAPTER
    # ------------------------------------------------------------------

    def _concat_and_apply_chapter_audio(self, scene_files: list, slug: str) -> str:
        chapter_groups = {}
        chapter_order  = []

        for path in scene_files:
            scene_id = os.path.basename(os.path.dirname(path))
            chapter_id = self.scene_chapter_map.get(scene_id, "__root__")
            if chapter_id not in chapter_groups:
                chapter_groups[chapter_id] = []
                chapter_order.append(chapter_id)
            chapter_groups[chapter_id].append(path)

        segment_paths = []

        for chapter_id in chapter_order:
            paths = chapter_groups[chapter_id]
            audio_cfg = self.chapter_audio_map.get(chapter_id, {})

            segment_concat = os.path.join(self.output_dir, f"_segment_{chapter_id}_concat.mp4")
            segment_final  = os.path.join(self.output_dir, f"_segment_{chapter_id}_final.mp4")

            concat_list = os.path.join(self.output_dir, f"_concat_{chapter_id}.txt")
            with open(concat_list, "w", encoding="utf-8") as f:
                for p in paths:
                    f.write(f"file '{os.path.abspath(p)}'\n")

            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_list,
                *self._ffmpeg_video_args(),
                "-keyint_min", "60", "-sc_threshold", "0",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-movflags", "+faststart",
                segment_concat
            ]
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)

            if audio_cfg and audio_cfg.get("source"):
                result = self._apply_background_audio_to_video(segment_concat, segment_final, audio_cfg)
                segment_paths.append(result)
                if result != segment_final and os.path.exists(segment_concat):
                    os.remove(segment_concat)
            else:
                os.rename(segment_concat, segment_final)
                segment_paths.append(segment_final)

        final_path = os.path.join(self.output_dir, f"{slug}.mp4")
        if len(segment_paths) == 1:
            os.rename(segment_paths[0], final_path)
            return final_path

        concat_final_list = os.path.join(self.output_dir, "_concat_final.txt")
        with open(concat_final_list, "w", encoding="utf-8") as f:
            for p in segment_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        ffmpeg_final = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_final_list,
            *self._ffmpeg_video_args(),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            final_path
        ]
        subprocess.run(ffmpeg_final, check=True, capture_output=True, text=True)

        for p in segment_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        return final_path

    # ------------------------------------------------------------------
    # VIDEO RECORD
    # ------------------------------------------------------------------

    def _save_video_record(self, youtube_id: str, thumbnail_path: str | None, scenes: list):
        """Salva o registro do vídeo chamando a API via HTTP."""
        try:
            import requests

            api_url = os.getenv("API_URL", "http://localhost:8000")

            transcript = "\n".join(
                scene.get("narration", {}).get("text", "")
                for scene in scenes
                if scene.get("narration", {}).get("text")
            ) or None

            yt = self.youtube_config
            tags = yt.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]

            payload = {
                "youtube_id": youtube_id,
                "title": yt.get("title", ""),
                "description": yt.get("description"),
                "tags": tags,
                "category_id": str(yt.get("category_id", "")) or None,
                "slug": self.video_data.get("slug"),
                "channel_slug": self.video_data.get("channel_name"),
                "privacy_status": yt.get("privacy_status"),
                "thumbnail_path": thumbnail_path,
                "transcript": transcript,
            }

            response = requests.post(f"{api_url}/videos/", json=payload, timeout=10)
            response.raise_for_status()
            video = response.json()
            print(f"[UVE] Registro do vídeo salvo no banco (id={video['id']}, youtube_id={youtube_id})")
        except Exception as e:
            print(f"[UVE] Aviso: falha ao salvar registro do vídeo no banco: {e}")

    # ------------------------------------------------------------------
    # RUN
    # ------------------------------------------------------------------

    def _resolve_visual_elements_ai_sources(self, scenes: list) -> None:
        """Pré-resolve sources de IA em visual_elements antes do pool de workers.
        Substitui cada source com type=ai por um path de arquivo local.
        Modifica as cenas in-place.
        """
        if not AI_AVAILABLE:
            return

        from libs.AIProviders.PollinationsProvider import PollinationsProvider
        provider = PollinationsProvider()

        for scene in scenes:
            elements = scene.get("visual_elements", [])
            for element in elements:
                source = element.get("source")
                if not isinstance(source, dict) or source.get("type") != "ai":
                    continue

                prompt = source.get("prompt", "")
                if not prompt:
                    print(f"[UVE] visual_element ai source sem prompt — ignorado")
                    continue

                model = source.get("model", "flux")
                width = source.get("width", 576)
                height = source.get("height", 1024)
                scene_id = scene.get("id", "scene")

                print(f"[UVE] Gerando imagem IA para visual_element da cena '{scene_id}' (model={model})...")

                result = provider.generate_image(
                    prompt=prompt,
                    model=model,
                    width=width,
                    height=height,
                )

                if not result.get("success"):
                    print(f"[UVE] Falha ao gerar imagem IA para visual_element da cena '{scene_id}': {result.get('error')}")
                    continue

                ai_assets_dir = os.path.join(self.output_dir, "ai_assets")
                os.makedirs(ai_assets_dir, exist_ok=True)

                import hashlib
                h = hashlib.md5(prompt.encode()).hexdigest()[:8]
                file_path = os.path.join(ai_assets_dir, f"ve_ai_{scene_id}_{h}.png")

                with open(file_path, "wb") as f:
                    f.write(result["content"])

                element["source"] = file_path
                print(f"[UVE] Imagem IA salva: {file_path}")

    def run(self):
        print("[UVE] Iniciando processamento do vídeo...")

        scenes = self._normalize_scenes()
        total_scenes = len(scenes)

        if not scenes:
            print("[UVE] Nenhuma cena encontrada na configuração")
            return None

        # PRÉ-PROCESSAMENTO: resolve imagens IA em visual_elements antes do pool
        try:
            self._resolve_visual_elements_ai_sources(scenes)
        except Exception as e:
            print(f"[UVE] Pré-processamento de IA em visual_elements falhou: {e}")

        # PRÉ-PROCESSAMENTO
        try:
            scenes = NarrationEngine.preprocess_scenes({
                "provider": self.tts_config.get("provider", "edge"),
                "tts_config": self.tts_config,
                "scenes_data": scenes,
                "output_base_dir": self.output_dir
            })
        except Exception as e:
            print(f"[UVE] Pré-processamento de narração falhou: {e}")

        # Determinar número de workers
        max_workers = min(self.max_parallel_scenes, multiprocessing.cpu_count(), len(scenes))

        try:
            import psutil
            available_ram_gb = psutil.virtual_memory().available / (1024**3)
            if available_ram_gb < 4 and max_workers > 1:
                print(f"[UVE] RAM disponível baixa ({available_ram_gb:.1f}GB). Forçando modo sequencial.")
                max_workers = 1
        except ImportError:
            pass

        scene_files = []

        if max_workers == 1:
            print("[UVE] Modo sequencial ativado")

            for scene_index, scene in enumerate(scenes):
                scene_id = scene.get("id", f"cena_{scene_index}")
                print(f"\n[UVE] Processando cena {scene_index + 1}/{total_scenes}: {scene_id}")

                effective_gs = self._resolve_scene_gs(scene)

                # FIX: tts merge — global < chapter < cena
                tts_config = _resolve_scene_tts(
                    deep_merge(self.tts_config, effective_gs.get("tts", {})),
                    scene
                )

                scene_dir = os.path.join(self.output_dir, scene_id)
                os.makedirs(scene_dir, exist_ok=True)

                # 1. Narração
                narration_engine = NarrationEngine(tts_config, self.output_dir)
                narration_clip, duration_from_tts, subtitle_file = narration_engine.process_scene_narration(scene, scene_dir)

                if narration_clip is None:
                    print(f"[UVE] ⚠️ Narração não gerada para cena '{scene_id}'")
                else:
                    print(f"[UVE] ✅ Narração gerada: {duration_from_tts:.2f}s")

                # 2. Duração
                scene_duration = scene.get("duration", duration_from_tts)
                print(f"[UVE] Duração da cena: {scene_duration}s")

                # 3. Componentes
                try:
                    bg_engine = BackgroundEngine(
                        resolution_output=self.resolution_output,
                        dir_clips_cache=self.dir_media_index,
                        ai_cache=self.ai_cache,
                        remote_asset_manager=self.remote_asset_manager,
                    )
                    background_clip = bg_engine.build_scene_background(
                        effective_gs, scene, float(scene_duration), scene_dir, self.output_dir
                    )

                    # A cena pode zerar/ajustar os paddings só para ela.
                    scene_layout_params = _resolve_scene_layout_params(self.layout_params, scene)
                    scene_layout_config = SimpleNamespace(**scene_layout_params)

                    visual_clip = self._create_visual_elements_clip(
                        scene, scene_duration, scene_dir, layout_config=scene_layout_config
                    )

                    subtitle_clip = None
                    if _subtitles_enabled(effective_gs, scene):
                        has_visuals = bool(scene.get("visual_elements"))
                        subtitle_clip = self._create_subtitle_clip(
                            scene_duration, subtitle_file, effective_gs,
                            has_visuals, scene_data=scene, layout_params=scene_layout_params
                        )

                    # 4. Composição
                    final_scene_clip = [background_clip]
                    if visual_clip:
                        final_scene_clip.append(visual_clip)
                    if subtitle_clip:
                        final_scene_clip.append(subtitle_clip)

                    # 5. force_rgb
                    safe_clips = []
                    for c in final_scene_clip:
                        try:
                            c = c.fl_image(force_rgb)
                            safe_clips.append(c)
                        except Exception as e:
                            print(f"[UVE] Falha ao aplicar force_rgb: {e}")
                            safe_clips.append(c)

                    # 6. Compor cena final
                    composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
                    composed_clip = composed_clip.fl_image(force_rgb)

                    # 7. Narração
                    if narration_clip:
                        composed_clip = composed_clip.set_audio(narration_clip)
                    else:
                        print(f"[UVE] ⚠️ Cena '{scene_id}' sem narração — será renderizada com silêncio")

                    # 8. Transições — FIX: merge cena > global, respeita enabled: false
                    transitions_config = _resolve_scene_transitions(effective_gs, scene)
                    if transitions_config and transitions_config.get("enabled", False):
                        print(f"[UVE] Aplicando transição na cena {scene_index + 1}...")
                        try:
                            transition_engine = TransitionEngine({
                                "clip": composed_clip,
                                "transitions_settings": transitions_config,
                                "resolution": self.resolution_output
                            })
                            composed_clip = transition_engine.apply_transition()
                            print(f"[UVE] Transição aplicada com sucesso")
                        except Exception as e:
                            print(f"[UVE] Falha ao aplicar transição: {e}")
                    else:
                        print(f"[UVE] Transições desabilitadas para esta cena")

                    scene_clip_path = self._render_scene(
                        scene_index, scene_id, total_scenes,
                        composed_clip, narration_clip, scene_dir
                    )
                    scene_files.append(scene_clip_path)

                except Exception as e:
                    print(f"[UVE] Erro ao processar cena {scene_index + 1} (ID: {scene_id}): {e}")
                    import traceback
                    traceback.print_exc()
                    continue

        else:
            print(f"[UVE] Modo paralelo ativado: {max_workers} workers")

            scene_bundles = []
            for scene_index, scene in enumerate(scenes):
                effective_gs = self._resolve_scene_gs(scene)

                # FIX: tts merge — global < chapter < cena (bundle já leva config resolvida)
                tts_config = _resolve_scene_tts(
                    deep_merge(self.tts_config, effective_gs.get("tts", {})),
                    scene
                )

                bundle = {
                    "scene_index": scene_index,
                    "scene": scene,
                    "total_scenes": total_scenes,
                    "output_dir": self.output_dir,
                    "resolution_output": self.resolution_output,
                    "output_quality": self.output_quality,
                    "tts_config": tts_config,
                    "effective_gs": effective_gs,
                    "layout_params": self.layout_params,
                    "remote_assets_config": self.remote_assets_config,
                    "ai_cache_dir": self.ai_cache_dir,
                }
                scene_bundles.append(bundle)

            results = []
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_process_scene_worker, bundle): bundle["scene_index"]
                    for bundle in scene_bundles
                }

                for future in as_completed(futures):
                    try:
                        scene_index, scene_path = future.result(timeout=600)
                        if scene_path:
                            results.append((scene_index, scene_path))
                            print(f"[UVE] Cena {scene_index + 1} concluída com sucesso")
                        else:
                            print(f"[UVE] Cena {scene_index + 1} falhou")
                    except Exception as e:
                        print(f"[UVE] Exceção no worker: {e}")
                        import traceback
                        traceback.print_exc()

            results.sort(key=lambda x: x[0])
            scene_files = [path for _, path in results]

        # 9. Diagnóstico de áudio antes de concatenar
        scenes_without_audio = []
        for path in scene_files:
            if not _probe_has_audio(path):
                scenes_without_audio.append(os.path.basename(os.path.dirname(path)))

        if scenes_without_audio:
            print(f"\n[UVE] ⚠️ AVISO: {len(scenes_without_audio)} cena(s) ainda sem áudio após correção:")
            for s in scenes_without_audio:
                print(f"[UVE]    - {s}")

        # 10. Concatenar e aplicar bg audio
        slug = self.video_data.get("slug", "video_final")
        output_path = os.path.join(self.output_dir, f"{slug}.mp4")

        if not scene_files:
            print("[UVE] Nenhuma cena foi renderizada com sucesso")
            return None

        try:
            print(f"[UVE] Concatenando {len(scene_files)} cenas...")

            if self._has_per_chapter_audio():
                print("[UVE] Modo de áudio por chapter ativado")
                final_path = self._concat_and_apply_chapter_audio(scene_files, slug)
            else:
                intermediate_path = os.path.join(self.output_dir, f"{slug}_no_bg_audio.mp4")

                concat_list_path = os.path.join(self.output_dir, "concat_list.txt")
                with open(concat_list_path, "w", encoding="utf-8") as f:
                    for p in scene_files:
                        f.write(f"file '{os.path.abspath(p)}'\n")

                print("[UVE] Concatenando com re-encoding e FPS constante...")
                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", concat_list_path,
                    *self._ffmpeg_video_args(),
                    "-keyint_min", "60",
                    "-sc_threshold", "0",
                    "-force_key_frames", "expr:gte(t,n_forced*2)",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                    "-movflags", "+faststart",
                    intermediate_path
                ]
                subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
                print(f"[UVE] Vídeo concatenado: {intermediate_path}")

                if not _probe_has_audio(intermediate_path):
                    print("[UVE] ⚠️ Vídeo concatenado não tem stream de áudio!")
                    print("[UVE]    Verifique se o TTS gerou áudio para as cenas acima.")

                bg_audio_config = self.global_settings.get("background", {}).get("audio", {})
                if bg_audio_config and bg_audio_config.get("source"):
                    final_path = self._apply_background_audio_to_video(intermediate_path, output_path)
                else:
                    shutil.move(intermediate_path, output_path)
                    final_path = output_path
                    print("[UVE] Sem áudio de fundo configurado")

        except subprocess.CalledProcessError as e:
            print(f"[UVE] Falha na concatenação FFmpeg")
            print(f"[UVE] stderr: {e.stderr if e.stderr else 'N/A'}")
            return None
        except Exception as e:
            print(f"[UVE] Erro inesperado na concatenação: {e}")
            import traceback
            traceback.print_exc()
            return None

        # 11. Estatísticas Remote Assets
        print("\n[UVE] Estatísticas de Remote Assets:")
        final_stats = self.remote_asset_manager.get_stats()
        print(f"[UVE]    Total de slugs: {final_stats['total_slugs']}")
        print(f"[UVE]    URLs válidas: {final_stats['valid_media']}")
        print(f"[UVE]    URLs inválidas: {final_stats['invalid_media']}")

        print("[UVE] Debug config: " + str(self.video_data.get("debug", "N/A")))

        # 12. Upload YouTube
        if self.youtube_config and self.video_data.get("debug") is not True:
            try:
                print("[UVE] Iniciando upload para o YouTube...")
                youtube_params = self.youtube_config.copy()
                youtube_params["video_path"] = final_path
                youtube_uploader = YouTube(params=youtube_params)
                video_id = youtube_uploader.upload()

                thumbnail_path = youtube_uploader._resolve_thumbnail_path()
                if thumbnail_path:
                    print(f"[UVE] Enviando thumbnail: {os.path.basename(thumbnail_path)}")
                    youtube_uploader.upload_thumbnail(video_id, thumbnail_path)

                self._save_video_record(video_id, thumbnail_path, scenes)
            except Exception as e:
                print(f"[UVE] Upload YouTube falhou: {e}")

        # 12b. Upload TikTok
        tiktok_config = self.video_data.get("tiktok") or self.global_settings.get("tiktok")
        if tiktok_config and self.video_data.get("debug") is not True:
            try:
                print("[UVE] Iniciando upload para o TikTok...")
                tiktok_params = tiktok_config.copy()
                tiktok_params["video_path"] = final_path
                tiktok_uploader = TikTok(params=tiktok_params)
                tiktok_uploader.upload()
            except Exception as e:
                print(f"[UVE] Upload TikTok falhou: {e}")

        # 13. Abrir vídeo (debug)
        if self.video_data.get("debug") is True:
            try:
                print("[UVE] Abrindo vídeo final...")
                if os.name == 'nt':
                    os.startfile(final_path)
                elif os.name == 'posix':
                    subprocess.run(
                        ["open" if "darwin" in os.uname().sysname.lower() else "xdg-open", final_path])
            except Exception as e:
                print(f"[UVE] Falha ao abrir vídeo: {e}")

        print(f"\n[UVE] Processamento concluído com sucesso!")
        print(f"[UVE] Arquivo final: {final_path}")

        # 14 se debug for false e tiver uploadado, pode remover a pasta de saída para economizar espaço
        if self.video_data.get("debug") is not True:
            # try:
            #     shutil.rmtree(self.output_dir)
            #     print(f"[UVE] Pasta de saída removida: {self.output_dir}")
            # except Exception as e:
            #     print(f"[UVE] Falha ao remover pasta de saída: {e}")
            
            # se tiver uploadado para o youtube, pode remover a pasta inteira do video, se não deixa somente o arquivo final
            if self.youtube_config:
                try:
                    parent_dir = os.path.dirname(self.output_dir)
                    no_bg_filename = f"{slug}_no_bg_audio.mp4"
                    no_bg_path = os.path.join(self.output_dir, no_bg_filename)
                    if os.path.exists(no_bg_path):
                        dest = os.path.join(parent_dir, no_bg_filename)
                        shutil.move(no_bg_path, dest)
                        print(f"[UVE] Vídeo sem bg audio preservado: {dest}")
                    shutil.rmtree(self.output_dir)
                    print(f"[UVE] Pasta de saída removida: {self.output_dir}")
                except Exception as e:
                    print(f"[UVE] Falha ao remover pasta de saída: {e}")
            else:
                try:
                    for root, dirs, files in os.walk(self.output_dir):
                        for file in files:
                            if file != os.path.basename(final_path):
                                os.remove(os.path.join(root, file))

                    # mover o final para a pasta pai e remover a pasta de saída
                    parent_dir = os.path.dirname(self.output_dir)
                    shutil.move(final_path, os.path.join(parent_dir, os.path.basename(final_path))) # move o arquivo final para a pasta pai
                    shutil.rmtree(self.output_dir) # remove a pasta de saída após mover o final para a pasta pai

                    print(f"[UVE] Arquivos temporários removidos, mantendo apenas o final: {final_path}")
                except Exception as e:
                    print(f"[UVE] Falha ao limpar arquivos temporários: {e}")

        return final_path
