import re
import os
import time
import requests
from typing import Dict, Any, Optional
from pathlib import Path


class ModelScopeProvider:
    """
    Provider para a API-Inference do ModelScope (Alibaba).

    Serve o Z-Image-Turbo — o mesmo modelo que o Pollinations expoe como
    "zimage" — com duas diferencas que importam para um canal de estilo fixo:

      1. DIMENSAO EXATA. O Pollinations arredonda para multiplos de 32
         (1284 -> 1280, 857 -> 864); aqui 1284x1440 e 857x1440 voltam exatos.
         Medido em 21/09/2026.
      2. API ASSINCRONA. O POST so' enfileira e devolve um task_id; a imagem
         sai de um poll. Por isso uma geracao leva ~25s, contra a resposta
         direta do Pollinations.

    CONTA E COBRANCA
    ----------------
    Exige conta em modelscope.AI (o host .cn e' outra plataforma, com contas
    separadas: um token .ai recebe do .cn um 401 generico de "token invalido")
    e binding com a Alibaba Cloud.

    Ha' cota gratuita — 2.000 chamadas/dia na conta, com teto por modelo — e
    estourar devolve 429. O que NAO esta' confirmado e' se, com pagamento
    vinculado, passar da cota cobra em vez de recusar. Um video do canal usa
    ~135 imagens, perto do teto por modelo. Confira a fatura na Alibaba Cloud
    antes de usar isto em volume.
    """

    BASE_URL = "https://api-inference.modelscope.ai"
    DEFAULT_MODEL = "Tongyi-MAI/Z-Image-Turbo"

    # O Z-Image-Turbo e' destilado: poucos passos e guidance baixo e' a
    # configuracao CORRETA, nao uma economia. Valores altos degradam a imagem.
    #
    # A model card pede guidance 0.0, mas esta API valida o campo em
    # [1.0, 20.0] e devolve 400 para 0.0 — entao 1.0, o mais baixo aceito.
    DEFAULT_GUIDANCE = 1.0
    DEFAULT_STEPS = 9

    POLL_INTERVAL = 5     # intervalo do poll, conforme a doc da API
    MAX_SIDE = 2048       # teto por lado medido no Pollinations; nao reavaliado aqui

    @staticmethod
    def disponivel() -> bool:
        """Ha' token configurado? Usado pelo setup para nao registrar a` toa."""
        return bool(os.getenv('MODELSCOPE_TOKEN'))

    def __init__(self, api_token: Optional[str] = None):
        """
        Args:
            api_token: Token do ModelScope. Se None, busca em MODELSCOPE_TOKEN.
        """
        self.api_token = api_token or os.getenv('MODELSCOPE_TOKEN')
        if not self.api_token:
            raise ValueError(
                "ModelScope exige um token: defina MODELSCOPE_TOKEN ou passe "
                "api_token. Gere em modelscope.ai > Access Tokens.")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "User-Agent": "AutomatedPythonVideoMaker/1.0",
        })

    def generate_image(self,
                       prompt: str,
                       model: str = DEFAULT_MODEL,
                       width: int = 1024,
                       height: int = 1024,
                       seed: Optional[int] = None,
                       guidance: float = DEFAULT_GUIDANCE,
                       steps: int = DEFAULT_STEPS,
                       negative_prompt: Optional[str] = None,
                       timeout: int = 300,
                       **_ignorados) -> Dict[str, Any]:
        """
        Gera uma imagem. Devolve o mesmo dict do PollinationsProvider, para ser
        substituivel sem mexer em quem chama.

        Args:
            prompt: Descricao da imagem
            model: Id do modelo no ModelScope. "zimage" e' aceito como apelido.
            width, height: Dimensoes exatas (nao ha' arredondamento)
            seed: Seed para reproduzibilidade. NAO reproduz o seed do
                  Pollinations — implementacoes diferentes, imagens diferentes.
            guidance: [1.0, 20.0]; ver DEFAULT_GUIDANCE
            steps: Passos de difusao
            negative_prompt: O que evitar
            timeout: Teto total da geracao, incluindo o poll

        `**_ignorados` absorve os kwargs so' do Pollinations (enhance, safe,
        quality, transparent, enable_fallback...) para que a troca de provider
        nao quebre chamadas existentes. Aqui nao ha' fallback de modelo: se a
        geracao falhar ela FALHA, em vez de sair em outro estilo.

        Returns:
            Dict com success, content (bytes), content_type, size, ...
        """
        # "zimage" e' o alias do Pollinations para o mesmo modelo.
        if model in ("zimage", "z-image", None, ""):
            model = self.DEFAULT_MODEL

        params: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": f"{width}x{height}",
            "guidance": guidance,
            "steps": steps,
        }
        if seed is not None:
            params["seed"] = seed
        if negative_prompt:
            params["negative_prompt"] = negative_prompt

        print(f"[ModelScope] 🎨 Gerando {width}x{height} com '{model}'...")
        inicio = time.time()

        try:
            url = self._enfileirar(params, timeout)
            content = self._baixar(url, timeout)
        except (requests.exceptions.RequestException, RuntimeError) as e:
            print(f"[ModelScope] ❌ Falhou: {e}")
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is None:
                m = re.match(r"HTTP (\d{3})", str(e))
                status = int(m.group(1)) if m else None
            return {
                "success": False,
                "error": str(e),
                "status_code": status,
                "parameters": params,
                "prompt": prompt,
            }

        print(f"[ModelScope] ✅ Imagem gerada em {time.time() - inicio:.0f}s "
              f"({len(content) / 1024:.0f} KB)")
        return {
            "success": True,
            "content": content,
            "content_type": "image/png",
            "size": len(content),
            "parameters": params,
            "prompt": prompt,
            "model_used": model,
            "attempts": 1,
        }

    def _enfileirar(self, params: Dict[str, Any], timeout: int) -> str:
        """POST + poll. Devolve a URL da imagem pronta.

        O header X-ModelScope-Async-Mode e' o que faz a resposta vir como
        task_id; sem ele a API tenta responder sincrona e estoura em imagem
        grande.
        """
        r = self.session.post(
            f"{self.BASE_URL}/v1/images/generations",
            json=params,
            headers={"X-ModelScope-Async-Mode": "true"},
            timeout=60,
        )
        self._erro_legivel(r)
        task_id = r.json().get("task_id")
        if not task_id:
            raise RuntimeError(f"resposta sem task_id: {r.text[:200]}")

        limite = time.time() + timeout
        while time.time() < limite:
            time.sleep(self.POLL_INTERVAL)
            s = self.session.get(
                f"{self.BASE_URL}/v1/tasks/{task_id}",
                headers={"X-ModelScope-Task-Type": "image_generation"},
                timeout=60,
            )
            self._erro_legivel(s)
            dados = s.json()
            estado = dados.get("task_status")
            if estado == "SUCCEED":
                urls = dados.get("output_images") or []
                if not urls:
                    raise RuntimeError(f"SUCCEED sem imagem: {dados}")
                return urls[0]
            if estado == "FAILED":
                raise RuntimeError(f"task falhou: {dados}")

        raise RuntimeError(f"timeout de {timeout}s no task {task_id}")

    def _baixar(self, url: str, timeout: int) -> bytes:
        r = self.session.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content

    @staticmethod
    def _erro_legivel(r: requests.Response):
        """Levanta com a mensagem da API, nao so' o codigo HTTP.

        A API explica no corpo o que falta (binding da conta pendente,
        guidance fora da faixa, cota estourada); um raise_for_status cru
        esconde justamente isso.
        """
        if r.status_code < 400:
            return
        try:
            msg = r.json().get("errors", {}).get("message") or r.text[:300]
        except ValueError:
            msg = r.text[:300]
        raise RuntimeError(f"HTTP {r.status_code}: {msg}")

    def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Nao implementado: este provider serve so' imagem."""
        return {
            "success": False,
            "error": "ModelScopeProvider nao gera video; use o Pollinations.",
            "prompt": prompt,
        }

    def save_media(self, media_data: Dict[str, Any], output_path: str) -> bool:
        """Salva o conteudo gerado em arquivo."""
        if not media_data.get("success"):
            print(f"❌ Erro: {media_data.get('error', 'Erro desconhecido')}")
            return False

        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(media_data["content"])
            print(f"✅ Mídia salva em: {output_path}")
            print(f"📊 Tamanho: {media_data['size']} bytes")
            return True
        except OSError as e:
            print(f"❌ Erro ao salvar arquivo: {e}")
            return False
