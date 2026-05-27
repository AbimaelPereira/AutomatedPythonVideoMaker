import os
import re
import json
import time
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
]


class GeminiProvider:
    def __init__(self, api_key: str = None, models: list[str] = None, retry_delay: float = 2.0):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise EnvironmentError("Defina GEMINI_API_KEY no ambiente.")

        self.client = genai.Client(api_key=key)
        self.models = models or MODELS
        self.retry_delay = retry_delay

    def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        """Envia um prompt e retorna o texto da resposta. Tenta os modelos em sequência."""
        config = types.GenerateContentConfig(temperature=temperature)
        last_error = None

        for model_name in self.models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                return response.text.strip()
            except Exception as e:
                last_error = e
                time.sleep(self.retry_delay)

        raise RuntimeError(f"Todos os modelos Gemini falharam. Último erro: {last_error}")

    def generate_json(self, prompt: str, temperature: float = 0.2) -> any:
        """Envia um prompt e retorna o resultado já parseado como JSON."""
        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
        )
        last_error = None

        for model_name in self.models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                raw = response.text.strip()
                raw = re.sub(r"```(?:json)?", "", raw).strip("` \n")
                return json.loads(raw)
            except Exception as e:
                last_error = e
                time.sleep(self.retry_delay)

        raise RuntimeError(f"Todos os modelos Gemini falharam. Último erro: {last_error}")
