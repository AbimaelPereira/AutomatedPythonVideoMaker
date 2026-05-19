"""
Busca a transcrição de um vídeo do YouTube.
Saída: JSON em stdout. Logs em stderr.
"""
import sys
import json

sys.stderr.write = lambda *a, **k: None  # silencia prints acidentais para stderr visível

url = sys.argv[1]

# Redireciona prints para stderr para não poluir stdout
import builtins
_original_print = builtins.print
builtins.print = lambda *a, **kw: _original_print(*a, **{**kw, 'file': sys.stderr})

sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))
from a import extract_video_id, get_transcript, transcript_with_timestamps

video_id = extract_video_id(url)
transcript = get_transcript(video_id)
text = transcript_with_timestamps(transcript)

builtins.print = _original_print
sys.stdout.write(json.dumps({
    'video_id': video_id,
    'transcript': transcript,
    'text': text,
}) + '\n')
