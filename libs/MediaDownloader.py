import os
import requests
import mimetypes
import hashlib 

class MediaDownloader:
    """
    Classe utilitária para baixar e armazenar em cache ativos de mídia externos (imagens, vídeos).
    """
    
    @staticmethod
    def resolve_source_path(source: str, temp_dir: str = "output/temp") -> str | None:
        """
        Verifica se a fonte é uma URL. Se for, baixa e armazena em cache localmente.
        Caso contrário, retorna o caminho de origem original (assumido como local).
        """
        if not source:
            print("[DEBUG_MD] Fonte (source) ausente.")
            return None
        
        local_path = source
        os.makedirs(temp_dir, exist_ok=True)

        if source.lower().startswith(("http:", "https:")):
            print(f"[DEBUG_MD] URL detectada: {source}. Tentando download...")
            try:
                # 1. Determinar o nome do arquivo no cache (usando hash da URL para segurança)
                url_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
                local_path_base = os.path.join(temp_dir, f"asset_{url_hash}")

                # 2. Verificar o Cache
                cached_path = None
                for ext in ['.png', '.jpg', '.jpeg', '.mp4', '.mov', '.webm']:
                    test_path = local_path_base + ext
                    if os.path.exists(test_path) and os.path.getsize(test_path) > 0:
                        cached_path = test_path
                        break
                        
                if cached_path:
                    print(f"[DEBUG_MD] Arquivo já existe no cache: {cached_path}")
                    return cached_path
                
                # 3. Executar o download
                print(f"[DEBUG_MD] Baixando (GET) para arquivo temporário...")
                response = requests.get(source, timeout=30)
                response.raise_for_status() 

                # 4. Determinar extensão final e salvar
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type)
                
                if not ext:
                    url_ext = os.path.splitext(source.split('?')[0])[-1]
                    if url_ext: ext = url_ext
                    else: ext = '.png'
                
                final_path = local_path_base + ext.lower()
                
                with open(final_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"[DEBUG_MD] Download CONCLUÍDO. Caminho local final: {final_path}")
                return final_path
                
            except requests.exceptions.Timeout:
                print(f"[ERRO DEBUG_MD] Falha no download: Timeout excedido (30s) para {source}")
                return None
            except requests.exceptions.RequestException as e:
                print(f"[ERRO DEBUG_MD] Falha no download (Rede/HTTP {response.status_code if 'response' in locals() else 'N/A'}): {e}")
                return None
            except Exception as e:
                print(f"[ERRO DEBUG_MD] Erro inesperado ao baixar/processar asset: {e}")
                return None
        
        return local_path