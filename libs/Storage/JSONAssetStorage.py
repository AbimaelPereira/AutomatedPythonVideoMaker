import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
from libs.Storage.RemoteAssetStorage import RemoteAssetStorage


class JSONAssetStorage(RemoteAssetStorage):
    """
    Implementação JSON do armazenamento de remote assets.
    Salva em arquivo JSON local no formato:
    [
        {
            "slug": "nome_slug",
            "description": "Descrição opcional",
            "media": [
                {
                    "url": "https://...",
                    "type": "image",
                    "extension": "jpg",
                    "lastUsed": "2024-06-01 12:00:00",
                    "invalid": false
                }
            ]
        }
    ]
    """
    
    def __init__(self, json_path: str = "cache/remote_assets.json"):
        """
        Inicializa o storage JSON.
        
        Args:
            json_path: Caminho para o arquivo JSON
        """
        self.json_path = Path(json_path)
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Carrega ou inicializa
        self._data = self._load()
    
    def _load(self) -> List[Dict]:
        """Carrega dados do arquivo JSON."""
        if self.json_path.exists():
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[JSONAssetStorage] ⚠️ Erro ao carregar {self.json_path}: {e}")
                return []
        return []
    
    def _save(self):
        """Salva dados no arquivo JSON."""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[JSONAssetStorage] ❌ Erro ao salvar {self.json_path}: {e}")
    
    def get_slug(self, slug: str) -> Optional[Dict]:
        """Retorna dados completos de um slug."""
        for entry in self._data:
            if entry.get("slug") == slug:
                return entry
        return None
    
    def get_media_list(self, slug: str) -> List[Dict]:
        """Retorna lista de mídias de um slug."""
        entry = self.get_slug(slug)
        if entry:
            return entry.get("media", [])
        return []
    
    def add_media(self, slug: str, media: Dict, description: str = "") -> bool:
        """
        Adiciona mídia a um slug (cria slug se não existir).
        Faz merge se URL já existir.
        """
        try:
            # Busca ou cria slug
            entry = self.get_slug(slug)
            
            if entry is None:
                # Cria novo slug
                entry = {
                    "slug": slug,
                    "description": description,
                    "media": []
                }
                self._data.append(entry)
                print(f"[JSONAssetStorage] 📁 Criado novo slug: {slug}")
            
            # Verifica se URL já existe
            url = media.get("url")
            existing_media = None
            
            for m in entry["media"]:
                if m.get("url") == url:
                    existing_media = m
                    break
            
            if existing_media:
                # Merge: atualiza lastUsed e reseta invalid
                existing_media["lastUsed"] = media.get("lastUsed", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                existing_media["invalid"] = False  # Reset invalid ao re-registrar
                print(f"[JSONAssetStorage] 🔄 URL atualizada no slug '{slug}': {url[:50]}...")
            else:
                # Adiciona nova mídia
                entry["media"].append(media)
                print(f"[JSONAssetStorage] ➕ URL adicionada ao slug '{slug}': {url[:50]}...")
            
            self._save()
            return True
            
        except Exception as e:
            print(f"[JSONAssetStorage] ❌ Erro ao adicionar mídia: {e}")
            return False
    
    def mark_invalid(self, url: str) -> bool:
        """Marca URL como inválida em todos os slugs onde aparecer."""
        found = False
        
        for entry in self._data:
            for media in entry.get("media", []):
                if media.get("url") == url:
                    media["invalid"] = True
                    found = True
                    print(f"[JSONAssetStorage] ⚠️ URL marcada como inválida: {url[:50]}...")
        
        if found:
            self._save()
        
        return found
    
    def update_last_used(self, url: str) -> bool:
        """Atualiza timestamp lastUsed de uma URL."""
        found = False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for entry in self._data:
            for media in entry.get("media", []):
                if media.get("url") == url:
                    media["lastUsed"] = now
                    found = True
        
        if found:
            self._save()
        
        return found
    
    def cleanup_invalid(self, days_threshold: int = 7) -> int:
        """
        Remove URLs com lastUsed mais antigo que X dias E que sejam invalid.
        """
        removed_count = 0
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        
        for entry in self._data:
            media_list = entry.get("media", [])
            new_media_list = []
            
            for media in media_list:
                # Só remove se for invalid E antigo
                if media.get("invalid", False):
                    try:
                        last_used_str = media.get("lastUsed", "")
                        last_used_dt = datetime.strptime(last_used_str, "%Y-%m-%d %H:%M:%S")
                        
                        if last_used_dt < cutoff_date:
                            # Remove
                            removed_count += 1
                            print(f"[JSONAssetStorage] 🗑️ Removida URL inválida antiga: {media.get('url', '')[:50]}...")
                            continue
                    except Exception as e:
                        print(f"[JSONAssetStorage] ⚠️ Erro ao parsear data: {e}")
                
                # Mantém
                new_media_list.append(media)
            
            entry["media"] = new_media_list
        
        if removed_count > 0:
            self._save()
            print(f"[JSONAssetStorage] 🧹 Limpeza concluída: {removed_count} URLs removidas")
        
        return removed_count
    
    def url_exists(self, slug: str, url: str) -> bool:
        """Verifica se URL já existe em um slug específico."""
        media_list = self.get_media_list(slug)
        
        for media in media_list:
            if media.get("url") == url:
                return True
        
        return False
    
    def list_all_slugs(self) -> List[str]:
        """Lista todos os slugs disponíveis."""
        return [entry.get("slug") for entry in self._data if entry.get("slug")]
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do storage."""
        total_slugs = len(self._data)
        total_media = sum(len(entry.get("media", [])) for entry in self._data)
        invalid_count = 0
        
        for entry in self._data:
            for media in entry.get("media", []):
                if media.get("invalid", False):
                    invalid_count += 1
        
        return {
            "total_slugs": total_slugs,
            "total_media": total_media,
            "invalid_media": invalid_count,
            "valid_media": total_media - invalid_count
        }
