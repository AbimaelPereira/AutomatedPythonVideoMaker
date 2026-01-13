import os
import requests
import json
from urllib.parse import quote
from typing import Dict, Any, Optional, Union
from pathlib import Path

class PollinationsProvider:
    """
    Provider para integração com a API Pollinations
    Suporta geração de imagens e vídeos usando o mesmo endpoint /image/
    """
    
    BASE_URL = "https://gen.pollinations.ai"
    
    def __init__(self, api_token: Optional[str] = None):
        """
        Inicializa o provider Pollinations
        
        Args:
            api_token: Token da API.  Se None, busca em POLLINATIONS_API_TOKEN
        """
        self.api_token = api_token or os.getenv('POLLINATIONS_API_TOKEN')
        if not self.api_token:
            raise ValueError("API Token necessário.  Configure POLLINATIONS_API_TOKEN ou passe via parâmetro")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization":  f"Bearer {self.api_token}",
            "User-Agent": "AutomatedPythonVideoMaker/1.0"
        })
    
    def generate_image(self, 
                      prompt:  str,
                      model:  str = "zimage",
                      width: int = 576,
                      height: int = 1024,
                      seed: Optional[int] = None,
                      enhance: bool = False,
                      negative_prompt: str = "worst quality, blurry",
                      safe: bool = False,
                      quality: str = "medium",
                      transparent: bool = False,
                      timeout: int = 60) -> Dict[str, Any]:
        """
        Gera uma imagem usando a API Pollinations
        
        Args: 
            prompt:  Descrição da imagem desejada
            model: Modelo a usar (flux, zimage, turbo, gptimage, kontext, seedream, etc.)
            width: Largura da imagem
            height: Altura da imagem  
            seed: Seed para reproduzibilidade (opcional, -1 para random)
            enhance:  Deixar IA melhorar o prompt
            negative_prompt:  O que evitar na imagem
            safe: Filtros de conteúdo seguros
            quality:  Qualidade da imagem (low, medium, high, hd)
            transparent: Fundo transparente (apenas gptimage)
            timeout: Timeout da requisição
            
        Returns:
            Dict com informações da imagem gerada
        """
        url = f"{self.BASE_URL}/image/{quote(prompt)}"
        
        params = {
            "model": model,
            "width":  width,
            "height": height,
            "enhance": str(enhance).lower(),
            "negative_prompt": negative_prompt,
            "safe": str(safe).lower(),
            "quality": quality,
            "transparent": str(transparent).lower()
        }
        
        if seed is not None:
            params["seed"] = seed
            
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            
            # Verifica se é realmente uma imagem
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image"):
                raise ValueError(f"Resposta não é uma imagem.  Content-Type: {content_type}")
            
            return {
                "success": True,
                "content": response.content,
                "content_type": content_type,
                "size": len(response.content),
                "parameters": params,
                "prompt": prompt
            }
            
        except requests.exceptions.RequestException as e: 
            return {
                "success": False,
                "error":  str(e),
                "parameters": params,
                "prompt": prompt
            }
    
    def generate_video(self, 
                      prompt: str,
                      model: str = "veo",
                      width: int = 576,
                      height: int = 1024,
                      duration: int = 4,
                      aspectRatio: str = "9:16",
                      seed: Optional[int] = None,
                      enhance:  bool = False,
                      negative_prompt: str = "worst quality, blurry",
                      safe: bool = False,
                      audio: bool = False,
                      image: Optional[str] = None,
                      timeout: int = 300) -> Dict[str, Any]:
        """
        Gera um vídeo usando a API Pollinations (mesmo endpoint /image/)
        
        Args:
            prompt: Descrição do vídeo desejado
            model: Modelo de vídeo (veo, seedance, seedance-pro)
            width: Largura do vídeo
            height: Altura do vídeo
            duration: Duração em segundos (veo:  4,6,8; seedance: 2-10)
            aspectRatio:  Proporção do vídeo (16:9 ou 9:16)
            seed: Seed para reproduzibilidade
            enhance: Deixar IA melhorar o prompt
            negative_prompt: O que evitar no vídeo
            safe: Filtros de conteúdo seguros
            audio:  Gerar áudio para o vídeo (apenas veo)
            image: URL de imagem de referência
            timeout:  Timeout da requisição (vídeos demoram mais)
            
        Returns: 
            Dict com informações do vídeo gerado
        """
        # CORRIGIDO: Usar o mesmo endpoint /image/ para vídeos
        url = f"{self.BASE_URL}/image/{quote(prompt)}"
        
        params = {
            "model": model,
            "width":  width,
            "height": height,
            "duration": duration,
            "aspectRatio": aspectRatio,
            "enhance": str(enhance).lower(),
            "negative_prompt": negative_prompt,
            "safe": str(safe).lower(),
            "audio": str(audio).lower()
        }
        
        if seed is not None: 
            params["seed"] = seed
            
        if image: 
            params["image"] = image
            
        try: 
            print(f"[Pollinations] 🎬 Gerando vídeo com modelo '{model}', duração {duration}s...")
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            
            # Verifica se é realmente um vídeo
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("video"):
                # Log para debug
                print(f"[Pollinations] ⚠️ Content-Type inesperado: {content_type}")
                print(f"[Pollinations] 📝 Primeiros 200 chars da resposta:  {response.text[: 200]}")
                raise ValueError(f"Resposta não é um vídeo. Content-Type: {content_type}")
            
            print(f"[Pollinations] ✅ Vídeo gerado:  {len(response.content)} bytes")
            return {
                "success": True,
                "content": response.content,
                "content_type": content_type,
                "size": len(response.content),
                "parameters": params,
                "prompt": prompt
            }
            
        except requests.exceptions.RequestException as e: 
            return {
                "success": False,
                "error": str(e),
                "parameters": params,
                "prompt": prompt
            }
    
    def save_media(self, media_data: Dict[str, Any], output_path: str) -> bool:
        """
        Salva o conteúdo de mídia gerado em arquivo
        
        Args:
            media_data: Dados retornados por generate_image ou generate_video
            output_path:  Caminho onde salvar o arquivo
            
        Returns:
            True se salvo com sucesso, False caso contrário
        """
        if not media_data.get("success"):
            print(f"❌ Erro:  {media_data.get('error', 'Erro desconhecido')}")
            return False
            
        try:
            # Cria diretório se não existir
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "wb") as f:
                f.write(media_data["content"])
                
            print(f"✅ Mídia salva em:  {output_path}")
            print(f"📊 Tamanho: {media_data['size']} bytes")
            return True
            
        except Exception as e: 
            print(f"❌ Erro ao salvar arquivo: {e}")
            return False