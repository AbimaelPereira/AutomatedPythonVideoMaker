import os
from datetime import datetime
from typing import Optional, Dict
from libs.Storage.RemoteAssetStorage import RemoteAssetStorage
from libs.Storage.HTTPAssetStorage import HTTPAssetStorage


class RemoteAssetManager:
    """
    Gerenciador de remote assets.
    Orquestra seleção inteligente de URLs e registro automático.
    
    Configuração padrão (pode ser override em global_settings):
    - selection_mode: "least_used" (padrão) ou "random"
    - cleanup_invalid_after_days: 7 (padrão)
    """
    
    # Defaults (podem ser sobrescritos via global_settings)
    DEFAULT_SELECTION_MODE = "least_used"
    DEFAULT_CLEANUP_DAYS = 7
    
    def __init__(self, storage: Optional[RemoteAssetStorage] = None, config: Optional[Dict] = None):
        """
        Inicializa o manager.
        
        Args:
            storage: Implementação de RemoteAssetStorage (default: HTTPAssetStorage — fala com a API)
            config: Configurações opcionais do global_settings
        """
        # Storage
        if storage is None:
            storage = HTTPAssetStorage()
        
        self.storage = storage
        
        # Configurações
        self.config = config or {}
        self.selection_mode = self.config.get("selection_mode", self.DEFAULT_SELECTION_MODE)
        # self.cleanup_days = self.config.get("cleanup_invalid_after_days", self.DEFAULT_CLEANUP_DAYS)
        
        print(f"[RemoteAssetManager] ✅ Inicializado")
        print(f"[RemoteAssetManager] Modo de seleção: {self.selection_mode}")
        # print(f"[RemoteAssetManager] Limpeza após: {self.cleanup_days} dias")
        
        # Limpeza automática ao inicializar
        # self._auto_cleanup()
    
    def _auto_cleanup(self):
        """Executa limpeza automática de URLs inválidas antigas."""
        try:
            removed = self.storage.cleanup_invalid(self.cleanup_days)
            if removed > 0:
                print(f"[RemoteAssetManager] 🧹 Auto-limpeza: {removed} URLs inválidas removidas")
        except Exception as e:
            print(f"[RemoteAssetManager] ⚠️ Erro na auto-limpeza: {e}")
    
    def register_url(self, slug: str, url: str, description: str = "") -> bool:
        """
        Registra uma URL em um slug.
        Detecta tipo e extensão automaticamente.
        
        Args:
            slug: Nome do slug
            url: URL da mídia
            description: Descrição do slug (usado apenas se criar novo)
            
        Returns:
            True se registrado com sucesso
        """
        try:
            # Detecta tipo e extensão pela URL
            media_type, extension = self._detect_media_type(url)
            
            # Cria entrada de mídia
            media = {
                "url": url,
                "type": media_type,
                "extension": extension,
                "lastUsed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "invalid": False
            }
            
            # Adiciona ao storage (faz merge se já existir)
            success = self.storage.add_media(slug, media, description)
            
            if success:
                print(f"[RemoteAssetManager] ✅ URL registrada: slug='{slug}', type={media_type}")
            
            return success
            
        except Exception as e:
            print(f"[RemoteAssetManager] ❌ Erro ao registrar URL: {e}")
            return False
    
    def _detect_media_type(self, url: str) -> tuple:
        """
        Detecta tipo de mídia e extensão pela URL.
        
        Returns:
            (type, extension) - ex: ("image", "jpg")
        """
        # Pega a parte antes do '?' (remove query params)
        clean_url = url.split('?')[0].lower()
        
        # Extensão
        extension = os.path.splitext(clean_url)[1].lstrip('.')
        
        if not extension:
            extension = "unknown"
        
        # Tipo
        image_exts = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'}
        video_exts = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv'}
        
        if extension in image_exts:
            media_type = "image"
        elif extension in video_exts:
            media_type = "video"
        else:
            media_type = "unknown"
        
        return media_type, extension
    
    def select_url(self, slug: str, on_download_fail_callback=None) -> Optional[str]:
        """
        Seleciona uma URL de um slug baseado no selection_mode.
        
        Args:
            slug: Nome do slug
            on_download_fail_callback: Função chamada se URL falhar (recebe url)
            
        Returns:
            URL selecionada ou None se nenhuma disponível
        """
        media_list = self.storage.get_media_list(slug)
        
        if not media_list:
            print(f"[RemoteAssetManager] ⚠️ Slug '{slug}' não encontrado ou vazio")
            return None
        
        # Filtra apenas válidas
        valid_media = [m for m in media_list if not m.get("invalid", False)]
        
        if not valid_media:
            print(f"[RemoteAssetManager] ⚠️ Todas as URLs do slug '{slug}' estão inválidas")
            return None
        
        # Seleciona baseado no modo
        if self.selection_mode == "random":
            selected = self._select_random(valid_media)
        else:  # "least_used" (padrão)
            selected = self._select_least_used(valid_media)
        
        if selected:
            url = selected.get("url")
            print(f"[RemoteAssetManager] 🎯 URL selecionada do slug '{slug}': {url[:50]}...")
            return url
        
        return None
    
    def _select_least_used(self, media_list: list) -> Optional[Dict]:
        """Seleciona a mídia menos usada recentemente."""
        if not media_list:
            return None
        
        # Ordena por lastUsed (mais antigo primeiro)
        sorted_media = sorted(
            media_list,
            key=lambda m: m.get("lastUsed", "1900-01-01 00:00:00")
        )
        
        return sorted_media[0]
    
    def _select_random(self, media_list: list) -> Optional[Dict]:
        """Seleciona uma mídia aleatória."""
        if not media_list:
            return None
        
        import random
        return random.choice(media_list)
    
    def mark_download_success(self, url: str):
        """Marca que download foi bem-sucedido (atualiza lastUsed)."""
        self.storage.update_last_used(url)
        print(f"[RemoteAssetManager] ✅ Download bem-sucedido: {url[:50]}...")
    
    def mark_download_failed(self, url: str):
        """Marca que download falhou (marca como invalid)."""
        self.storage.mark_invalid(url)
        print(f"[RemoteAssetManager] ❌ Download falhou, URL marcada como inválida: {url[:50]}...")
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do sistema."""
        return self.storage.get_stats()
