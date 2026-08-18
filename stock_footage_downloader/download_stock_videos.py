#!/usr/bin/env python3
"""
Baixa vídeos de paisagem (horizontais, alta resolução) do Pexels e Pixabay.

Uso:
    python download_stock_videos.py
    python download_stock_videos.py --target 500 --out "/media/pendrive/Grupo Win Lite BR"

Retomável: mantém um CSV de log + um arquivo de IDs já baixados. Se o script
for interrompido, rode de novo com o mesmo --out que ele continua de onde parou.
"""

import argparse
import csv
import os
import sys
import time
import random
import signal
import requests

# ----------------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------------

# Chaves lidas do ambiente (ex.: `export PEXELS_API_KEY=...`) para não ficarem
# no repositório. Sem a chave, o provedor correspondente é simplesmente pulado.
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"

SEARCH_TERMS = [
    "ocean", "sunset", "mountains", "forest", "sky",
    "clouds", "waterfall", "river", "beach", "sunrise",
]

DEFAULT_TARGET = 500
DEFAULT_OUT_DIR = "downloaded_videos"
MIN_WIDTH = 1920
MIN_HEIGHT = 1080

PEXELS_DELAY = 1.2   # ~50 req/hora no free tier costuma ser bem mais folgado; isso é conservador por página
PIXABAY_DELAY = 1.0
DOWNLOAD_DELAY = 0.5
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

STATE_FILENAME = "downloaded_ids.txt"
LOG_FILENAME = "metadata.csv"

CSV_FIELDS = [
    "source", "term", "video_id", "filename", "width", "height",
    "duration_seconds", "resolution_label", "original_url", "download_url",
]


# ----------------------------------------------------------------------------
# Controle de interrupção (Ctrl+C) — termina o download atual e sai limpo
# ----------------------------------------------------------------------------

class GracefulStop:
    def __init__(self):
        self.stop = False
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)

    def _handle(self, signum, frame):
        if self.stop:
            # segundo Ctrl+C: força saída imediata
            print("\nForçando saída imediata.")
            sys.exit(1)
        print("\nInterrompido. Terminando o download atual e salvando progresso...")
        self.stop = True


stopper = GracefulStop()


# ----------------------------------------------------------------------------
# Estado / retomada
# ----------------------------------------------------------------------------

def load_downloaded_ids(state_path):
    ids = set()
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ids.add(line)
    return ids


def append_downloaded_id(state_path, uid):
    with open(state_path, "w" if not os.path.exists(state_path) else "a", encoding="utf-8") as f:
        f.write(uid + "\n")


def init_csv_log(log_path):
    is_new = not os.path.exists(log_path)
    if is_new:
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def append_csv_log(log_path, row):
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow(row)


# ----------------------------------------------------------------------------
# HTTP helper com retry
# ----------------------------------------------------------------------------

def request_with_retry(method, url, **kwargs):
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            if resp.status_code == 429:
                wait = 5 * attempt
                print(f"  Rate limit atingido, aguardando {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            wait = 2 * attempt
            print(f"  Erro de rede ({exc.__class__.__name__}: {exc}), tentativa {attempt}/{MAX_RETRIES}, aguardando {wait}s...")
            time.sleep(wait)
    print(f"  Falhou após {MAX_RETRIES} tentativas: {last_exc}")
    return None


# ----------------------------------------------------------------------------
# Pexels
# ----------------------------------------------------------------------------

def pexels_search(term, page, per_page=80):
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": term, "orientation": "landscape", "per_page": per_page, "page": page}
    resp = request_with_retry("GET", PEXELS_SEARCH_URL, headers=headers, params=params)
    if resp is None:
        return None
    return resp.json()


def pexels_pick_best_file(video):
    """Escolhe o arquivo de maior resolução, horizontal, >= 1080p quando possível."""
    candidates = [
        f for f in video.get("video_files", [])
        if f.get("width") and f.get("height") and f["width"] > f["height"]
    ]
    if not candidates:
        return None

    hd_or_better = [f for f in candidates if f["height"] >= MIN_HEIGHT]
    pool = hd_or_better if hd_or_better else candidates
    best = max(pool, key=lambda f: f["width"] * f["height"])
    return best


def iter_pexels_videos(term, seen_ids):
    if not PEXELS_API_KEY:
        return
    page = 1
    while True:
        if stopper.stop:
            return
        data = pexels_search(term, page)
        time.sleep(PEXELS_DELAY)
        if data is None:
            return
        videos = data.get("videos", [])
        if not videos:
            return
        for video in videos:
            vid = str(video.get("id"))
            uid = f"pexels_{vid}"
            if uid in seen_ids:
                continue
            if video.get("width", 0) <= video.get("height", 0):
                continue  # não é horizontal
            best_file = pexels_pick_best_file(video)
            if not best_file:
                continue
            yield {
                "source": "pexels",
                "term": term,
                "video_id": vid,
                "uid": uid,
                "width": best_file["width"],
                "height": best_file["height"],
                "duration_seconds": video.get("duration", ""),
                "original_url": video.get("url", ""),
                "download_url": best_file["link"],
            }
        if not data.get("next_page"):
            return
        page += 1


# ----------------------------------------------------------------------------
# Pixabay
# ----------------------------------------------------------------------------

PIXABAY_PER_PAGE = 200


def pixabay_search(term, page, per_page=PIXABAY_PER_PAGE):
    params = {
        "key": PIXABAY_API_KEY,
        "q": term,
        "video_type": "film",
        "orientation": "horizontal",
        "per_page": per_page,
        "page": page,
    }
    resp = request_with_retry("GET", PIXABAY_SEARCH_URL, params=params)
    if resp is None:
        return None
    return resp.json()


def pixabay_pick_best_file(video):
    """videos: {large, medium, small, tiny} — cada um com width/height/url."""
    sizes = video.get("videos", {})
    candidates = [
        (label, f) for label, f in sizes.items()
        if f.get("width") and f.get("height") and f["width"] > f["height"]
    ]
    if not candidates:
        return None
    hd_or_better = [(l, f) for l, f in candidates if f["height"] >= MIN_HEIGHT]
    pool = hd_or_better if hd_or_better else candidates
    label, best = max(pool, key=lambda item: item[1]["width"] * item[1]["height"])
    return label, best


def iter_pixabay_videos(term, seen_ids):
    if not PIXABAY_API_KEY:
        return
    page = 1
    while True:
        if stopper.stop:
            return
        data = pixabay_search(term, page)
        time.sleep(PIXABAY_DELAY)
        if data is None:
            return
        hits = data.get("hits", [])
        if not hits:
            return
        for video in hits:
            vid = str(video.get("id"))
            uid = f"pixabay_{vid}"
            if uid in seen_ids:
                continue
            picked = pixabay_pick_best_file(video)
            if not picked:
                continue
            label, best_file = picked
            yield {
                "source": "pixabay",
                "term": term,
                "video_id": vid,
                "uid": uid,
                "width": best_file["width"],
                "height": best_file["height"],
                "duration_seconds": video.get("duration", ""),
                "original_url": f"https://pixabay.com/videos/id-{vid}/",
                "download_url": best_file["url"],
                "resolution_label": label,
            }
        total_hits = data.get("totalHits", 0)
        if page * PIXABAY_PER_PAGE >= total_hits:
            return
        page += 1


# ----------------------------------------------------------------------------
# Download de arquivo
# ----------------------------------------------------------------------------

class OutOfDiskSpace(Exception):
    pass


def download_file(url, dest_path):
    tmp_path = dest_path + ".part"
    try:
        with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        try:
                            f.write(chunk)
                        except OSError as exc:
                            if exc.errno == 28:  # ENOSPC
                                raise OutOfDiskSpace() from exc
                            raise
        os.replace(tmp_path, dest_path)
        return True
    except OutOfDiskSpace:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    except requests.RequestException as exc:
        print(f"  Falha ao baixar {url}: {exc}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def resolution_label_for(width, height, explicit_label=None):
    if explicit_label:
        return explicit_label
    if height >= 2160:
        return "4k"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    return f"{width}x{height}"


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Baixa vídeos de paisagem do Pexels/Pixabay.")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET, help="Total de vídeos a baixar.")
    parser.add_argument("--out", type=str, default=DEFAULT_OUT_DIR, help="Pasta de destino dos vídeos.")
    parser.add_argument("--terms", type=str, nargs="*", default=None, help="Lista customizada de termos de busca.")
    args = parser.parse_args()

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    state_path = os.path.join(out_dir, STATE_FILENAME)
    log_path = os.path.join(out_dir, LOG_FILENAME)
    init_csv_log(log_path)

    seen_ids = load_downloaded_ids(state_path)
    already = len(seen_ids)
    target = args.target
    terms = args.terms or SEARCH_TERMS

    if not PEXELS_API_KEY and not PIXABAY_API_KEY:
        print("Defina PEXELS_API_KEY e/ou PIXABAY_API_KEY no ambiente antes de rodar.")
        return
    for name, key in (("PEXELS_API_KEY", PEXELS_API_KEY), ("PIXABAY_API_KEY", PIXABAY_API_KEY)):
        if not key:
            print(f"{name} ausente: essa fonte será ignorada.")

    print(f"Destino: {out_dir}")
    print(f"Meta: {target} vídeos | Já baixados anteriormente: {already}")
    print(f"Termos: {', '.join(terms)}\n")

    if already >= target:
        print("Meta já atingida anteriormente. Nada a fazer.")
        return

    # Gera um iterador por termo/fonte, e alterna round-robin entre eles
    sources = []
    for term in terms:
        sources.append(("pexels", term, iter_pexels_videos(term, seen_ids)))
        sources.append(("pixabay", term, iter_pixabay_videos(term, seen_ids)))

    downloaded_count = already
    active_sources = list(sources)

    while active_sources and downloaded_count < target and not stopper.stop:
        next_round = []
        for source_name, term, gen in active_sources:
            if stopper.stop or downloaded_count >= target:
                break
            try:
                item = next(gen)
            except StopIteration:
                continue  # esgotado, não recoloca na próxima rodada
            except Exception as exc:
                print(f"  Erro inesperado em {source_name}/{term}: {exc}")
                continue

            uid = item["uid"]
            if uid in seen_ids:
                next_round.append((source_name, term, gen))
                continue

            width, height = item["width"], item["height"]
            ext = os.path.splitext(item["download_url"].split("?")[0])[1] or ".mp4"
            filename = f"{item['source']}_{item['term']}_{item['video_id']}{ext}"
            dest_path = os.path.join(out_dir, filename)

            print(f"[{downloaded_count + 1}/{target}] Baixando {filename} ({width}x{height})...")
            try:
                ok = download_file(item["download_url"], dest_path)
            except OutOfDiskSpace:
                print("\nSem espaço livre no destino. Parando o download (progresso já salvo).")
                stopper.stop = True
                break
            time.sleep(DOWNLOAD_DELAY)

            if ok:
                seen_ids.add(uid)
                append_downloaded_id(state_path, uid)
                append_csv_log(log_path, {
                    "source": item["source"],
                    "term": item["term"],
                    "video_id": item["video_id"],
                    "filename": filename,
                    "width": width,
                    "height": height,
                    "duration_seconds": item.get("duration_seconds", ""),
                    "resolution_label": resolution_label_for(width, height, item.get("resolution_label")),
                    "original_url": item.get("original_url", ""),
                    "download_url": item["download_url"],
                })
                downloaded_count += 1
                print(f"  OK. Progresso: {downloaded_count}/{target}")
            else:
                print(f"  Pulando {filename} (falha no download).")

            next_round.append((source_name, term, gen))

        active_sources = next_round
        if not active_sources:
            print("\nTodos os termos/fontes se esgotaram antes de atingir a meta.")
            break

    print(f"\nFinalizado. Total baixado nesta pasta: {downloaded_count}/{target}")
    if stopper.stop:
        print("Execução interrompida pelo usuário. Rode o script novamente com o mesmo --out para continuar de onde parou.")


if __name__ == "__main__":
    main()
