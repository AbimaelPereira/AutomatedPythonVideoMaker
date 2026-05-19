"""
Baixa o áudio e chama o Gemini para sugerir clips.
Argumentos: url video_id min_words max_words min_duration max_duration channel_name
Saída: JSON em stdout. Logs em stderr.
"""
import sys
import json
import builtins

# Redireciona todos os prints para stderr
_print = builtins.print
builtins.print = lambda *a, **kw: _print(*a, **{**kw, 'file': sys.stderr})

url          = sys.argv[1]
video_id     = sys.argv[2]
min_words    = int(sys.argv[3])
max_words    = int(sys.argv[4])
min_duration = int(sys.argv[5])
max_duration = int(sys.argv[6])
channel_name = sys.argv[7]
transcript_file = sys.argv[8]  # caminho para arquivo com a transcrição

with open(transcript_file, 'r', encoding='utf-8') as f:
    transcription_text = f.read()

sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))
import a
a.MIN_WORDS_SCENE = min_words
a.MAX_WORDS_SCENE = max_words
a.CHANNEL_NAME    = channel_name

import os
import re
import time
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Download áudio
audio_path = a.download_audio(url, video_id)

# ── Mock: pula chamada ao Gemini e serve JSON salvo ──────────────────────────
mock_file = os.getenv('REELSCUTTER_MOCK_FILE')
if mock_file:
    sys.stderr.write(f'[MOCK] Usando resposta salva: {mock_file}\n')
    with open(mock_file, 'r', encoding='utf-8') as f:
        mock_data = json.load(f)
    clips = mock_data.get('clips', mock_data)
    builtins.print = _print
    sys.stdout.write(json.dumps({'audio_path': audio_path, 'clips': clips}) + '\n')
    sys.exit(0)
# ─────────────────────────────────────────────────────────────────────────────

# Substitui duração no prompt
prompt_text = a.PROMPT_TEMPLATE.replace(
    'entre 55 e 85 segundos',
    f'entre {min_duration} e {max_duration} segundos'
)

prompt = prompt_text.format(
    transcription=transcription_text,
    min_words=min_words,
    max_words=max_words,
)

generation_config = genai.GenerationConfig(temperature=0.2, response_mime_type='application/json')
clips = None
last_error = None

for model_name in a.GEMINI_MODELS:
    try:
        model = genai.GenerativeModel(model_name=model_name, generation_config=generation_config)
        response = model.generate_content(prompt)
        raw = response.text.strip()
        raw = re.sub(r'```(?:json)?', '', raw).strip('` \n')
        clips = json.loads(raw)
        break
    except Exception as e:
        last_error = str(e)
        time.sleep(2)

if clips is None:
    builtins.print = _print
    sys.stderr.write(f'Gemini falhou: {last_error}\n')
    sys.exit(1)

builtins.print = _print
sys.stdout.write(json.dumps({'audio_path': audio_path, 'clips': clips}) + '\n')
