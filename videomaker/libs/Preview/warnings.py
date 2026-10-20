"""Degradações silenciosas das engines (fundo preto, elemento pulado) a partir do log."""

WARNING_MARKERS = (
    "Falha ao criar fundo",
    "Fallback: preto",
    "Tipo de fundo desconhecido",
    "Erro no elemento",
    "Falha ao posicionar elemento",
    "Falha no LayoutEngine",
    "não encontrado",
    "não encontrada",
)


def extract_warnings(log: str) -> list:
    seen, warnings = set(), []
    for line in log.splitlines():
        line = line.strip()
        if not line or line in seen:
            continue
        if any(marker in line for marker in WARNING_MARKERS):
            seen.add(line)
            warnings.append(line)
    return warnings
