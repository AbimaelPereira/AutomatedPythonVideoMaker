"""
generate_channel_assets.py
Gera imagens com fundo transparente para o canal Psychology of the Gospel.
Coloque este script na raiz do projeto e execute: python generate_channel_assets.py

Dependências: PollinationsProvider em libs/AIProviders/PollinationsProvider.py
Saída: output/psychology_of_the_gospel/
"""

import json
import sys
import os
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv(Path(os.path.dirname(os.path.abspath(__file__))) / ".env")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from libs.AIProviders.PollinationsProvider import PollinationsProvider

# ─── Configuração ────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("output/psychology_of_the_gospel")
PROMPTS_FILE = Path("oil_painting_assets.json")
MODEL = "flux"
WIDTH = 1536
HEIGHT = 1536
QUALITY = "hd"
MAX_WORKERS = 4        # requisições simultâneas
DELAY_MIN = 1.5        # delay mínimo entre requisições (segundos)
DELAY_MAX = 3.5        # delay máximo (jitter evita burst sincronizado)

# ─── Setup ───────────────────────────────────────────────────────────────────

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
provider = PollinationsProvider()

# ─── Carrega prompts ─────────────────────────────────────────────────────────

with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

prompts = data["assets"]
total = len(prompts)

print(f"\n{'='*60}")
print(f"  Psychology of the Gospel — Asset Generator")
print(f"  Total de imagens: {total}")
print(f"  Modelo: {MODEL} | Resolução: {WIDTH}x{HEIGHT} | Workers: {MAX_WORKERS}")
print(f"  Saída: {OUTPUT_DIR}")
print(f"{'='*60}\n")

# ─── Geração ─────────────────────────────────────────────────────────────────

success_count = 0
fail_count = 0
failed_items = []
lock_print = __import__("threading").Lock()


def generate_one(item, index):
    slug = item["slug"]
    prompt = item["prompt"]
    category = item["category"]

    category_dir = OUTPUT_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)
    output_path = category_dir / f"{slug}.png"

    if output_path.exists():
        with lock_print:
            print(f"[{index:02d}/{total}] ⏭️  Já existe: {slug}.png")
        return "skip", slug

    with lock_print:
        print(f"[{index:02d}/{total}] 🎨 Gerando: {slug}  ({category})")

    result = provider.generate_image(
        prompt=prompt,
        model=MODEL,
        width=WIDTH,
        height=HEIGHT,
        quality=QUALITY,
        transparent=False,
        enhance=False,
        safe=True,
        enable_fallback=True
    )

    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    time.sleep(delay)

    if result["success"]:
        output_path.write_bytes(result["content"])
        with lock_print:
            print(f"[{index:02d}/{total}] ✅ Salvo: {slug}.png")
        return "ok", slug
    else:
        with lock_print:
            print(f"[{index:02d}/{total}] ❌ Falhou: {slug} — {result.get('error')}")
        return "fail", slug


with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {
        executor.submit(generate_one, item, i): i
        for i, item in enumerate(prompts, 1)
    }
    for future in as_completed(futures):
        status, slug = future.result()
        if status == "ok":
            success_count += 1
        elif status == "skip":
            success_count += 1
        else:
            fail_count += 1
            failed_items.append(slug)

# ─── Relatório final ──────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"  Relatório Final")
print(f"  ✅ Sucesso: {success_count}/{total}")
print(f"  ❌ Falhas:  {fail_count}/{total}")
if failed_items:
    print(f"\n  Itens que falharam:")
    for slug in failed_items:
        print(f"    - {slug}")
print(f"{'='*60}\n")
