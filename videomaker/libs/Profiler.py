"""Profiler — instrumentação de tempo por etapa do pipeline.

Mede onde o tempo realmente vai num render. Antes disso, qualquer otimização é
hipótese: TTS, Whisper e download de assets não são tocados pelas otimizações de
encoding, e em vídeos longos podem ser fatias relevantes.

Uso:

    prof = Profiler(enabled=True)

    with prof.step("narracao"):
        ...

    prof.add("encode_cena", 12.4)      # soma manual (ex.: vindo de subprocesso)
    prof.report(total_video_duration=360.0)

Etapas repetidas (uma por cena) acumulam tempo e contagem — o relatório mostra
total, número de ocorrências e média.

Thread-safe para o modo sequencial. Nos workers de `ProcessPoolExecutor` cada
processo tem seu próprio Profiler; os tempos voltam pelo retorno do worker e são
somados no processo pai via `merge()`.
"""

import time
import threading
from collections import OrderedDict
from contextlib import contextmanager


class Profiler:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._steps = OrderedDict()   # nome -> {"total": float, "count": int}
        self._lock = threading.Lock()
        self._t0 = time.time()

    # ------------------------------------------------------------------
    # COLETA
    # ------------------------------------------------------------------

    @contextmanager
    def step(self, name: str):
        """Mede o bloco. Contabiliza mesmo se houver exceção (o tempo foi gasto)."""
        if not self.enabled:
            yield
            return
        t = time.time()
        try:
            yield
        finally:
            self.add(name, time.time() - t)

    def add(self, name: str, seconds: float):
        if not self.enabled:
            return
        with self._lock:
            entry = self._steps.get(name)
            if entry is None:
                self._steps[name] = {"total": float(seconds), "count": 1}
            else:
                entry["total"] += float(seconds)
                entry["count"] += 1

    def merge(self, other: dict):
        """Incorpora os tempos de um worker (dict vindo de `export()`)."""
        if not self.enabled or not other:
            return
        for name, entry in other.items():
            with self._lock:
                cur = self._steps.get(name)
                if cur is None:
                    self._steps[name] = {"total": float(entry.get("total", 0.0)),
                                         "count": int(entry.get("count", 0))}
                else:
                    cur["total"] += float(entry.get("total", 0.0))
                    cur["count"] += int(entry.get("count", 0))

    def export(self) -> dict:
        """Serializa para atravessar a fronteira de processo."""
        with self._lock:
            return {k: dict(v) for k, v in self._steps.items()}

    # ------------------------------------------------------------------
    # RELATÓRIO
    # ------------------------------------------------------------------

    def report(self, total_video_duration: float | None = None):
        """Imprime o resumo. `total_video_duration` habilita a razão vs realtime."""
        if not self.enabled:
            return

        wall = time.time() - self._t0
        with self._lock:
            steps = [(k, v["total"], v["count"]) for k, v in self._steps.items()]

        if not steps:
            return

        steps.sort(key=lambda x: x[1], reverse=True)
        measured = sum(s[1] for s in steps)

        print("\n" + "=" * 72)
        print("[PROFILER] Tempo por etapa (ordenado por custo)")
        print("=" * 72)
        print(f"{'etapa':<28} {'total':>10} {'n':>5} {'média':>10} {'%':>7}")
        print("-" * 72)

        for name, total, count in steps:
            avg = total / count if count else 0.0
            pct = (total / measured * 100) if measured else 0.0
            print(f"{name:<28} {self._fmt(total):>10} {count:>5} {self._fmt(avg):>10} {pct:>6.1f}%")

        print("-" * 72)
        print(f"{'soma das etapas medidas':<28} {self._fmt(measured):>10}")
        print(f"{'wall clock total':<28} {self._fmt(wall):>10}")

        # Paralelismo faz a soma das etapas passar do wall clock — é esperado.
        if wall > 0 and measured > wall * 1.05:
            print(f"{'(paralelismo: soma/wall)':<28} {measured / wall:>9.1f}x")
        elif wall > measured:
            gap = wall - measured
            if gap > wall * 0.1:
                print(f"{'não instrumentado':<28} {self._fmt(gap):>10} "
                      f"({gap / wall * 100:.0f}% do wall)")

        if total_video_duration and total_video_duration > 0:
            print("-" * 72)
            ratio = wall / total_video_duration
            print(f"duração do vídeo: {self._fmt(total_video_duration)} "
                  f"→ render {ratio:.1f}x realtime")
            if ratio > 1:
                print(f"projeção p/ 45 min de vídeo: "
                      f"{self._fmt(45 * 60 * ratio)}")
        print("=" * 72 + "\n")

    @staticmethod
    def _fmt(seconds: float) -> str:
        s = float(seconds)
        if s < 60:
            return f"{s:.1f}s"
        if s < 3600:
            return f"{int(s // 60)}m{int(s % 60):02d}s"
        return f"{int(s // 3600)}h{int((s % 3600) // 60):02d}m"


class NullProfiler(Profiler):
    """Profiler desligado — mesma interface, custo zero."""

    def __init__(self):
        super().__init__(enabled=False)
