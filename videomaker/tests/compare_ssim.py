"""Compara dois diretórios de MP4s por SSIM (via ffmpeg) e falha se divergirem.

    python tests/compare_ssim.py tests/baseline/ tests/atual/
    python tests/compare_ssim.py tests/baseline/ tests/atual/ --min 0.98

Pareia por nome de arquivo. Sai com código 1 se algum par ficar abaixo do limiar
ou se faltar/sobrar arquivo de um lado.
"""

import argparse
import os
import re
import subprocess
import sys

DEFAULT_MIN = 0.995


def ssim_all(path_a: str, path_b: str) -> float:
    """SSIM médio ("All") entre dois vídeos. Levanta se o ffmpeg falhar."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", path_a, "-i", path_b,
        "-lavfi", "[0:v][1:v]ssim=stats_file=-", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg ssim falhou: {(proc.stderr or '')[-500:]}")

    # O resumo vai para o stderr: "SSIM Y:0.99 U:... All:0.993 (21.5)"
    found = re.findall(r"All:([0-9.]+)", (proc.stderr or "") + (proc.stdout or ""))
    if not found:
        raise RuntimeError("ffmpeg não reportou SSIM (vídeos sem frames em comum?)")
    # A última ocorrência é o agregado do run inteiro; as anteriores são por frame.
    return min(float(v) for v in found[-1:])


def compare(dir_a: str, dir_b: str, minimum: float = DEFAULT_MIN) -> int:
    names_a = {f for f in os.listdir(dir_a) if f.endswith(".mp4")}
    names_b = {f for f in os.listdir(dir_b) if f.endswith(".mp4")}

    failures = []
    for name in sorted(names_a - names_b):
        failures.append(f"{name}: ausente em {dir_b}")
    for name in sorted(names_b - names_a):
        failures.append(f"{name}: ausente em {dir_a}")

    for name in sorted(names_a & names_b):
        try:
            value = ssim_all(os.path.join(dir_a, name), os.path.join(dir_b, name))
        except Exception as e:
            failures.append(f"{name}: {e}")
            continue
        status = "✅" if value >= minimum else "❌"
        print(f"{status} {name}  SSIM={value:.5f}")
        if value < minimum:
            failures.append(f"{name}: SSIM {value:.5f} < {minimum}")

    if failures:
        print(f"\n[ssim] {len(failures)} divergência(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\n[ssim] {len(names_a & names_b)} par(es) ≥ {minimum} — ok")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir_a")
    ap.add_argument("dir_b")
    ap.add_argument("--min", type=float, default=DEFAULT_MIN,
                    help=f"SSIM mínimo aceito (default {DEFAULT_MIN})")
    args = ap.parse_args()
    return compare(args.dir_a, args.dir_b, args.min)


if __name__ == "__main__":
    sys.exit(main())
