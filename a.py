"""
pregacao_clipper.py
-------------------
1. Recebe URL do YouTube via terminal
2. Baixa o áudio (yt-dlp)
3. Obtém transcrição (youtube_transcript_api)
4. Envia para Gemini API (com fallback entre modelos) → retorna clips JSON
5. Para cada clip:
   - Corta o áudio (pydub)
   - Gera JSON no formato do template
"""

import os
import re
import json
import subprocess
import time
import google.generativeai as genai
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# ── CONFIGURAÇÕES ──────────────────────────────────────────────────────────────
# Número mínimo de palavras por cena (evita cenas muito curtas)
MIN_WORDS_SCENE  = 12
# Número máximo de palavras por cena
MAX_WORDS_SCENE  = 18

CHANNEL_NAME     = "devocional_com_jesus"
JSONS_DIR        = "./jsons"
TEMP_DIR         = "./temp"

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
]

_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    raise EnvironmentError("Defina GEMINI_API_KEY no ambiente.")
genai.configure(api_key=_api_key)
# ──────────────────────────────────────────────────────────────────────────────

YTDLP_BROWSER = "brave:~/snap/brave/current/.config/BraveSoftware/Brave-Browser"

PROMPT_TEMPLATE = """Voce eh um especialista em conteudo cristao viral para TikTok, YouTube Shorts e Instagram Reels voltado ao publico evangelico brasileiro.

Seu trabalho eh ler a transcricao de uma pregacao e selecionar os trechos com MAIOR potencial de viralizar — aqueles que fazem o espectador parar o scroll, sentir algo forte e compartilhar.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O QUE REALMENTE VIRALIZA NO MEIO EVANGELICO BRASILEIRO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. REVELACAO INESPERADA
   Algo que inverte o entendimento comum. O ouvinte pensa que sabe, mas o pregador muda tudo.
   Exemplo de gancho: "Todo mundo acha que Deus quer te abençoar... mas isso não é verdade."

2. CONFRONTO AMOROSO
   Toca numa ferida que as pessoas carregam em silêncio. Sem julgamento, mas sem rodeios.
   Exemplo de gancho: "Você ora, você jejua, mas continua esperando Deus mudar o que só você pode mudar."

3. PROMESSA COM AUTORIDADE
   Fe declarada com convicção, nao so explicada. O pregador NAO esta sugerindo — esta afirmando.
   Exemplo de gancho: "Deus não esqueceu de você. O que parece abandono é preparação."

4. HISTORIA OU METAFORA QUE PRENDE
   Uma ilustração poderosa que resolve em imagem o que sermão resolve em argumento.
   Exemplo de gancho: "Imagine um pai que vê o filho se afogar e não pula na água..."

5. DECLARACAO ESPIRITUAL / GUERRA
   Conteudo que as pessoas salvam, repetem e mandam para quem esta sofrendo.
   Exemplo de gancho: "Eu decreto e declaro sobre a sua vida hoje..."

6. CHAMADO URGENTE
   Convite direto a conversao, a mudanca ou a oracao. Tom de ultimato amoroso.
   Exemplo de gancho: "Se voce esta assistindo isso hoje, nao eh coincidencia."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGRAS PARA SELECAO DOS TRECHOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Duracao: entre 55 e 85 segundos por clip
- O trecho precisa ter inicio, desenvolvimento e conclusao — NUNCA corte no meio de um raciocinio
- O INICIO do trecho deve ser uma frase que prende imediatamente — nao pode comecar com introducao
- O FIM deve ser uma declaracao forte, uma conclusao ou uma virada — nao pode terminar no meio
- Se o inicio do segmento tiver uma introducao fraca (ex: "Entao como eu estava dizendo..."),
  avance para o primeiro momento forte dentro daquele intervalo de tempo
- Selecione apenas trechos com impacto REAL — prefira qualidade a quantidade

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOBRE AS CENAS (scenes_text)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

O campo "scenes_text" deve conter o texto do clip dividido em blocos de legenda.
Cada bloco deve:
- Ter entre {min_words} e {max_words} palavras
- Representar uma unidade de sentido (nao cortar no meio de uma frase)
- Ser o texto EXATO falado no audio, sem resumir ou parafrasear
- Comecar pelo primeiro momento FORTE do clip — pode ignorar introducoes fracas no inicio
- Se um segmento comecar ruim mas melhorar, inclua apenas a parte boa

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO DE RESPOSTA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Responda SOMENTE com um array JSON valido. Sem texto antes ou depois. Sem markdown. Sem explicacoes.

[
  {{
    "clip_number": 1,
    "start_time": 125.4,
    "end_time": 198.2,
    "duration_seconds": 72.8,
    "title": "Titulo chamativo, direto, em ate 60 caracteres",
    "hook": "Primeira frase exata do trecho — a que prende o espectador",
    "why_viral": "Uma frase explicando por que este trecho vai parar o scroll",
    "category": "revelacao|confronto|promessa|historia|declaracao|chamado",
    "scenes_text": [
      "Primeiro bloco de texto do clip com entre {min_words} e {max_words} palavras.",
      "Segundo bloco de texto continuando o raciocinio.",
      "Terceiro bloco finalizando com forca."
    ]
  }}
]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRANSCRICAO DA PREGACAO:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{transcription}"""


# ── HELPERS ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.upper()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text.strip())
    return text


def today_publish_at() -> str:
    now = datetime.now()
    return now.strftime("%Y-%m-%d 17:00:00")


def ensure_dirs():
    os.makedirs(JSONS_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)


# ── STEP 1: baixar áudio ──────────────────────────────────────────────────────

def download_audio(url: str, video_id: str) -> str:
    out_path = os.path.join(TEMP_DIR, f"{video_id}.mp3")
    if os.path.exists(out_path):
        print(f"[✓] Áudio já existe: {out_path}")
        return out_path

    strategies = [
        [
            "yt-dlp",
            "--cookies-from-browser", YTDLP_BROWSER,
            "--extractor-args", "youtube:player_client=default,android_vr",
            "-x", "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", out_path,
            url,
        ],
        [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android_vr",
            "-x", "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", out_path,
            url,
        ],
    ]

    last_error = None
    for i, cmd in enumerate(strategies, 1):
        print(f"[↓] Baixando áudio (estratégia {i}/{len(strategies)})...")
        try:
            subprocess.run(cmd, check=True)
            print(f"[✓] Áudio salvo: {out_path}")
            return out_path
        except subprocess.CalledProcessError as e:
            last_error = e
            print(f"    [!] Estratégia {i} falhou. Tentando próxima...")

    raise RuntimeError(f"Não foi possível baixar o áudio após {len(strategies)} tentativas. Último erro: {last_error}")


# ── STEP 2: transcrição ───────────────────────────────────────────────────────

def get_transcript(video_id: str) -> list[dict]:
    from youtube_transcript_api import YouTubeTranscriptApi
    print("[↓] Obtendo transcrição do YouTube...")
    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id, languages=["pt", "pt-BR", "en"])
        transcript = [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]
    except Exception:
        fetched = YouTubeTranscriptApi.list_transcripts(video_id) \
            .find_transcript(["pt", "pt-BR", "en"]).fetch()
        transcript = [{"text": s["text"], "start": s["start"], "duration": s["duration"]} for s in fetched]
    print(f"[✓] {len(transcript)} segmentos obtidos.")
    return transcript


def transcript_with_timestamps(transcript: list[dict]) -> str:
    lines = []
    for seg in transcript:
        start = seg["start"]
        text  = seg["text"].strip()
        lines.append(f"[{start:.1f}s] {text}")
    return "\n".join(lines)


# ── STEP 3: Gemini API ────────────────────────────────────────────────────────

def call_gemini(transcription_text: str) -> list[dict]:
    prompt = PROMPT_TEMPLATE.format(
        transcription=transcription_text,
        min_words=MIN_WORDS_SCENE,
        max_words=MAX_WORDS_SCENE,
    )

    generation_config = genai.GenerationConfig(
        temperature=0.2,
        response_mime_type="application/json",
    )

    last_error = None
    for model_name in GEMINI_MODELS:
        print(f"[↑] Enviando para Gemini ({model_name})...")
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
            )
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip("` \n")
            clips = json.loads(raw)
            print(f"[✓] {len(clips)} clips identificados ({model_name}).")
            return clips
        except Exception as e:
            last_error = e
            print(f"    [!] {model_name} falhou: {e}. Tentando próximo...")
            time.sleep(2)

    raise RuntimeError(f"Todos os modelos Gemini falharam. Último erro: {last_error}")


# ── STEP 4: cortar áudio ──────────────────────────────────────────────────────

def cut_audio(source_mp3: str, start: float, end: float, out_path: str):
    from pydub import AudioSegment
    audio = AudioSegment.from_mp3(source_mp3)
    segment = audio[int(start * 1000): int(end * 1000)]
    segment.export(out_path, format="mp3")


# ── STEP 5: converter scenes_text → scenes JSON ───────────────────────────────

def scenes_from_text_blocks(scenes_text: list[str]) -> list[dict]:
    """
    Converte a lista de blocos de texto retornada pelo Gemini em scenes JSON.
    Garante mínimo de MIN_WORDS_SCENE por cena — mescla blocos curtos com o próximo.
    """
    # Mescla blocos abaixo do mínimo de palavras com o bloco seguinte
    merged: list[str] = []
    buffer = ""

    for block in scenes_text:
        block = block.strip()
        if not block:
            continue
        combined = (buffer + " " + block).strip() if buffer else block
        word_count = len(combined.split())
        if word_count < MIN_WORDS_SCENE:
            buffer = combined  # ainda curto, continua acumulando
        else:
            merged.append(combined)
            buffer = ""

    if buffer:
        # último bloco curto — anexa ao anterior se existir
        if merged:
            merged[-1] = (merged[-1] + " " + buffer).strip()
        else:
            merged.append(buffer)

    scenes = []
    for i, text in enumerate(merged, 1):
        scenes.append({
            "id": str(i).zfill(4),
            "narration": {
                "text": text,
                "subtitles": True,
            }
        })

    return scenes


def build_json(clip: dict, audio_filename: str) -> dict:
    title_clean = clip["title"]
    slug = slugify(title_clean)
    yt_title = f"🙏 {title_clean.upper()} 🙏"

    # Usa scenes_text do Gemini como fonte principal
    scenes_text = clip.get("scenes_text", [])

    if scenes_text:
        scenes = scenes_from_text_blocks(scenes_text)
    else:
        # fallback: hook como cena única (Gemini não retornou scenes_text)
        hook = clip.get("hook", "")
        scenes = [{"id": "0001", "narration": {"text": hook, "subtitles": True}}]
        print(f"    [!] scenes_text ausente — usando hook como fallback para clip {clip.get('clip_number')}")

    category_tags = {
        "revelacao": ["revelacao biblica", "insight espiritual"],
        "confronto":  ["confronto amoroso", "reflexao crista"],
        "promessa":   ["promessa de deus", "versiculo biblico"],
        "historia":   ["testemunho", "historia de fe"],
        "declaracao": ["declaracao de fe", "guerra espiritual"],
        "chamado":    ["chamado", "evangelismo"],
    }
    extra_tags = category_tags.get(clip.get("category", ""), [])

    return {
        "slug": slug,
        "channel_name": CHANNEL_NAME,
        "output_ratio": "9:16",
        # FIX: global_settings (sem //) para que o TTS local seja aplicado corretamente
        "global_settings": {
            "tts": {
                "provider": "local_file",
                "audio_file": f"./temp/{audio_filename}"
            }
        },
        "scenes": scenes,
        # youtube com // = comentado, não sobe automaticamente (ajuste conforme necessário)
        "youtube": {
            "title": yt_title,
            "tags": [
                "devocional com jesus",
                "palavra de deus",
                "fe",
                "biblia",
                "versiculo biblico",
                *extra_tags
            ],
            "description": (
                f'"{clip.get("hook", "")}"\n\n'
                f'📖 Leia a Biblia diariamente.\n'
                f'🙏 Inscreva-se para receber a Palavra de Deus todo dia.'
            ),
            "publish_at": today_publish_at()
        }
    }


# ── MAIN ──────────────────────────────────────────────────────────────────────

def extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"shorts/([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    raise ValueError(f"Não foi possível extrair o video_id de: {url}")


def main():
    ensure_dirs()

    url = input("Cole o link do vídeo do YouTube: ").strip()
    video_id = extract_video_id(url)
    print(f"[i] Video ID: {video_id}")

    # 1. baixar áudio
    source_mp3 = download_audio(url, video_id)

    # 2. transcrição
    transcript = get_transcript(video_id)
    transcription_text = transcript_with_timestamps(transcript)

    # 3. Gemini
    clips = call_gemini(transcription_text)

    all_json = []

    for clip in clips:
        n     = clip["clip_number"]
        start = clip["start_time"]
        end   = clip["end_time"]
        title = clip["title"]
        slug  = slugify(title)

        # 4. cortar áudio
        clip_filename = f"clip_{n:02d}_{slug[:40]}.mp3"
        clip_path     = os.path.join(TEMP_DIR, clip_filename)
        print(f"[✂] Cortando clip {n}: {start:.1f}s → {end:.1f}s ...")
        try:
            cut_audio(source_mp3, start, end, clip_path)
            print(f"    Salvo: {clip_path}")
        except Exception as e:
            print(f"    [!] Erro ao cortar: {e}")

        # 5. gerar JSON
        doc = build_json(clip, clip_filename)
        all_json.append(doc)

        print(f"    Cenas geradas: {len(doc['scenes'])}")
        for s in doc["scenes"]:
            words = len(s["narration"]["text"].split())
            print(f"      [{s['id']}] {words} palavras: {s['narration']['text'][:60]}...")

    # salvar JSON consolidado
    consolidated_path = os.path.join(JSONS_DIR, f"{video_id}.json")
    with open(consolidated_path, "w", encoding="utf-8") as f:
        json.dump(all_json, f, ensure_ascii=False, indent=2)

    print(f"\n[✓] Concluído! {len(clips)} clips gerados.")
    print(f"[✓] JSON consolidado: {consolidated_path}")


if __name__ == "__main__":
    main()
