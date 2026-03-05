import os
import base64
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import requests as http_requests
from mutagen.mp3 import MP3


def ms_to_srt_time(ms: int) -> str:
    from datetime import timedelta
    td = timedelta(milliseconds=int(ms))
    total_s = int(td.total_seconds())
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    ms_val = int(td.microseconds / 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_val:03d}"


# ==============================================================================
# Configurações por modelo: free tier e preço excedente
# ==============================================================================
MODEL_INFO = {
    "Chirp3-HD": {
        "label":            "Chirp 3 HD",
        "free_tier_chars":  1_000_000,
        "price_per_million": 30.0,
        "filter":           lambda name: "Chirp3-HD" in name,
        "api_version":      "v1beta1",       # endpoint beta
    },
    "Neural2": {
        "label":            "Neural2",
        "free_tier_chars":  1_000_000,
        "price_per_million": 16.0,
        "filter":           lambda name: "Neural2" in name,
        "api_version":      "v1",
    },
    "WaveNet": {
        "label":            "WaveNet",
        "free_tier_chars":  4_000_000,
        "price_per_million": 4.0,
        "filter":           lambda name: "Wavenet" in name,
        "api_version":      "v1",
    },
    "Standard": {
        "label":            "Standard",
        "free_tier_chars":  4_000_000,
        "price_per_million": 4.0,
        "filter":           lambda name: "Standard" in name,
        "api_version":      "v1",
    },
}

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class GoogleCloudTTS:
    """
    TTS unificado para Google Cloud Text-to-Speech — todos os modelos pt-BR.

    Modelos disponíveis via parâmetro `model`:
      - "Chirp3-HD"  → vozes Chirp 3 HD  (melhor qualidade, free 1M chars/mês)
      - "Neural2"    → vozes Neural2      (boa qualidade,    free 1M chars/mês)
      - "WaveNet"    → vozes WaveNet      (qualidade média,  free 4M chars/mês)
      - "Standard"   → vozes Standard     (básica,           free 4M chars/mês)

    Vozes Chirp 3 HD pt-BR (30 vozes):
      Femininas : Achernar, Aoede, Autonoe, Callirrhoe, Despina, Erinome,
                  Gacrux, Kore, Laomedeia, Leda, Pulcherrima, Sulafat,
                  Vindemiatrix, Zephyr
      Masculinas: Achird, Algenib, Algieba, Alnilam, Charon, Enceladus,
                  Fenrir, Iapetus, Orus, Puck, Rasalgethi, Sadachbia,
                  Sadaltager, Schedar, Umbriel, Zubenelgenubi

    Vozes Neural2 pt-BR:
      pt-BR-Neural2-A (F), pt-BR-Neural2-B (M), pt-BR-Neural2-C (F)

    Vozes WaveNet pt-BR:
      pt-BR-Wavenet-A (F), pt-BR-Wavenet-B (M), pt-BR-Wavenet-C (F),
      pt-BR-Wavenet-D (F), pt-BR-Wavenet-E (M)

    Vozes Standard pt-BR:
      pt-BR-Standard-A (F), pt-BR-Standard-B (M), pt-BR-Standard-C (F),
      pt-BR-Standard-D (F), pt-BR-Standard-E (M)
    """

    def __init__(self, params=None):
        defaults = {
            "credentials_file":        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json"),
            "model":                   "Chirp3-HD",          # modelo padrão
            "voice_id":                "pt-BR-Chirp3-HD-Charon",
            "language_code":           "pt-BR",
            "audio_format":            "mp3",
            "output_basename":         "narration",
            "text":                    None,
            "text_narration_filename": os.getenv("TEXT_NARRATION_FILE", "texto.txt"),
            # Controles de voz (suportados por Neural2, WaveNet, Standard)
            # Chirp3-HD ignora speaking_rate e pitch silenciosamente
            "speaking_rate":           float(os.getenv("GOOGLE_TTS_RATE",   1.15)),
            "pitch":                   float(os.getenv("GOOGLE_TTS_PITCH",  0.0)),
            "volume_gain_db":          float(os.getenv("GOOGLE_TTS_VOLUME", 0.0)),
            "min_word_duration":       160,
            "last_word_duration":      400,
            "show_usage_report":       True,
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)

        if self.model not in MODEL_INFO:
            raise ValueError(
                f"Modelo '{self.model}' inválido. "
                f"Use um de: {list(MODEL_INFO.keys())}"
            )

        self.text_file_path = Path(self.text_narration_filename)
        if self.text is None and self.text_file_path.exists():
            self.text = self.text_file_path.read_text(encoding="utf-8").strip()

        self._credentials = service_account.Credentials.from_service_account_file(
            self.credentials_file, scopes=SCOPES
        )

        if self.show_usage_report:
            self.usage_report()

    # ------------------------------------------------------------------
    # AUTH
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return self._credentials.token

    def _get_project_id(self) -> str:
        if getattr(self._credentials, "project_id", None):
            return self._credentials.project_id
        with open(self.credentials_file) as f:
            return json.load(f).get("project_id", "")

    def _api_url(self, version: str, endpoint: str) -> str:
        return f"https://texttospeech.googleapis.com/{version}/{endpoint}"

    # ------------------------------------------------------------------
    # RELATÓRIO DE USO — todos os modelos
    # ------------------------------------------------------------------

    def usage_report(self):
        """
        Exibe relatório de uso no mês corrente para TODOS os modelos Google TTS,
        com free tier, progresso e custo estimado de cada um.
        """
        print("\n[GoogleCloudTTS] 📊 Relatório de Uso — Google Cloud TTS (mês corrente)")
        print("═" * 62)

        try:
            token      = self._get_access_token()
            project_id = self._get_project_id()
            now            = datetime.now(timezone.utc)
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Busca série temporal de caracteres sintetizados
            # A API Monitoring exige RFC3339 com Z no final (não +00:00)
            fmt       = "%Y-%m-%dT%H:%M:%SZ"
            start_str = start_of_month.strftime(fmt)
            end_str   = now.strftime(fmt)

            # view=FULL é obrigatório (doc oficial)
            # aggregation sem groupByFields para evitar 400
            # sem crossSeriesReducer: retorna série por voz, somamos manualmente
            monitoring_params = {
                "filter":                       'metric.type="cloudtts.googleapis.com/character/count"',
                "interval.startTime":           start_str,
                "interval.endTime":             end_str,
                "aggregation.alignmentPeriod":  "2678400s",
                "aggregation.perSeriesAligner": "ALIGN_SUM",
                "view":                         "FULL",
            }

            resp = http_requests.get(
                f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries",
                params=monitoring_params,
                headers={"Authorization": f"Bearer {token}"},
            )

            # Agrupa chars por modelo
            chars_by_model = {k: 0 for k in MODEL_INFO}

            if resp.status_code == 200:
                for series in resp.json().get("timeSeries", []):
                    voice = series.get("metric", {}).get("labels", {}).get("voice_name", "")
                    total = sum(
                        int(p.get("value", {}).get("int64Value", 0))
                        for p in series.get("points", [])
                    )
                    for model_key, info in MODEL_INFO.items():
                        if info["filter"](voice):
                            chars_by_model[model_key] += total
                            break
            else:
                print(f"  ⚠️  Monitoramento indisponível (HTTP {resp.status_code}).")
                print(f"  Resposta da API: {resp.json()}")
                print(f"  Exibindo apenas limites de free tier.\n")
                # exibir reposta da api completa

            print(f"  Período: {start_of_month.strftime('%d/%m/%Y')} → {now.strftime('%d/%m/%Y')}\n")

            total_cost = 0.0
            for model_key, info in MODEL_INFO.items():
                used      = chars_by_model[model_key]
                free      = info["free_tier_chars"]
                price     = info["price_per_million"]
                pct       = min(used / free * 100, 100.0) if free > 0 else 0.0
                billable  = max(0, used - free)
                cost      = (billable / 1_000_000) * price
                remaining = max(0, free - used)
                total_cost += cost

                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))

                print(f"  ── {info['label']}")
                print(f"     Chars usados : {used:>12,}  /  {free:,} free")
                print(f"     Progresso    : [{bar}] {pct:.1f}%")
                if billable > 0:
                    print(f"     ⚠️  Excedente : {billable:>12,} chars  →  USD {cost:.4f}")
                else:
                    print(f"     Restante     : {remaining:>12,} chars livres")
                print()

            print(f"  {'─'*58}")
            if total_cost > 0:
                print(f"  💰 Custo total estimado no mês: USD {total_cost:.4f}")
            else:
                print(f"  ✅ Custo total estimado no mês: USD 0.0000  (dentro do free tier)")

        except Exception as e:
            print(f"  ⚠️  Erro ao obter dados de uso: {e}")
            print(f"\n  Limites de free tier:")
            for info in MODEL_INFO.values():
                print(f"    {info['label']:<12} {info['free_tier_chars']:>12,} chars/mês  "
                      f"| USD {info['price_per_million']:.2f}/1M excedente")

        print("═" * 62 + "\n")

    # ------------------------------------------------------------------
    # LISTAR VOZES
    # ------------------------------------------------------------------

    def list_voices(
        self,
        language: str = "pt-BR",
        gender: str = None,
        model: str = None,
        generate_audio: bool = False,
        text: str = "Olá! Esta é uma demonstração de voz.",
        output_dir: str = "test_voices/google",
    ) -> list:
        """
        Lista vozes Google Cloud TTS disponíveis.

        Args:
            language:       Idioma filtrado (default "pt-BR"). Use "" para todas.
            gender:         "masculino", "feminino" ou None para ambos.
            model:          Filtra por modelo específico: "Chirp3-HD", "Neural2",
                            "WaveNet", "Standard" ou None para todos.
            generate_audio: Se True, gera MP3 de demonstração para cada voz.
            text:           Texto narrado nas demos.
            output_dir:     Diretório dos áudios gerados.

        Returns:
            Lista de dicts com as vozes filtradas.
        """
        token = self._get_access_token()

        # Chirp3-HD usa v1beta1, demais usam v1
        api_ver = "v1beta1" if (model == "Chirp3-HD" or (not model)) else "v1"
        url = self._api_url(api_ver, "voices")
        if language:
            url += f"?languageCode={language}"

        resp = http_requests.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            raise RuntimeError(f"Erro ao listar vozes [{resp.status_code}]: {resp.text}")

        voices = resp.json().get("voices", [])

        # Filtro de modelo
        if model:
            if model not in MODEL_INFO:
                raise ValueError(f"Modelo '{model}' inválido. Use: {list(MODEL_INFO.keys())}")
            voices = [v for v in voices if MODEL_INFO[model]["filter"](v.get("name", ""))]
        else:
            # Exclui vozes que não são de nenhum modelo conhecido (ex: Studio sem pt-BR)
            known = [v for v in voices if any(
                info["filter"](v.get("name", "")) for info in MODEL_INFO.values()
            )]
            voices = known

        # Filtro de gênero
        if gender:
            g_en = "MALE" if gender.lower() in ("masculino", "male", "m") else "FEMALE"
            voices = [v for v in voices if v.get("ssmlGender", "").upper() == g_en]

        if not voices:
            print("[GoogleCloudTTS] Nenhuma voz encontrada com os filtros aplicados.")
            return []

        # Exibe agrupado por modelo
        model_label = MODEL_INFO[model]["label"] if model else "todos os modelos"
        print(f"\n[GoogleCloudTTS] 🎙️  Vozes disponíveis "
              f"({language or 'todas'}, {model_label}"
              f"{', ' + gender if gender else ''}):\n")

        # Agrupa por modelo para exibição
        grouped = {}
        for v in sorted(voices, key=lambda x: x["name"]):
            for mk, info in MODEL_INFO.items():
                if info["filter"](v["name"]):
                    grouped.setdefault(mk, []).append(v)
                    break

        for mk, vlist in grouped.items():
            info = MODEL_INFO[mk]
            print(f"  ── {info['label']} "
                  f"(free {info['free_tier_chars']//1_000_000}M chars/mês, "
                  f"USD {info['price_per_million']:.0f}/1M excedente)")
            for v in vlist:
                g    = "masculino" if v.get("ssmlGender", "").upper() == "MALE" else "feminino"
                print(f"     {v['name']:<52} {g}")
            print()

        total = sum(len(vl) for vl in grouped.values())
        print(f"  Total: {total} voz(es)\n")

        if not generate_audio:
            return voices

        os.makedirs(output_dir, exist_ok=True)
        print(f"[GoogleCloudTTS] 🔊 Gerando demos em: {output_dir}\n")

        results = []
        for v in sorted(voices, key=lambda x: x["name"]):
            voice_name = v["name"]
            g          = "masculino" if v.get("ssmlGender", "").upper() == "MALE" else "feminino"
            out_base   = os.path.join(output_dir, voice_name.replace("-", "_"))

            # Detecta modelo da voz para instanciar corretamente
            detected_model = "Chirp3-HD"
            for mk, info in MODEL_INFO.items():
                if info["filter"](voice_name):
                    detected_model = mk
                    break

            try:
                tts = GoogleCloudTTS(params={
                    "credentials_file":  self.credentials_file,
                    "model":             detected_model,
                    "voice_id":          voice_name,
                    "text":              text,
                    "output_basename":   out_base,
                    "show_usage_report": False,
                })
                result = tts.generate_audio_and_subtitles()
                print(f"  ✅ {voice_name:<52} {g:<12} → {os.path.basename(result['audio_file'])}")
                results.append({"voice": voice_name, "gender": g, "model": detected_model, **result})
                time.sleep(0.3)
            except Exception as e:
                print(f"  ❌ {voice_name:<52} Erro: {e}")

        print(f"\n[GoogleCloudTTS] Concluído. {len(results)}/{total} áudios gerados.\n")
        return results

    # ------------------------------------------------------------------
    # SÍNTESE
    # ------------------------------------------------------------------

    def _synthesize(self) -> bytes:
        if not self.text:
            raise ValueError("Nenhum texto disponível para síntese.")

        token   = self._get_access_token()
        version = MODEL_INFO[self.model]["api_version"]
        url     = self._api_url(version, "text:synthesize")

        audio_config = {"audioEncoding": "MP3", "volumeGainDb": self.volume_gain_db}

        # speaking_rate e pitch não são suportados pelo Chirp3-HD
        if self.model != "Chirp3-HD":
            audio_config["speakingRate"] = self.speaking_rate
            audio_config["pitch"]        = self.pitch

        payload = {
            "input": {"text": self.text},
            "voice": {"languageCode": self.language_code, "name": self.voice_id},
            "audioConfig": audio_config,
        }

        resp = http_requests.post(
            url, json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Erro na API Google TTS [{resp.status_code}] "
                f"(modelo={self.model}, voz={self.voice_id}): {resp.text}"
            )

        audio_content = resp.json().get("audioContent")
        if not audio_content:
            raise ValueError(f"Resposta inesperada: {resp.json()}")

        return base64.b64decode(audio_content)

    def _generate_srt_from_duration(self, audio_path: str) -> str:
        duration_ms = int(MP3(audio_path).info.length * 1000)
        words       = self.text.split()
        if not words:
            return ""

        ms_per_word = duration_ms / len(words)
        srt_path    = f"{self.output_basename}.srt"

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, word in enumerate(words):
                start_ms = int(i * ms_per_word)
                end_ms   = int((i + 1) * ms_per_word)
                if i == len(words) - 1:
                    end_ms = max(end_ms, start_ms + self.last_word_duration)
                else:
                    end_ms = max(end_ms, start_ms + self.min_word_duration)
                f.write(f"{i + 1}\n{ms_to_srt_time(start_ms)} --> {ms_to_srt_time(end_ms)}\n{word}\n\n")

        return srt_path

    def generate_audio_and_subtitles(self) -> dict:
        if not self.text:
            raise ValueError("Nenhum texto disponível para síntese.")

        out_dir = os.path.dirname(self.output_basename)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        audio_bytes = self._synthesize()
        audio_path  = f"{self.output_basename}.mp3"

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        srt_path = self._generate_srt_from_duration(audio_path)
        duration = MP3(audio_path).info.length

        print(f"[GoogleCloudTTS] ✅ {audio_path}  ({duration:.2f}s)")

        return {
            "audio_file":           audio_path,
            "subtitle_file":        srt_path,
            "audio_total_duration": duration,
        }

if __name__ == "__main__":
    tts = GoogleCloudTTS(params={
        "credentials_file": "./tokens/tts-automate-videos-20509ec7c438.json",
    })
    tts.usage_report()
    # tts.list_voices(
    #     generate_audio=True,
    #     language="pt-BR",
    #     gender="masculino",
    #     text="Olá! Esta é uma demonstração de voz.",
    # )