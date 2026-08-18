# Templates de cena prontos

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

Cenas reutilizáveis já validadas (render + revisão visual de frames), pensadas
para copiar/colar como ponto de partida e adaptar `content`/`source`/textos.
Cópia canônica **dentro da skill**, sempre disponível independente do projeto:

- [../examples/template_logo_scenes.json](../examples/template_logo_scenes.json) —
  com placeholders `{{...}}` para preencher.
- [../examples/template_logo_scenes_demo.json](../examples/template_logo_scenes_demo.json) —
  mesma estrutura com valores reais, pronta para rodar em `DEBUG=1`.
- [../examples/template_split_scenes.json](../examples/template_split_scenes.json) —
  com placeholders `{{...}}` para preencher.
- [../examples/template_split_scenes_demo.json](../examples/template_split_scenes_demo.json) —
  mesma estrutura com valores reais, pronta para rodar em `DEBUG=1`.

Os mesmos arquivos também vivem em `jsons/templates/{nome}.json` /
`{nome}_demo.json` no projeto — é a cópia "de trabalho", onde `python main.py`
de fato lê. Ao editar um template, replique a mudança nos dois lugares (ou
copie de novo de `jsons/templates/` para `examples/` depois de validar).

## `template_logo_scenes.json` — abertura/encerramento com logo

Duas cenas que replicam fielmente o padrão de 3 elementos empilhados
verticalmente (logo + título + subtítulo), mesmo ritmo de espaçamento usado em
produções anteriores (`anchor` em 10% / 70% / 80% da área segura):

- **`logo_center_title_below`** — logo no topo (`10%`, `width: "34%"`), título
  grande em `ExtraBold` (`70%`, `width: "45%"`, `font_size: 100`), tagline em
  `LightItalic` (`80%`, `width: "25%"`, `font_size: 100`). Uso: abertura/intro.
- **`logo_center_title_above`** — mesma estrutura invertida (tagline no meio,
  handle/nome de usuário embaixo em `ExtraBold`, `width: "35%"` — largura maior
  porque `@handle` tende a ser uma string mais longa que a tagline). Uso:
  encerramento/CTA.

**Armadilha resolvida:** a caixa de um `text_box` sem `width` suficiente para o
conteúdo real (ex.: `@handle` mais longo que a tagline acima) faz o
`LayoutEngine` recalcular a largura e desloca visualmente o centro do texto —
meça o texto mais longo que a cena vai receber e dê margem no `width` (ver
[placement.md](placement.md)).

Fundo sólido `#1A0F05` (cor `primary` de exemplo); troque pela paleta do
canal. Logo em `./assets/image/pyvideomaker_logo.png` é um placeholder — troque
pelo logo real do canal (PNG com fundo transparente).

## `template_split_scenes.json` — tela dividida com legenda lateral

Três cenas de "imagem + legenda lado a lado" usando `placement` explícito
(visual de um lado, legenda no espaço que sobra do outro — ver
[placement.md](placement.md) para o caso de uso clássico):

- **`split_dark_right_image`** — fundo escuro à esquerda, imagem ocupando 50%
  à direita (`placement.width: "50%", height: "100%"`), legenda karaokê
  encostada à esquerda (`anchor: ["7%","center"], region: "36%"`).
- **`split_light_left_image`** — inverso: fundo claro à direita, imagem à
  esquerda, legenda encostada à direita (`anchor: ["57%","center"]`).
- **`fullscreen_background_center_subtitle`** — fundo em tela cheia
  (`remote_asset`/`image`/`ai`) com zoom lento, legenda central grande
  (`region: "80%"`) com sombra.

Todas as cenas têm `subtitle.enabled: true` explícito — **checklist obrigatório**,
já que o default do pipeline é legenda desligada quando o campo está ausente.
Esse foi o bug mais comum encontrado ao criar esses templates: cena com
narração e bloco `subtitle` completo, mas sem legenda nenhuma no vídeo final
porque faltava esse único campo.

## Armadilhas encontradas montando estes templates

- **Legenda "sumida" com narração funcionando** → confira `subtitle.enabled: true`
  em cada cena (ou em `global_settings.subtitle`). Sintoma: narração e áudio ok,
  vídeo sem nenhum texto — o bloco `subtitle` existe mas fica silenciosamente
  inativo.
- **Texto de handle/nome cortado ou fora do centro** → ver armadilha de
  `logo_scenes.json` acima; sempre teste com a string real mais longa.
- **Cores da paleta do canal**: os templates usam uma paleta de exemplo
  (`#1A0F05` / `#FFF6EC` / `#FF8C32`) — troque via find/replace pelas cores do
  canal alvo antes de gerar em produção.

---

Próximos passos: [placement.md](placement.md) · [subtitle.md](subtitle.md) ·
[visual_elements.md](visual_elements.md).
