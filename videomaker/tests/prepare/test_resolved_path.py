import numpy as np
from PIL import Image

from libs.Background.BackgroundEngine import BackgroundEngine


def test_fundo_ia_preparado_mantem_resize_puro(tmp_path, monkeypatch):
    """Provider devolveu tamanho diferente do pedido: segue com resize (sem crop)."""
    import libs.Background.BackgroundEngine as be
    monkeypatch.setattr(be, "_ai_manager", lambda: object())

    img = np.zeros((50, 100, 3), dtype=np.uint8)
    img[:, :50] = (255, 0, 0)  # metade esquerda vermelha
    path = tmp_path / "ai.png"
    Image.fromarray(img).save(path)

    engine = BackgroundEngine((60, 120), {}, asset_store=None)
    cfg = {"type": "ai", "prompt": "x", "_resolved_path": str(path)}
    clip = engine._build_ai(cfg, 1.0, str(tmp_path), {})
    frame = clip.get_frame(0)
    assert frame.shape[:2] == (120, 60)
    # resize puro: a fronteira vermelho/preto continua no meio (cover recortaria)
    assert frame[60, 10, 0] > 200 and frame[60, 50, 0] < 50
