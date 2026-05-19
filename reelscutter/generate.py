"""
Corta os áudios e gera os JSONs finais.
Argumentos: audio_path min_words max_words channel_name clips_json_file
Saída: JSON em stdout. Logs em stderr.
"""
import sys
import json
import builtins

_print = builtins.print
builtins.print = lambda *a, **kw: _print(*a, **{**kw, 'file': sys.stderr})

audio_path      = sys.argv[1]
min_words       = int(sys.argv[2])
max_words       = int(sys.argv[3])
channel_name    = sys.argv[4]
clips_json_file = sys.argv[5]

with open(clips_json_file, 'r', encoding='utf-8') as f:
    clips = json.load(f)

sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))
import a
import os

a.MIN_WORDS_SCENE = min_words
a.MAX_WORDS_SCENE = max_words
a.CHANNEL_NAME    = channel_name
a.ensure_dirs()

results = []
for clip in clips:
    n     = clip['clip_number']
    start = clip['start_time']
    end   = clip['end_time']
    slug  = a.slugify(clip['title'])
    filename  = f'clip_{n:02d}_{slug[:40]}.mp3'
    clip_path = os.path.join('./temp', filename)
    try:
        a.cut_audio(audio_path, start, end, clip_path)
        doc = a.build_json(clip, filename)
        results.append({'clip': clip, 'json': doc, 'audio': clip_path})
    except Exception as e:
        results.append({'clip': clip, 'error': str(e)})

video_id = os.path.splitext(os.path.basename(audio_path))[0]
out_path = os.path.join('./jsons', f'{video_id}.json')
os.makedirs('./jsons', exist_ok=True)

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump([r['json'] for r in results if 'json' in r], f, ensure_ascii=False, indent=2)

builtins.print = _print
sys.stdout.write(json.dumps({'results': results, 'json_path': out_path}) + '\n')
