import os
import re
import time
import requests
import mimetypes
import hashlib


def _sanitize_source(source: str) -> str:
    """
    Normaliza a source removendo artefatos de markdown e URLs duplicadas.

    Casos tratados:
      1. "[label](url)"              → url
      2. "url](url)"                 → url  (markdown quebrado sem colchete de abertura)
      3. "url](url_diferente)"       → primeira url
      4. "url"                       → url  (passthrough)
    """
    if not source:
        return source

    source = source.strip()

    # Caso 1: markdown link completo [label](url)
    match = re.match(r'^\[.*?\]\((https?://[^)]+)\)$', source)
    if match:
        return match.group(1)

    # Caso 2/3: URL contém "](..." — pega apenas a parte antes do "]("
    # Ex: "https://exemplo.com/img.jpg](https://exemplo.com/img.jpg"
    bracket_pos = source.find('](')
    if bracket_pos != -1:
        candidate = source[:bracket_pos].strip()
        if candidate.lower().startswith(("http:", "https:")):
            return candidate

    return source


class MediaDownloader:
    """
    Classe utilitária para baixar e armazenar em cache ativos de mídia externos (imagens, vídeos).
    Suporta retry com backoff em erros 429/5xx.
    """

    # Erros que valem retry (rate limit e erros temporários de servidor)
    _RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
    _MAX_RETRIES        = 3
    _RETRY_BACKOFF      = [2, 5, 10]   # segundos entre tentativas

    @staticmethod
    def resolve_source_path(source: str, temp_dir: str = "output/temp",
                            on_success_callback=None, on_fail_callback=None) -> str | None:
        """
        Verifica se a fonte é uma URL. Se for, baixa e salva em temp_dir.
        Reutiliza cache local se o arquivo já existir.
        Faz retry automático em 429/5xx com backoff.

        Args:
            source: URL ou caminho local
            temp_dir: Diretório onde salvar
            on_success_callback: Chamado após download bem-sucedido (recebe url)
            on_fail_callback: Chamado se download falhar definitivamente (recebe url)

        Returns:
            Caminho local do arquivo ou None se falhar
        """
        if not source:
            print("[MediaDownloader] Fonte (source) ausente.")
            return None

        # Sanitiza markdown links e URLs malformadas
        source = _sanitize_source(source)

        local_path = source
        os.makedirs(temp_dir, exist_ok=True)

        if source.lower().startswith(("http:", "https:")):
            print(f"[MediaDownloader] URL detectada: {source[:80]}...")
            try:
                # 1. Nome único baseado no hash da URL limpa
                url_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()[:16]
                local_path_base = os.path.join(temp_dir, f"asset_{url_hash}")

                # 2. Cache local — reutiliza se já existir nesta pasta
                cached_path = None
                for ext in ['.png', '.jpg', '.jpeg', '.mp4', '.mov', '.webm', '.gif']:
                    test_path = local_path_base + ext
                    if os.path.exists(test_path) and os.path.getsize(test_path) > 0:
                        cached_path = test_path
                        break

                if cached_path:
                    print(f"[MediaDownloader] ✅ Cache hit: {os.path.basename(cached_path)}")
                    if on_success_callback:
                        on_success_callback(source)
                    return cached_path

                # 3. Download com retry em 429/5xx
                response = None
                last_exc  = None

                for attempt in range(1, MediaDownloader._MAX_RETRIES + 1):
                    try:
                        print(f"[MediaDownloader] 📥 Baixando (tentativa {attempt}/{MediaDownloader._MAX_RETRIES}): {temp_dir}...")
                        response = requests.get(
                            source,
                            timeout=30,
                            headers={"User-Agent": "Mozilla/5.0 (compatible; AutomatedVideoMaker/1.0)"},
                        )
                        response.raise_for_status()
                        last_exc = None
                        break  # sucesso

                    except requests.exceptions.HTTPError as e:
                        status = response.status_code if response is not None else 0
                        last_exc = e
                        if status in MediaDownloader._RETRYABLE_STATUSES and attempt < MediaDownloader._MAX_RETRIES:
                            wait = MediaDownloader._RETRY_BACKOFF[attempt - 1]
                            print(f"[MediaDownloader] ⚠️  HTTP {status} — aguardando {wait}s antes de tentar novamente...")
                            time.sleep(wait)
                            continue
                        break  # erro não-retryable ou esgotou tentativas

                    except requests.exceptions.Timeout:
                        last_exc = None
                        print(f"[MediaDownloader] ❌ Timeout (30s): {source[:80]}...")
                        if on_fail_callback:
                            on_fail_callback(source)
                        return None

                if last_exc is not None:
                    status = response.status_code if response is not None else 'N/A'
                    print(f"[MediaDownloader] ❌ Erro HTTP {status} após {MediaDownloader._MAX_RETRIES} tentativas: {last_exc}")
                    if on_fail_callback:
                        on_fail_callback(source)
                    return None

                if response is None:
                    print(f"[MediaDownloader] ❌ Sem resposta para: {source[:80]}...")
                    if on_fail_callback:
                        on_fail_callback(source)
                    return None

                # 4. Determina extensão e salva
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type)

                if not ext:
                    url_ext = os.path.splitext(source.split('?')[0])[-1]
                    ext = url_ext if url_ext else '.png'

                final_path = local_path_base + ext.lower()

                with open(final_path, 'wb') as f:
                    f.write(response.content)

                print(f"[MediaDownloader] ✅ Download concluído: {os.path.basename(final_path)}")

                if on_success_callback:
                    on_success_callback(source)

                return final_path

            except requests.exceptions.RequestException as e:
                status = response.status_code if response is not None else 'N/A'
                print(f"[MediaDownloader] ❌ Erro HTTP {status}: {e}")
                if on_fail_callback:
                    on_fail_callback(source)
                return None

            except Exception as e:
                print(f"[MediaDownloader] ❌ Erro inesperado: {e}")
                if on_fail_callback:
                    on_fail_callback(source)
                return None

        return local_path