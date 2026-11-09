"""`output.type: "image"`: cada cena vira um PNG (motor do preview) e é publicada no Instagram.

1 cena → post/story simples; 2–10 cenas → carrossel no feed (story: um por imagem).
Pula TTS, legenda, transições, concat e áudio. YouTube/TikTok são ignorados.
Limpeza igual ao vídeo: tudo OK → apaga a pasta; falha → mantém só os PNGs finais.
"""
import os
import shutil

from libs.utils import deep_merge
from libs.VideoContext import VideoContext


def output_type(video_data: dict) -> str:
    from libs.utils import load_channel_config
    channel = load_channel_config(video_data["channel_name"]) if video_data.get("channel_name") else {}
    out = deep_merge(channel.get("output", {}) or {}, video_data.get("output", {}) or {})
    return out.get("type") or "video"


class ImagePostEngine:
    def __init__(self, video_data: dict):
        self.video_data = video_data
        self.debug = (os.getenv("DEBUG", "0").lower() in ("true", "1", "t")
                      or video_data.get("debug") is True)
        self.ctx = VideoContext.from_video_data(video_data)
        ig = deep_merge(self.ctx.channel_config.get("instagram", {}) or {},
                        video_data.get("instagram", {}) or {})
        self.instagram_config = ig if ig and ig.get("enabled", True) else None

    def _warn_ignored(self):
        for k in ("youtube", "tiktok"):
            if self.video_data.get(k) or self.ctx.channel_config.get(k) or self.ctx.global_settings.get(k):
                print(f"[ImagePost] Aviso: '{k}' ignorado no modo imagem")
        for i, scene in enumerate(self.ctx.scenes):
            gs = scene.get("_effective_gs") or {}
            if (scene.get("subtitle") or gs.get("subtitle") or {}).get("enabled"):
                print(f"[ImagePost] Aviso: cena {i + 1}: subtitle ignorado (use text_box)")
            if any(el.get("motion") or el.get("animation") for el in scene.get("visual_elements") or []):
                print(f"[ImagePost] Aviso: cena {i + 1}: motion/animation ignorado (pose de repouso)")

    def _final_paths(self, previews: list) -> list:
        slug, n = self.ctx.slug, len(previews)
        finals = []
        for i, src in enumerate(previews, 1):
            name = f"{slug}.png" if n == 1 else f"{slug}_{i:02d}.png"
            dst = os.path.join(self.ctx.output_dir, name)
            shutil.copyfile(src, dst)
            finals.append(dst)
        return finals

    def _cleanup(self, finals: list, all_ok: bool) -> None:
        out = self.ctx.output_dir
        try:
            if all_ok:
                shutil.rmtree(out)
                print(f"[ImagePost] Pasta de saída removida: {out}")
                return
            keep = {os.path.abspath(f) for f in finals}
            for entry in os.listdir(out):
                path = os.path.abspath(os.path.join(out, entry))
                if path in keep:
                    continue
                shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
            print(f"[ImagePost] Publicação falhou — imagens preservadas em {out}")
        except Exception as e:
            print(f"[ImagePost] Falha na limpeza: {e}")

    def run(self) -> list:
        from libs.Instagram import CAROUSEL_MAX, Instagram
        from libs.Preview.PreviewEngine import PreviewEngine

        publish = bool(self.instagram_config) and not self.debug
        n = len(self.ctx.scenes)
        if publish:
            ig = Instagram(params=self.instagram_config)
            problemas = ig.validar()
            if "feed" in ig.targets() and n > CAROUSEL_MAX:
                problemas.append(f"{n} cenas: carrossel aceita no máximo {CAROUSEL_MAX}")
            if problemas:
                raise ValueError("Config do Instagram inválida:\n  - " + "\n  - ".join(problemas))
        self._warn_ignored()

        result = PreviewEngine(self.ctx).run()
        erros = [f"cena {sp.index}: {sp.error}" for sp in result.scenes if not sp.path]
        if erros:
            raise RuntimeError("Falha ao renderizar imagens: " + "; ".join(erros))
        finals = self._final_paths([sp.path for sp in result.scenes])
        print(f"[ImagePost] {len(finals)} imagem(ns) em {self.ctx.output_dir}")

        if not publish:
            return finals

        all_ok = False
        try:
            for f in finals:
                problemas = ig.validar(f, kind="image")
                if problemas:
                    raise ValueError(f"{os.path.basename(f)}: " + "; ".join(problemas))
            results = ig.publish_images(finals, slug=self.ctx.slug)
            all_ok = bool(results) and all(r["ok"] for r in results)
        except Exception as e:
            print(f"[ImagePost] Publicação falhou: {e}")
        self._cleanup(finals, all_ok)
        return finals
