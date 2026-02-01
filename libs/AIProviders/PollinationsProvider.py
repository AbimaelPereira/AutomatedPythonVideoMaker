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
    Implementa sistema de fallback automático para modelos indisponíveis
    """
    
    BASE_URL = "https://gen.pollinations.ai"
    
    # Modelos de fallback para imagens (em ordem de preferência)
    IMAGE_FALLBACK_MODELS = [
        "zimage",      # Modelo padrão, rápido e de boa qualidade
        "flux",        # Alta qualidade, mais lento
        "turbo"       # Muito rápido, qualidade média
    ]
    
    # Modelos de fallback para vídeos (em ordem de preferência)
    VIDEO_FALLBACK_MODELS = [
        "veo",         # Modelo padrão do Google
        "seedance",    # Alternativa rápida
        "seedance-pro" # Versão pro se disponível
    ]
    
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
                      timeout: int = 60,
                      enable_fallback: bool = True) -> Dict[str, Any]:
        """
        Gera uma imagem usando a API Pollinations com sistema de fallback automático
        
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
            enable_fallback: Se True, tenta modelos alternativos em caso de falha
            
        Returns:
            Dict com informações da imagem gerada
        """
        # Prepara lista de modelos para tentar
        models_to_try = [model]
        
        if enable_fallback:
            # Adiciona outros modelos da lista de fallback (exceto o já usado)
            for fallback_model in self.IMAGE_FALLBACK_MODELS:
                if fallback_model != model and fallback_model not in models_to_try:
                    models_to_try.append(fallback_model)
        
        print(f"[Pollinations] 🎨 Tentando gerar imagem com modelo '{model}'")
        if enable_fallback:
            print(f"[Pollinations] 📋 Modelos de fallback disponíveis: {models_to_try[1:]}")
        
        # Tenta cada modelo em sequência
        last_error = None
        for attempt, current_model in enumerate(models_to_try, 1):
            try:
                if attempt > 1:
                    print(f"[Pollinations] 🔄 Tentativa {attempt}/{len(models_to_try)} com modelo '{current_model}'...")
                
                url = f"{self.BASE_URL}/image/{quote(prompt)}"
                
                params = {
                    "model": current_model,
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
                
                response = self.session.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                
                # Verifica se é realmente uma imagem
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image"):
                    raise ValueError(f"Resposta não é uma imagem. Content-Type: {content_type}")
                
                print(f"[Pollinations] ✅ Imagem gerada com sucesso usando modelo '{current_model}'")
                
                return {
                    "success": True,
                    "content": response.content,
                    "content_type": content_type,
                    "size": len(response.content),
                    "parameters": params,
                    "prompt": prompt,
                    "model_used": current_model,  # Indica qual modelo funcionou
                    "attempts": attempt  # Quantas tentativas foram necessárias
                }
                
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                print(f"[Pollinations] ⚠️ Falha com modelo '{current_model}': {e}")
                
                # Se não for a última tentativa, continua
                if attempt < len(models_to_try):
                    continue
                else:
                    # Última tentativa falhou
                    print(f"[Pollinations] ❌ Todos os modelos falharam após {attempt} tentativas")
                    break
            
            except ValueError as e:
                last_error = str(e)
                print(f"[Pollinations] ⚠️ Erro de validação com modelo '{current_model}': {e}")
                
                if attempt < len(models_to_try):
                    continue
                else:
                    print(f"[Pollinations] ❌ Todos os modelos falharam após {attempt} tentativas")
                    break
        
        # Se chegou aqui, todas as tentativas falharam
        return {
            "success": False,
            "error":  f"Falha em todos os modelos testados. Último erro: {last_error}",
            "parameters": params,
            "prompt": prompt,
            "models_tried": models_to_try,
            "attempts": len(models_to_try)
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
                      timeout: int = 300,
                      enable_fallback: bool = True) -> Dict[str, Any]:
        """
        Gera um vídeo usando a API Pollinations com sistema de fallback automático
        
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
            enable_fallback: Se True, tenta modelos alternativos em caso de falha
            
        Returns: 
            Dict com informações do vídeo gerado
        """
        # Prepara lista de modelos para tentar
        models_to_try = [model]
        
        if enable_fallback:
            # Adiciona outros modelos da lista de fallback (exceto o já usado)
            for fallback_model in self.VIDEO_FALLBACK_MODELS:
                if fallback_model != model and fallback_model not in models_to_try:
                    models_to_try.append(fallback_model)
        
        print(f"[Pollinations] 🎬 Tentando gerar vídeo com modelo '{model}', duração {duration}s...")
        if enable_fallback:
            print(f"[Pollinations] 📋 Modelos de fallback disponíveis: {models_to_try[1:]}")
        
        # Tenta cada modelo em sequência
        last_error = None
        for attempt, current_model in enumerate(models_to_try, 1):
            try:
                if attempt > 1:
                    print(f"[Pollinations] 🔄 Tentativa {attempt}/{len(models_to_try)} com modelo '{current_model}'...")
                
                url = f"{self.BASE_URL}/image/{quote(prompt)}"
                
                params = {
                    "model": current_model,
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
                
                response = self.session.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                
                # Verifica se é realmente um vídeo
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("video"):
                    # Log para debug
                    print(f"[Pollinations] ⚠️ Content-Type inesperado: {content_type}")
                    print(f"[Pollinations] 📝 Primeiros 200 chars da resposta:  {response.text[:200]}")
                    raise ValueError(f"Resposta não é um vídeo. Content-Type: {content_type}")
                
                print(f"[Pollinations] ✅ Vídeo gerado com sucesso usando modelo '{current_model}': {len(response.content)} bytes")
                
                return {
                    "success": True,
                    "content": response.content,
                    "content_type": content_type,
                    "size": len(response.content),
                    "parameters": params,
                    "prompt": prompt,
                    "model_used": current_model,  # Indica qual modelo funcionou
                    "attempts": attempt  # Quantas tentativas foram necessárias
                }
                
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                print(f"[Pollinations] ⚠️ Falha com modelo '{current_model}': {e}")
                
                # Se não for a última tentativa, continua
                if attempt < len(models_to_try):
                    continue
                else:
                    # Última tentativa falhou
                    print(f"[Pollinations] ❌ Todos os modelos falharam após {attempt} tentativas")
                    break
            
            except ValueError as e:
                last_error = str(e)
                print(f"[Pollinations] ⚠️ Erro de validação com modelo '{current_model}': {e}")
                
                if attempt < len(models_to_try):
                    continue
                else:
                    print(f"[Pollinations] ❌ Todos os modelos falharam após {attempt} tentativas")
                    break
        
        # Se chegou aqui, todas as tentativas falharam
        return {
            "success": False,
            "error": f"Falha em todos os modelos testados. Último erro: {last_error}",
            "parameters": params,
            "prompt": prompt,
            "models_tried": models_to_try,
            "attempts": len(models_to_try)
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