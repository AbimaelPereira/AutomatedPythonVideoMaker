"""Erros do Motion. Todos carregam o caminho JSON do que falhou (princípio P3:
falhar cedo e alto, apontando o lugar exato no JSON)."""


class MotionError(Exception):
    """Base. `path` é o caminho JSON, ex.:
    `scenes[2].visual_elements[0].motion.actions[1].ease`."""

    def __init__(self, message: str, path: str = "", hint: str = ""):
        self.path = path
        self.hint = hint
        self.message = message
        full = f"{path}: {message}" if path else message
        if hint:
            full = f"{full} ({hint})"
        super().__init__(full)


class AnchorNotFound(MotionError):
    """Âncora de palavra/frase não encontrada no SRT da cena.

    Só escapa quando `on_missing: "strict"`; nas outras políticas o resolvedor
    devolve None e o `timeline.py` aplica o fallback.
    """


class ValidationError(MotionError):
    """Erro de schema (chave desconhecida, easing inexistente, valor inválido)."""
