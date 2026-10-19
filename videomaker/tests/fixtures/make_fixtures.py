"""Gera os assets sintéticos usados pelos testes golden e de motion.

Determinístico: mesma seed, mesmos bytes. Roda offline (PIL + ffmpeg lavfi), sem
baixar nada e sem depender de `assets/` do projeto (que é gitignored).

    python tests/fixtures/make_fixtures.py [--force]

Saída em `tests/fixtures/assets/`:
    solid_1920x1080.png  solid_1080x1920.png  solid_800x800.png
    alpha_circle.png     (PNG com alpha)
    testsrc2.mp4  smptebars.mp4             (4 s cada)
    b_roll/clip_{1..4}.mp4                  (2 s cada, p/ type "directory")
    words.srt                               (SRT palavra-a-palavra sintético)
"""

import argparse
import os
import subprocess

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

# Cores fixas (não aleatórias): a "seed" deste gerador é a própria tabela.
_SOLIDS = {
    "solid_1920x1080.png": ((1920, 1080), (32, 96, 176)),
    "solid_1080x1920.png": ((1080, 1920), (176, 64, 32)),
    "solid_800x800.png":   ((800, 800),   (240, 200, 48)),
}


def _run(cmd: list):
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _solid(path: str, size: tuple, color: tuple):
    """Cor sólida com uma grade de contraste — cor plana esconderia erro de
    enquadramento (crop/zoom), que é justamente o que os golden vigiam."""
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    step = max(size) // 8
    light = tuple(min(255, c + 70) for c in color)
    for x in range(0, size[0], step):
        draw.line([(x, 0), (x, size[1])], fill=light, width=3)
    for y in range(0, size[1], step):
        draw.line([(0, y), (size[0], y)], fill=light, width=3)
    draw.rectangle([0, 0, size[0] - 1, size[1] - 1], outline=(255, 255, 255), width=6)
    img.save(path)


def _alpha_circle(path: str):
    size = (600, 600)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 20, size[0] - 20, size[1] - 20], fill=(255, 80, 120, 255))
    draw.ellipse([180, 180, 420, 420], fill=(255, 255, 255, 255))
    img.save(path)


def _lavfi_video(path: str, source: str, duration: float, size="640x360"):
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"{source}=size={size}:rate=30:duration={duration}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", path,
    ])


# Frase do SRT sintético. Palavras de 0,4 s cada, a partir de 0,2 s — tempos
# redondos para os testes de âncora poderem afirmar valores exatos.
SRT_TEXT = ("Hoje o dinheiro muda de mão. Porém o lucro de um bilhão não "
            "aparece sozinho; o dinheiro cobra juros.")
SRT_WORD_DURATION = 0.4
SRT_FIRST_START = 0.2


def _srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_entries() -> list:
    """[(index, word, start, end)] do SRT sintético — fonte única da verdade."""
    out = []
    for i, word in enumerate(SRT_TEXT.split()):
        start = SRT_FIRST_START + i * SRT_WORD_DURATION
        out.append((i + 1, word, start, start + SRT_WORD_DURATION))
    return out


def _words_srt(path: str):
    blocks = []
    for idx, word, start, end in srt_entries():
        blocks.append(f"{idx}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{word}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))


def build(force: bool = False) -> str:
    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(os.path.join(ASSETS, "b_roll"), exist_ok=True)

    for name, (size, color) in _SOLIDS.items():
        path = os.path.join(ASSETS, name)
        if force or not os.path.exists(path):
            _solid(path, size, color)

    path = os.path.join(ASSETS, "alpha_circle.png")
    if force or not os.path.exists(path):
        _alpha_circle(path)

    for name, src in (("testsrc2.mp4", "testsrc2"), ("smptebars.mp4", "smptebars")):
        path = os.path.join(ASSETS, name)
        if force or not os.path.exists(path):
            _lavfi_video(path, src, 4.0)

    for i, src in enumerate(("testsrc2", "smptebars", "testsrc", "rgbtestsrc"), start=1):
        path = os.path.join(ASSETS, "b_roll", f"clip_{i}.mp4")
        if force or not os.path.exists(path):
            _lavfi_video(path, src, 2.0, size="480x270")

    path = os.path.join(ASSETS, "words.srt")
    if force or not os.path.exists(path):
        _words_srt(path)

    return ASSETS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="regera mesmo se existir")
    args = ap.parse_args()
    out = build(force=args.force)
    print(f"[fixtures] assets em {out}")


if __name__ == "__main__":
    main()
