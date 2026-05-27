from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class RemoteAssetStorage(ABC):
    """
    Interface abstrata para armazenamento de remote assets.
    Permite migração futura para MongoDB ou outros bancos.
    """
    
    @abstractmethod
    def get_slug(self, slug: str) -> Optional[Dict]:
        """
        Retorna dados completos de um slug.
        
        Returns:
            Dict com estrutura: {"slug": str, "description": str, "media": List[Dict]}
            ou None se não existir
        """
        pass
    
    @abstractmethod
    def get_media_list(self, slug: str) -> List[Dict]:
        """
        Retorna lista de mídias de um slug.
        
        Returns:
            Lista de dicts com: url, type, extension, lastUsed, invalid
        """
        pass
    
    @abstractmethod
    def add_media(self, slug: str, media: Dict, description: str = "") -> bool:
        """
        Adiciona mídia a um slug (cria slug se não existir).
        
        Args:
            slug: Nome do slug
            media: Dict com url, type, extension, lastUsed, invalid
            description: Descrição do slug (usado apenas se criar novo)
            
        Returns:
            True se adicionado com sucesso
        """
        pass
    
    @abstractmethod
    def mark_invalid(self, url: str) -> bool:
        """
        Marca URL como inválida em todos os slugs onde aparecer.
        
        Returns:
            True se encontrou e marcou
        """
        pass
    
    @abstractmethod
    def update_last_used(self, url: str) -> bool:
        """
        Atualiza timestamp lastUsed de uma URL.
        
        Returns:
            True se encontrou e atualizou
        """
        pass
    
    @abstractmethod
    def cleanup_invalid(self, days_threshold: int = 7) -> int:
        """
        Remove URLs marcadas como invalid há mais de X dias.
        
        Args:
            days_threshold: Dias desde lastUsed para remover
            
        Returns:
            Quantidade de URLs removidas
        """
        pass
    
    @abstractmethod
    def url_exists(self, slug: str, url: str) -> bool:
        """
        Verifica se URL já existe em um slug específico.
        
        Returns:
            True se já existe
        """
        pass
    
    @abstractmethod
    def list_all_slugs(self) -> List[str]:
        """
        Lista todos os slugs disponíveis.
        
        Returns:
            Lista de nomes de slugs
        """
        pass
