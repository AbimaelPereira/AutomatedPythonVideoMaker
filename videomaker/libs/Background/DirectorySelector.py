"""DirectorySelector — escolhe quais arquivos de uma pasta preenchem uma cena.

Núcleo compartilhado por `background.visual` e `visual_elements[]`, nos DOIS
caminhos de render. Trabalha só com **caminhos e metadados** — nunca com clips
MoviePy — porque o caminho ffmpeg precisa do plano de seleção antes de existir
qualquer objeto de vídeo.

Devolve um "plano de preenchimento": a lista de segmentos que, concatenados,
cobrem exatamente a duração da cena. Cada caminho de render materializa esse
plano do seu jeito (MoviePy: subclip/concatenate; ffmpeg: inputs + concat).

## Estratégias (`fill_strategy`)

- `"prefer_single"` (**default**) — usa um arquivo só quando existir algum que
  cubra a cena inteira; senão, cai em `concat`. Evita cortes desnecessários no
  meio da cena sem travar quando a pasta só tem clipes curtos.
- `"concat"` — sempre sorteia arquivos até cobrir a duração e concatena. É o
  comportamento histórico do `_build_directory`.
- `"single"` — força UM arquivo só. Se nenhum cobrir a cena, usa o mais longo
  disponível em loop (aceita a repetição visível como parte da escolha).

> O default mudou de `concat` para `prefer_single`: cenas cujo diretório tenha
> clipes longos o bastante passam a mostrar um vídeo contínuo em vez de vários
> cortes. Para manter o comportamento antigo, declare `"fill_strategy": "concat"`.

## Anti-repetição

O histórico de uso é **persistido em disco** (`cache/directory_usage.json`),
não em memória. Isso não é um detalhe de implementação: o pipeline roda cenas
em `ProcessPoolExecutor`, então um histórico em memória morre com o processo e
não impede repetição entre cenas — que é exatamente onde a repetição incomoda.

A regra é "não repete enquanto houver alternativa": arquivos usados nos últimos
`no_repeat_window` sorteios daquela pasta saem do bolo. Se isso esvaziar as
opções, a janela é ignorada (melhor repetir do que não ter fundo).
"""

import json
import os
import random
import tempfile
import time

from libs.Background.MediaProbe import MediaProbe

_DEFAULT_IMAGE_DURATION = 4.0
_DEFAULT_NO_REPEAT_WINDOW = 20
_DEFAULT_FILL_STRATEGY = "prefer_single"


class DirectorySelector:
    """Seleciona arquivos de uma pasta para preencher a duração de uma cena."""

    def __init__(self, probe: MediaProbe = None,
                 usage_path: str = "cache/directory_usage.json"):
        self.probe = probe or MediaProbe()
        self.usage_path = usage_path

    # ------------------------------------------------------------------
    # HISTÓRICO DE USO (persistido)
    # ------------------------------------------------------------------

    def _load_usage(self) -> dict:
        try:
            with open(self.usage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _record_usage(self, directory: str, paths: list, window: int):
        """Anexa os paths ao histórico da pasta, mantendo só a janela recente.

        Relê o arquivo imediatamente antes de gravar para não sobrescrever o que
        outro processo registrou — sem isso, cenas paralelas se apagariam
        mutuamente e o anti-repetição viraria enfeite.
        """
        if not paths:
            return
        try:
            directory_key = os.path.abspath(directory)
            usage = self._load_usage()
            history = list(usage.get(directory_key) or [])
            history.extend(os.path.abspath(p) for p in paths)

            # Guarda um pouco mais que a janela: o excedente é histórico morto,
            # mas evita reescrever o arquivo a cada sorteio por 1 item.
            limit = max(int(window) * 2, 20)
            usage[directory_key] = history[-limit:]

            target_dir = os.path.dirname(os.path.abspath(self.usage_path))
            os.makedirs(target_dir, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(usage, f)
                os.replace(tmp, self.usage_path)
            except Exception:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as e:
            print(f"[DirectorySelector] ⚠️ Falha ao registrar uso: {e}")

    def _recent(self, directory: str, window: int) -> set:
        if window <= 0:
            return set()
        history = self._load_usage().get(os.path.abspath(directory)) or []
        return set(history[-int(window):])

    # ------------------------------------------------------------------
    # SELEÇÃO
    # ------------------------------------------------------------------

    def build_plan(self, cfg: dict, scene_duration: float, seed=None) -> list:
        """Plano de preenchimento da cena.

        Devolve lista de segmentos:
            [{path, start, duration, is_video, width, height, loop}]

        - `start`/`duration` são o trecho a usar do arquivo (em segundos).
        - `loop=True` significa que o arquivo é mais curto que `duration` e deve
          ser repetido para preencher (só ocorre em `single`).
        - Para imagem, `start` é 0 e `duration` vem de `image_default_duration`.

        Lista vazia = pasta sem mídia utilizável; quem chama cai no fallback
        (fundo preto), como já fazia.
        """
        source = str(cfg.get("source", "")).strip()
        if not source:
            return []

        scene_duration = float(scene_duration)
        if scene_duration <= 0:
            return []

        files = self.probe.list_media(source)
        if not files:
            print(f"[DirectorySelector] ⚠️ Nenhuma mídia em {source}")
            return []

        # Metadados de todos os candidatos (barato: cacheado por path+mtime).
        candidates = []
        image_duration = float(cfg.get("image_default_duration", _DEFAULT_IMAGE_DURATION))
        max_clip_duration = cfg.get("max_clip_duration")

        for path in files:
            info = self.probe.probe(path)
            if info["is_video"]:
                usable = info["duration"]
                if not usable or usable <= 0:
                    continue  # vídeo ilegível: fora do bolo
            else:
                usable = image_duration
            if max_clip_duration:
                usable = min(usable, float(max_clip_duration))
            candidates.append({
                "path": path,
                "usable": float(usable),
                "is_video": info["is_video"],
                "width": info["width"],
                "height": info["height"],
            })

        if not candidates:
            print(f"[DirectorySelector] ⚠️ Nenhuma mídia legível em {source}")
            return []

        window = int(cfg.get("no_repeat_window", _DEFAULT_NO_REPEAT_WINDOW))
        strategy = str(cfg.get("fill_strategy", _DEFAULT_FILL_STRATEGY)).strip().lower()
        shuffle = bool(cfg.get("shuffle", True))
        rng = random.Random(seed) if seed is not None else random

        pool = self._apply_no_repeat(candidates, source, window)

        if strategy in ("single", "prefer_single"):
            plan = self._plan_single(pool, scene_duration, rng, shuffle,
                                     strict=(strategy == "single"))
            # Sem cobertura no bolo filtrado, mas talvez exista um arquivo que
            # cobre e só foi barrado pelo anti-repetição. Cobertura vale mais
            # que variedade: um clipe repetido incomoda menos que um loop
            # visível dentro da mesma cena.
            if not plan and len(pool) < len(candidates):
                plan = self._plan_single(candidates, scene_duration, rng, shuffle,
                                         strict=(strategy == "single"))
            if plan:
                self._record_usage(source, [s["path"] for s in plan], window)
                return plan
            # prefer_single sem cobertura única → concat

        plan = self._plan_concat(pool, scene_duration, rng, shuffle, cfg,
                                 all_candidates=candidates)
        self._record_usage(source, [s["path"] for s in plan], window)
        return plan

    def _apply_no_repeat(self, candidates: list, directory: str, window: int) -> list:
        """Remove os usados recentemente — a menos que isso zere as opções."""
        recent = self._recent(directory, window)
        if not recent:
            return list(candidates)
        fresh = [c for c in candidates if os.path.abspath(c["path"]) not in recent]
        if fresh:
            return fresh
        # Pasta menor que a janela: repetir é inevitável.
        return list(candidates)

    def _plan_single(self, pool: list, scene_duration: float, rng,
                     shuffle: bool, strict: bool) -> list:
        """Um arquivo só. Prefere quem cobre a cena inteira."""
        covering = [c for c in pool if c["usable"] >= scene_duration]

        if covering:
            chosen = rng.choice(covering) if shuffle else covering[0]
            # Cobre de sobra: começa num ponto aleatório para não mostrar sempre
            # o mesmo trecho do mesmo arquivo.
            slack = chosen["usable"] - scene_duration
            start = rng.uniform(0, slack) if (shuffle and slack > 0) else 0.0
            return [self._segment(chosen, start, scene_duration)]

        if not strict:
            return []

        # `single` estrito e nada cobre: usa o mais longo e faz loop.
        longest = max(pool, key=lambda c: c["usable"])
        seg = self._segment(longest, 0.0, scene_duration)
        seg["loop"] = True
        return [seg]

    def _plan_concat(self, pool: list, scene_duration: float, rng,
                     shuffle: bool, cfg: dict, all_candidates: list = None) -> list:
        """Sorteia arquivos até cobrir a duração.

        Não repete dentro de uma passada. Se a pasta inteira não bastar para a
        cena, dá outra volta nela (reembaralhada) em vez de esticar um clipe em
        loop — 5 repetições do mesmo trecho de 7 s aparecem muito mais que o
        mesmo clipe voltando depois de outros quatro.
        """
        max_clips = cfg.get("max_clips")
        limit = max_clips if isinstance(max_clips, int) and max_clips > 0 else None

        segments = []
        filled = 0.0
        # Passadas extras usam o bolo completo: o anti-repetição já não tem o
        # que proteger quando a pasta toda foi consumida nesta cena.
        recycle_pool = all_candidates or pool
        current = list(pool)
        guard = 0

        while filled < scene_duration - 0.01 and guard < 100:
            guard += 1
            order = list(current)
            if shuffle:
                rng.shuffle(order)

            for item in order:
                remaining = scene_duration - filled
                if remaining <= 0.01:
                    break
                if limit is not None and len(segments) >= limit:
                    break
                take = min(item["usable"], remaining)
                # Arquivo mais longo que o necessário: pega um trecho aleatório
                # em vez de sempre o começo.
                slack = item["usable"] - take
                start = rng.uniform(0, slack) if (shuffle and slack > 0) else 0.0
                segments.append(self._segment(item, start, take))
                filled += take

            if limit is not None and len(segments) >= limit:
                break
            current = recycle_pool

        if not segments:
            return []

        # Só sobra buraco se `max_clips` cortou o preenchimento. Aí sim estica o
        # último segmento, porque o usuário pediu explicitamente um teto.
        remaining = scene_duration - filled
        if remaining > 0.01:
            segments[-1]["duration"] = round(segments[-1]["duration"] + remaining, 3)
            segments[-1]["loop"] = True

        return segments

    @staticmethod
    def _segment(item: dict, start: float, duration: float) -> dict:
        return {
            "path": item["path"],
            "start": round(float(start), 3),
            "duration": round(float(duration), 3),
            "is_video": item["is_video"],
            "width": item["width"],
            "height": item["height"],
            "loop": False,
        }
