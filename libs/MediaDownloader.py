import os
import requests
import mimetypes
import hashlib 

class MediaDownloader:
    """
    Classe utilitária para baixar e armazenar em cache ativos de mídia externos (imagens, vídeos).
    MODIFICADO: Agora sempre baixa de novo e salva em diretório específico da cena/vídeo.
    """
    
    @staticmethod
    def resolve_source_path(source: str, temp_dir: str = "output/temp", 
                          on_success_callback=None, on_fail_callback=None) -> str | None:
        """
        Verifica se a fonte é uma URL. Se for, SEMPRE baixa e salva em temp_dir.
        Caso contrário, retorna o caminho de origem original (assumido como local).
        
        Args:
            source: URL ou caminho local
            temp_dir: Diretório onde salvar (pasta da cena/vídeo)
            on_success_callback: Função chamada após download bem-sucedido (recebe url)
            on_fail_callback: Função chamada se download falhar (recebe url)
        
        Returns:
            Caminho local do arquivo ou None se falhar
        """
        if not source:
            print("[MediaDownloader] Fonte (source) ausente.")
            return None
        
        local_path = source
        os.makedirs(temp_dir, exist_ok=True)

        if source.lower().startswith(("http:", "https:")):
            print(f"[MediaDownloader] URL detectada: {source[:60]}...")
            try:
                # 1. Gera nome único baseado no hash da URL
                url_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()[:16]
                local_path_base = os.path.join(temp_dir, f"asset_{url_hash}")

                # 2. Verifica se JÁ EXISTE neste diretório específico (reutiliza entre cenas do mesmo vídeo)
                cached_path = None
                for ext in ['.png', '.jpg', '.jpeg', '.mp4', '.mov', '.webm', '.gif']:
                    test_path = local_path_base + ext
                    if os.path.exists(test_path) and os.path.getsize(test_path) > 0:
                        cached_path = test_path
                        break
                        
                if cached_path:
                    print(f"[MediaDownloader] ✅ Arquivo já existe nesta pasta: {os.path.basename(cached_path)}")
                    
                    # Callback de sucesso (reutilização também é sucesso)
                    if on_success_callback:
                        on_success_callback(source)
                    
                    return cached_path
                
                # 3. Download (sempre faz se não estiver nesta pasta)
                print(f"[MediaDownloader] 📥 Baixando para: {temp_dir}...")
                response = requests.get(source, timeout=30)
                response.raise_for_status() 

                # 4. Determina extensão e salva
                content_type = response.headers.get('content-type', '')
                ext = mimetypes.guess_extension(content_type)
                
                if not ext:
                    url_ext = os.path.splitext(source.split('?')[0])[-1]
                    if url_ext: 
                        ext = url_ext
                    else: 
                        ext = '.png'
                
                final_path = local_path_base + ext.lower()
                
                with open(final_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"[MediaDownloader] ✅ Download concluído: {os.path.basename(final_path)}")
                
                # Callback de sucesso
                if on_success_callback:
                    on_success_callback(source)
                
                return final_path
                
            except requests.exceptions.Timeout:
                print(f"[MediaDownloader] ❌ Timeout (30s): {source[:60]}...")
                if on_fail_callback:
                    on_fail_callback(source)
                return None
                
            except requests.exceptions.RequestException as e:
                status = response.status_code if 'response' in locals() else 'N/A'
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
