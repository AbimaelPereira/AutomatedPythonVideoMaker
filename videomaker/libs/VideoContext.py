"""Contexto compartilhado de vídeo: merge de canal, output_dir, layout_params e
cenas achatadas — sem depender de MoviePy/TTS/Whisper.

Extraído do `UnifiedVideoEngine.__init__` (Fase 1 do plano de preview) para que
`Prepare` e `PreviewEngine` consigam montar o mesmo contexto sem pagar o custo
de importar o motor de render completo.
"""
import copy
import os
from dataclasses import dataclass, field

from libs.utils import deep_merge, load_channel_config, resolve_output_resolution, _default_safe_paddings


def resolve_video_output_dir(video_data: dict, channel_config: dict) -> str:
    """Resolve a pasta base de saída ({output.dir}), igual ao UVE.

    `output.dir` do vídeo vence o do canal; relativo resolve a partir do cwd
    (o `main.py` faz `chdir` para `videomaker/`); `~` é expandido; ausente →
    `{cwd}/output`.
    """
    output_cfg = deep_merge(
        channel_config.get("output", {}) or {},
        video_data.get("output", {}) or {}
    )
    configured_dir = output_cfg.get("dir")
    if configured_dir:
        return os.path.abspath(os.path.expanduser(str(configured_dir)))
    return os.path.join(os.getcwd(), "output")


def _sanitize_slug(slug: str) -> str:
    if "/" in slug or "\\" in slug or ".." in slug or "\0" in slug:
        raise ValueError(f"slug inválido (path traversal?): {slug!r}")
    return slug


def _normalize_scenes(video_data: dict, global_settings: dict) -> list:
    """Achata `chapters` em lista de cenas, cada uma com `_chapter_gs` anotado.

    Espelha `UnifiedVideoEngine._normalize_scenes`, mas não muta `video_data`
    (quem chama já trabalha sobre uma cópia).
    """
    scenes_out = []

    if "scenes" in video_data and "chapters" not in video_data:
        for scene in video_data["scenes"]:
            scene = dict(scene)
            scene["_chapter_gs"] = {}
            scenes_out.append(scene)
        return scenes_out

    if "chapters" in video_data:
        for chapter in video_data["chapters"]:
            chapter_gs = chapter.get("global_settings", {})
            for scene in chapter.get("scenes", []):
                scene = dict(scene)
                scene["_chapter_gs"] = chapter_gs
                scenes_out.append(scene)
        return scenes_out

    return scenes_out


@dataclass
class VideoContext:
    video_data: dict
    channel_config: dict
    global_settings: dict
    output_config: dict
    resolution: tuple
    layout_params: dict
    slug: str
    output_dir: str
    assets_dir: str
    previews_dir: str
    scenes: list = field(default_factory=list)

    @classmethod
    def from_video_data(cls, video_data: dict, *, require_slug: bool = True) -> "VideoContext":
        video_data = copy.deepcopy(video_data)

        channel_name = video_data.get("channel_name")
        channel_config = load_channel_config(channel_name) if channel_name else {}

        channel_gs = channel_config.get("global_settings", {})
        video_gs = video_data.get("global_settings", {})
        global_settings = deep_merge(channel_gs, video_gs)

        output_cfg = deep_merge(
            channel_config.get("output", {}) or {},
            video_data.get("output", {}) or {}
        )
        output_ratio = output_cfg.get("ratio") or video_data.get("output_ratio", "9:16")
        resolution = resolve_output_resolution(output_ratio)

        pad_defaults = _default_safe_paddings(resolution)
        layout_params = {
            "width":             resolution[0],
            "height":            resolution[1],
            "padding_bottom":    global_settings.get("padding_bottom", int(os.getenv("PADDING_BOTTOM", pad_defaults["padding_bottom"]))),
            "padding_top":       global_settings.get("padding_top",    int(os.getenv("PADDING_TOP", pad_defaults["padding_top"]))),
            "padding_side":      global_settings.get("padding_side",   int(os.getenv("PADDING_SIDE", pad_defaults["padding_side"]))),
            "stack_gap_percent": global_settings.get("stack_gap_percent", float(os.getenv("STACK_GAP_PERCENT", 0.02))),
        }

        slug = video_data.get("slug")
        if require_slug and not slug:
            raise ValueError("slug ausente no JSON do vídeo")
        slug = slug or "video_sem_slug"
        _sanitize_slug(slug)

        base_output_dir = resolve_video_output_dir(video_data, channel_config)
        output_dir = os.path.join(base_output_dir, slug)
        assets_dir = os.path.join(output_dir, "assets")
        previews_dir = os.path.join(output_dir, "previews")

        scenes = _normalize_scenes(video_data, global_settings)
        for index, scene in enumerate(scenes):
            chapter_gs = scene.pop("_chapter_gs", {})
            scene["_index"] = index
            scene["_effective_gs"] = deep_merge(global_settings, chapter_gs)

        return cls(
            video_data=video_data,
            channel_config=channel_config,
            global_settings=global_settings,
            output_config=output_cfg,
            resolution=resolution,
            layout_params=layout_params,
            slug=slug,
            output_dir=output_dir,
            assets_dir=assets_dir,
            previews_dir=previews_dir,
            scenes=scenes,
        )

    def select_scenes(self, selection) -> list:
        """ids ou índices 1-based → índices 0-based. None = todas."""
        if selection is None:
            return [s["_index"] for s in self.scenes]
        by_id = {s.get("id"): s["_index"] for s in self.scenes if s.get("id")}
        out = []
        for item in selection:
            if isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
                n = int(item)
                if not 1 <= n <= len(self.scenes):
                    raise ValueError(f"cena {n} fora do intervalo 1..{len(self.scenes)}")
                idx = n - 1
            elif item in by_id:
                idx = by_id[item]
            else:
                raise ValueError(f"cena '{item}' não existe. Válidas: {sorted(by_id)}")
            if idx not in out:
                out.append(idx)
        return out
