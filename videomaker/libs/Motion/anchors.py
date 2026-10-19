"""Âncoras: transforma uma referência do JSON em segundos na cena.

A fonte de verdade dos tempos é o SRT palavra-a-palavra que o `NarrationEngine`
já grava (`{scene_dir}/{scene_id}.srt`). Ele sai do provider (edge/polly) ou do
Whisper (google/kokoro) e passa por `_apply_silence_removal`, que REMAPEIA os
tempos depois do corte de silêncio — ou seja, chega aqui já no timeline final do
áudio. Nenhuma correção extra é aplicada.

O casamento é tolerante de propósito: o TTS troca pontuação, expande número e
muda acento, então comparar string crua erraria quase sempre. Em ordem:
normalização (sem acento, sem pontuação) → igualdade exata → fuzzy.
"""

import difflib
import re
import unicodedata

from libs.Motion.errors import AnchorNotFound

# Limiares de similaridade. Acima deles o casamento é aceito; abaixo é miss (e
# a política `on_missing` decide). 88/85 vêm do plano.
_WORD_RATIO = 88
_PHRASE_RATIO = 85

_SENTENCE_SPLIT = re.compile(r"[.!?…;]+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    """lower → NFD → sem diacríticos → sem pontuação → espaços colapsados."""
    text = unicodedata.normalize("NFD", str(text).lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())


def _ratio(a: str, b: str) -> float:
    """Similaridade 0–100. Usa `thefuzz` quando disponível (já é dependência);
    `difflib` é o plano B, para o pacote Motion não quebrar sem ela."""
    try:
        from thefuzz import fuzz
        return float(fuzz.ratio(a, b))
    except Exception:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100.0


class AnchorResolver:
    """Resolve âncoras de uma cena. Uma instância por elemento (acumula misses).

    `words` é `[{word, start, end}]` (de `SubtitleUtils.parse_srt_words`), ou
    None quando a cena não tem narração — nesse caso toda âncora de fala é miss
    e a política `on_missing` assume, sem erro de render (princípio P4).
    """

    def __init__(self, words: list = None, narration_text: str = "",
                 scene_duration: float = 0.0, on_missing: str = "proportional"):
        self.words = list(words or [])
        self.narration_text = narration_text or ""
        self.scene_duration = float(scene_duration or 0.0)
        self.on_missing = on_missing
        self.misses: list = []
        self._norm = [normalize(w.get("word", "")) for w in self.words]

    # -- API ---------------------------------------------------------------

    def resolve(self, spec, *, align: str = None, path: str = ""):
        """Segundos na cena, ou None se a âncora não casou."""
        if isinstance(spec, bool):
            return None
        if isinstance(spec, (int, float)):
            return self._clamp(float(spec))
        if isinstance(spec, str):
            return self._resolve_literal(spec, path)
        if not isinstance(spec, dict):
            return None

        align = spec.get("align", align or "start")
        offset = float(spec.get("offset") or 0.0)

        if "word" in spec:
            span = self._find_word(spec["word"], int(spec.get("nth", 1) or 1), path)
        elif "word_index" in spec:
            span = self._word_at(int(spec["word_index"]), path)
        elif "phrase" in spec:
            span = self._find_phrase(spec["phrase"], path)
        elif "sentence" in spec:
            span = self._find_sentence(int(spec["sentence"]), path)
        else:
            return None

        if span is None:
            return None
        return self._clamp(self._align(span, align) + offset)

    # -- literais ----------------------------------------------------------

    def _resolve_literal(self, text: str, path: str):
        value = text.strip().lower()
        if value == "start":
            return 0.0
        if value == "end":
            return self.scene_duration
        if value.endswith("%"):
            try:
                return self._clamp(float(value[:-1]) / 100.0 * self.scene_duration)
            except ValueError:
                pass
        if value.endswith("s"):
            try:
                return self._clamp(float(value[:-1]))
            except ValueError:
                pass
        try:
            return self._clamp(float(value))
        except ValueError:
            self._miss(f"âncora literal inválida: {text!r}", path, "")
            return None

    # -- seletores ---------------------------------------------------------

    def _find_word(self, word, nth: int, path: str):
        target = normalize(word)
        hits = [i for i, w in enumerate(self._norm) if w == target]

        if not hits:
            # Fuzzy: o TTS/Whisper muda plural, acento e grafia de número.
            scored = sorted(
                ((_ratio(target, w), i) for i, w in enumerate(self._norm)),
                key=lambda pair: -pair[0],
            )
            hits = [i for score, i in scored if score >= _WORD_RATIO]
            if not hits:
                self._miss(f"palavra {word!r} não encontrada", path, target)
                return None

        if nth > len(hits):
            self._miss(f"palavra {word!r} aparece {len(hits)}x, "
                       f"pedido nth={nth}", path, target)
            return None
        index = hits[nth - 1]
        return (self.words[index]["start"], self.words[index]["end"])

    def _word_at(self, index: int, path: str):
        if not self.words or index > len(self.words):
            self._miss(f"word_index {index} fora da cena "
                       f"({len(self.words)} palavras)", path, "")
            return None
        word = self.words[index - 1]
        return (word["start"], word["end"])

    def _find_phrase(self, phrase, path: str):
        target = normalize(phrase)
        size = len(target.split())
        if not self.words or size == 0:
            self._miss(f"frase {phrase!r} não encontrada", path, target)
            return None

        best = (0.0, -1)
        for i in range(0, max(1, len(self.words) - size + 1)):
            window = " ".join(self._norm[i:i + size])
            score = _ratio(target, window)
            if score > best[0]:
                best = (score, i)

        if best[1] < 0 or best[0] < _PHRASE_RATIO:
            self._miss(f"frase {phrase!r} não encontrada "
                       f"(melhor score {best[0]:.0f})", path, target)
            return None
        start = self.words[best[1]]["start"]
        end = self.words[min(best[1] + size - 1, len(self.words) - 1)]["end"]
        return (start, end)

    def _find_sentence(self, number: int, path: str):
        """n-ésima frase do `narration.text`, mapeada para palavras do SRT.

        O texto escrito e o SRT divergem (o TTS fala "mil novecentos e noventa"
        onde o JSON escreveu "1990"), então o alinhamento é feito por
        `SequenceMatcher` sobre as palavras normalizadas, não por contagem.
        """
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(self.narration_text)
                     if s.strip()]
        if not sentences or number > len(sentences) or not self.words:
            self._miss(f"sentence {number} fora do texto "
                       f"({len(sentences)} frases)", path, "")
            return None

        tokens, owner = [], []
        for s_index, sentence in enumerate(sentences):
            for token in normalize(sentence).split():
                tokens.append(token)
                owner.append(s_index)

        matcher = difflib.SequenceMatcher(None, tokens, self._norm, autojunk=False)
        # token do texto → índice da palavra no SRT
        mapping: dict = {}
        for a0, b0, size in matcher.get_matching_blocks():
            for k in range(size):
                mapping[a0 + k] = b0 + k

        indices = [mapping[i] for i, who in enumerate(owner)
                   if who == number - 1 and i in mapping]
        if not indices:
            self._miss(f"sentence {number} não alinhou com o SRT", path, "")
            return None
        return (self.words[min(indices)]["start"], self.words[max(indices)]["end"])

    # -- auxiliares --------------------------------------------------------

    @staticmethod
    def _align(span: tuple, align: str) -> float:
        start, end = span
        if align == "end":
            return float(end)
        if align == "center":
            return (float(start) + float(end)) / 2.0
        return float(start)

    def _clamp(self, value: float) -> float:
        if self.scene_duration <= 0:
            return max(0.0, value)
        return max(0.0, min(value, self.scene_duration))

    def _miss(self, message: str, path: str, target: str):
        """Registra (e loga) uma âncora não resolvida, com as palavras mais
        parecidas do SRT para diagnóstico."""
        nearby = ""
        if target and self._norm:
            scored = sorted(((_ratio(target, w), w) for w in set(self._norm)),
                            key=lambda pair: -pair[0])[:5]
            nearby = "  próximas: " + " ".join(f"{w!r}({s:.0f})" for s, w in scored)

        detail = f"{path}: {message}" if path else message
        self.misses.append(detail + nearby)
        print(f"[Motion] ⚠️ âncora não resolvida: {detail}{nearby}")

        if self.on_missing == "strict":
            raise AnchorNotFound(message, path, nearby.strip())
