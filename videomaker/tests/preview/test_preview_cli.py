import json
import os
import subprocess
import sys

VIDEOMAKER = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_cli_preview(tmp_path, red_png):
    video = {"slug": "cli", "output": {"dir": str(tmp_path / "out"), "ratio": "16:9"},
             "scenes": [{"id": "a", "background": {"visual": {"type": "color", "color": "#000"}},
                         "visual_elements": [{"type": "image", "source": red_png}]}]}
    path = tmp_path / "v.json"
    path.write_text(json.dumps(video))
    proc = subprocess.run([sys.executable, "main.py", str(path), "--preview"],
                          cwd=VIDEOMAKER, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert all(os.path.isfile(s["path"]) for s in result["scenes"])
