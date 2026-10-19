"""Paridade entre os dois backends de render.

Renderiza a MESMA cena com `RENDER_BACKEND=ffmpeg` e com `moviepy` e compara por
SSIM. Tolerância 0,98 (e não os 0,995 do golden) porque a reamostragem difere:
o ffmpeg escala com `bilinear` por frame e o MoviePy com PIL — 1 px de diferença
na borda de um elemento é esperado, 10 px não é.

É o teste caro da suíte (renderiza vídeo duas vezes, ~30 s). Marcado como `slow`:

    pytest tests/test_parity.py -q            # roda
    pytest tests/ -q -m "not slow"            # pula
"""

import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEOMAKER = os.path.dirname(HERE)
sys.path.insert(0, VIDEOMAKER)

from tests.compare_ssim import ssim_all          # noqa: E402

MIN_SSIM = 0.98

# Por caso, quando a tolerância precisa ser diferente — sempre com o motivo.
CASES = {
    "teste_01.json": MIN_SSIM,
    "teste_02.json": MIN_SSIM,
    "teste_03.json": MIN_SSIM,
    # Rotação: o `rotate` do ffmpeg e o do PIL interpolam a borda de um jeito
    # ligeiramente diferente. Com a textura de grade de alto contraste do
    # fixture isso custa ~2 pontos de SSIM, sem diferença visível (conferido
    # quadro a quadro: mesma posição, mesmo ângulo, mesmo tamanho).
    "teste_04.json": 0.96,
}


def _render(json_path: str, backend: str, out_dir: str) -> list:
    """Renderiza um JSON com o backend pedido, num processo separado.

    Processo separado porque `RENDER_BACKEND` é lido por variável de ambiente e
    o MoviePy deixa estado global (caches de clipe) que não vale a pena limpar
    dentro do pytest.
    """
    env = dict(os.environ, RENDER_BACKEND=backend, PROFILE="0")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "golden_render.py"),
         "--json", json_path, "--save", out_dir],
        cwd=VIDEOMAKER, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]
    return sorted(f for f in os.listdir(out_dir) if f.endswith(".mp4"))


@pytest.mark.slow
@pytest.mark.parametrize("case", sorted(CASES))
def test_backends_agree(case):
    json_path = os.path.join(HERE, "motion", case)
    if not os.path.exists(json_path):
        pytest.skip(f"{case} ausente")

    work = tempfile.mkdtemp(prefix="motion_parity_")
    try:
        fast = os.path.join(work, "ffmpeg")
        slow = os.path.join(work, "moviepy")
        names = _render(json_path, "ffmpeg", fast)
        assert names, "o backend ffmpeg não produziu nenhuma cena"
        assert names == _render(json_path, "moviepy", slow)

        for name in names:
            minimum = CASES[case]
            value = ssim_all(os.path.join(fast, name), os.path.join(slow, name))
            assert value >= minimum, f"{case}/{name}: SSIM {value:.5f} < {minimum}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# REGRESSÃO: dimensão ímpar na fonte de cor
# ---------------------------------------------------------------------------

def test_lavfi_color_keeps_odd_height():
    """`color` do lavfi nasce em yuv420p e ARREDONDA altura ímpar sem avisar.

    Regressão real: uma caixa de 864x307 virava 864x306 e o `alphamerge` do
    `border_radius` falhava, porque a máscara PNG tinha a altura exata. O
    `format=rgba` logo na fonte preserva o tamanho pedido.
    """
    cmd = [
        "ffmpeg", "-v", "info",
        "-f", "lavfi", "-i", "color=c=red:size=864x307:rate=5:duration=0.2,format=rgba",
        "-vf", "showinfo", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-400:]
    assert "s:864x307" in proc.stderr, "a altura ímpar foi arredondada"
