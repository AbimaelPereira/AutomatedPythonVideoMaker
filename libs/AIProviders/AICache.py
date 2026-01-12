import os
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

class AICache:
    """
    Sistema de cache para conteúdo gerado por IA
    Evita regerar o mesmo conteúdo múltiplas vezes
    """
    
    def __init__(self, cache_dir: str, max_age_days: int = 30):
        """
        Inicializa o cache de IA
        
        Args:
            cache_dir: Diretório onde armazenar arquivos em cache
            max_age_days:  Dias para manter arquivos no cache
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.metadata_file = self. cache_dir / "cache_metadata.json"
        self.max_age_days = max_age_days
        
        # Carregar ou criar metadata
        self.metadata = self._load_metadata()
        
        # Limpeza automática de arquivos antigos
        self._cleanup_old_files()
    
    def _load_metadata(self) -> Dict[str, Any]: 
        """Carrega metadata do cache"""
        if self.metadata_file.exists():
            try: 
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json. load(f)
            except Exception as e:
                print(f"[AICache] ⚠️ Erro ao carregar metadata: {e}")
        
        return {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "entries": {}
        }
    
    def _save_metadata(self):
        """Salva metadata do cache"""
        try:
            self.metadata["last_updated"] = datetime.now().isoformat()
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json. dump(self.metadata, f, indent=2, ensure_ascii=False)
        except Exception as e: 
            print(f"[AICache] ❌ Erro ao salvar metadata: {e}")
    
    def _cleanup_old_files(self):
        """Remove arquivos antigos do cache"""
        cutoff_date = datetime.now() - timedelta(days=self.max_age_days)
        removed_count = 0
        
        entries_to_remove = []
        
        for cache_key, entry in self. metadata. get("entries", {}).items():
            try:
                created_date = datetime. fromisoformat(entry. get("created", ""))
                if created_date < cutoff_date:
                    # Remover arquivo físico
                    file_path = Path(entry. get("file_path", ""))
                    if file_path.exists():
                        file_path.unlink()
                        removed_count += 1
                    
                    entries_to_remove. append(cache_key)
            except Exception as e:
                print(f"[AICache] ⚠️ Erro ao limpar entrada {cache_key}: {e}")
                entries_to_remove. append(cache_key)
        
        # Remover entradas do metadata
        for key in entries_to_remove:
            del self.metadata["entries"][key]
        
        if removed_count > 0:
            print(f"[AICache] 🧹 Removidos {removed_count} arquivos antigos do cache")
            self._save_metadata()
    
    def _generate_file_path(self, cache_key: str, content_type: str) -> Path:
        """Gera caminho do arquivo baseado na chave e tipo"""
        extension = "png" if content_type == "image" else "mp4"
        filename = f"{cache_key}.{extension}"
        return self. cache_dir / filename
    
    def get(self, cache_key: str, content_type: str) -> Optional[str]:
        """
        Recupera arquivo do cache
        
        Args: 
            cache_key: Chave única do conteúdo
            content_type:  Tipo do conteúdo (image/video)
            
        Returns: 
            Caminho do arquivo se encontrado, None caso contrário
        """
        entry = self.metadata. get("entries", {}).get(cache_key)
        if not entry:
            return None
        
        file_path = Path(entry.get("file_path", ""))
        
        # Verificar se arquivo ainda existe
        if not file_path. exists():
            print(f"[AICache] ⚠️ Arquivo cache perdido: {cache_key}")
            # Remover entrada inválida
            del self.metadata["entries"][cache_key]
            self._save_metadata()
            return None
        
        # Atualizar último acesso
        entry["last_accessed"] = datetime.now().isoformat()
        entry["access_count"] = entry.get("access_count", 0) + 1
        self._save_metadata()
        
        print(f"[AICache] ✅ Cache hit para {cache_key}")
        return str(file_path)
    
    def store(self, cache_key: str, source_file_path: str, content_type:  str, metadata: Dict[str, Any] = None) -> bool:
        """
        Armazena arquivo no cache
        
        Args: 
            cache_key:  Chave única do conteúdo
            source_file_path: Caminho do arquivo a ser cacheado
            content_type: Tipo do conteúdo (image/video)
            metadata: Metadados adicionais
            
        Returns:
            True se armazenado com sucesso
        """
        try:
            source_path = Path(source_file_path)
            if not source_path. exists():
                print(f"[AICache] ❌ Arquivo fonte não existe: {source_file_path}")
                return False
            
            # Gerar caminho de destino
            dest_path = self._generate_file_path(cache_key, content_type)
            
            # Copiar arquivo
            shutil.copy2(source_path, dest_path)
            
            # Salvar metadata
            entry = {
                "cache_key": cache_key,
                "content_type": content_type,
                "file_path": str(dest_path),
                "original_path": str(source_path),
                "created": datetime.now().isoformat(),
                "last_accessed": datetime. now().isoformat(),
                "access_count": 1,
                "file_size": dest_path.stat().st_size,
                "metadata":  metadata or {}
            }
            
            self.metadata. setdefault("entries", {})[cache_key] = entry
            self._save_metadata()
            
            print(f"[AICache] 💾 Arquivo cacheado: {cache_key} -> {dest_path. name}")
            return True
            
        except Exception as e: 
            print(f"[AICache] ❌ Erro ao armazenar no cache: {e}")
            return False
    
    def exists(self, cache_key: str) -> bool:
        """Verifica se uma chave existe no cache"""
        return cache_key in self.metadata.get("entries", {})
    
    def remove(self, cache_key: str) -> bool:
        """Remove entrada específica do cache"""
        entry = self.metadata. get("entries", {}).get(cache_key)
        if not entry:
            return False
        
        try:
            file_path = Path(entry. get("file_path", ""))
            if file_path.exists():
                file_path.unlink()
            
            del self.metadata["entries"][cache_key]
            self._save_metadata()
            
            print(f"[AICache] 🗑️ Cache removido: {cache_key}")
            return True
            
        except Exception as e:
            print(f"[AICache] ❌ Erro ao remover cache: {e}")
            return False
    
    def clear_all(self) -> int:
        """Limpa todo o cache"""
        removed_count = 0
        
        for cache_key in list(self.metadata.get("entries", {}).keys()):
            if self.remove(cache_key):
                removed_count += 1
        
        print(f"[AICache] 🧹 Cache limpo completamente:  {removed_count} arquivos removidos")
        return removed_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache"""
        entries = self.metadata. get("entries", {})
        total_size = sum(entry. get("file_size", 0) for entry in entries.values())
        
        stats = {
            "total_entries": len(entries),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
            "max_age_days": self.max_age_days
        }
        
        # Estatísticas por tipo
        type_stats = {}
        for entry in entries.values():
            content_type = entry.get("content_type", "unknown")
            if content_type not in type_stats: 
                type_stats[content_type] = {"count": 0, "size_bytes": 0}
            
            type_stats[content_type]["count"] += 1
            type_stats[content_type]["size_bytes"] += entry.get("file_size", 0)
        
        stats["by_type"] = type_stats
        return stats
    
    def list_entries(self, content_type: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Lista entradas do cache"""
        entries = self. metadata.get("entries", {})
        
        if content_type:
            return {k: v for k, v in entries.items() if v.get("content_type") == content_type}
        
        return entries