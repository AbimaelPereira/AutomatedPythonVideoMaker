---
name: criar-json-videomaker
description: Manual para criar e editar JSONs de vídeo do videomaker (cenas, narração, fundo, transições, legendas e upload). Use ao montar um JSON novo para um canal, ajustar configuração de legenda (subtitle), ou tirar dúvida sobre os campos aceitos pelo pipeline. Acione quando o usuário pedir para "criar um json", "fazer um vídeo", "ajustar a legenda", "configurar karaokê", etc.
---

# Criar JSONs para o videomaker

Esta skill é o manual de criação de JSONs de vídeo para o módulo `videomaker/`.
A documentação completa do JSON (estrutura geral, cenas, fundo, TTS, transições)
está em [videomaker/.claude/CLAUDE.md](../../CLAUDE.md) — **leia-a antes** de
montar um JSON do zero.

Esta skill cobre em profundidade o tema que tem mais campos e mais armadilhas:
as **legendas**.

## Referências

- **Legendas (subtitle)** — todos os campos, defaults reais do código, modos do
  karaokê e exemplos prontos: [legendas.md](legendas.md). **É a fonte da verdade
  para `subtitle`.**
- Estrutura geral do JSON, cenas, background, TTS, placement, ordem de merge:
  [videomaker/.claude/CLAUDE.md](../../CLAUDE.md).
- Configs base por canal: [videomaker/channels_config/](../../../channels_config/).
- Exemplos de produção/teste: [videomaker/jsons/](../../../jsons/) — em especial
  `teste_karaoke.json` e `teste_placement_16x9.json`.

## Como usar esta skill

1. Identifique o **canal** (`channel_name`) — a config base dele em
   `channels_config/{canal}.json` já traz `subtitle`, `background`, `tts` etc.
   O JSON do vídeo só precisa do **delta** (o que muda em relação ao canal).
2. Lembre da **ordem de merge** (cada um sobrescreve o anterior, via `deep_merge`):
   canal → `global_settings` → `global_settings` do capítulo → cena.
   Dicts são mesclados recursivamente; **listas são substituídas** (atenção à
   `palette` do karaokê — a paleta da cena vence a global inteira, não funde).
3. Para legendas, consulte [legendas.md](legendas.md) e copie o exemplo do tipo
   desejado (`classic` ou `karaoke`), ajustando só o necessário.
4. Comentários no JSON: qualquer chave terminada em `/` (ex.: `"tts/"`) é
   ignorada pelo pipeline. Use para manter alternativas desabilitadas no arquivo.

## Checklist ao entregar um JSON

- [ ] `slug`, `channel_name`, `output_ratio` presentes (ou herdados do contexto).
- [ ] `subtitle.enabled: true` quando se quer legenda (default é desligado).
- [ ] Fontes referenciadas (`font_path`) existem em `assets/fonts/`.
- [ ] Cores em formato válido (`"#RRGGBB"` ou nome CSS).
- [ ] No karaokê com `palette`: lista completa (não fundirá com a global).
- [ ] `placement` (se usado) coerente com `output_ratio` e com os visuais.
