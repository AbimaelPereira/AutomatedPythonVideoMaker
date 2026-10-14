# YouTube — upload, playlists e coleta de dados

Tudo que fala com as APIs do YouTube vive em três libs do videomaker, expostas
pela API em `/youtube/{slug}/...`. Antes isso estava espalhado em scripts dentro
dos repos dos canais (`subir_video.py`, `playlists_series.py`,
`coletar_dados_canal.py`).

| Arquivo | Papel |
|---|---|
| `libs/YouTube.py` | escrita: upload de vídeo, thumbnail, validação, token |
| `libs/YouTubeReader.py` | leitura: canal, vídeos, playlists, Analytics |
| `libs/YouTubePlaylists.py` | playlists: listar, criar, inserir vídeo |
| `api/youtube/` | os endpoints HTTP |

---

## As três pegadinhas

Estas custaram render e publicação errada. Leia antes de mexer.

### 1. `containsSyntheticMedia` é WRITE-ONLY

A declaração "Conteúdo alterado ou sintético" (a pergunta de IA do Studio) é
enviada no upload, aceita pelo YouTube — e **`videos().list` nunca a devolve**.
Não existe forma de ler esse campo pela API.

Consequências:
- Um sync não traz esse dado. Não é bug.
- A única conferência possível é no Studio: *Conteúdo > o vídeo > Editar >
  Mostrar tudo > "Conteúdo alterado ou sintético"*.

Não é marcado por default. A pergunta do YouTube é sobre conteúdo confundível
com a realidade (pessoa real, lugar real, simulação realista); ilustração 2D
estilizada de gente fictícia é explicitamente isenta. Para marcar, declare
`"contains_synthetic_media": true` no bloco `youtube`.

### 2. `publish_at` só funciona com `privacy_status: "private"`

Com qualquer outro valor o agendamento é **descartado** e o vídeo fica visível
na hora — o oposto exato do pretendido. O `validar()` barra isso antes de subir.

```jsonc
"youtube": {
  "privacy_status": "private",            // OBRIGATÓRIO para agendar
  "publish_at": "2026-10-20 18:00:00",
  "timezone": "America/New_York"          // o fuso do PÚBLICO, não o seu
}
```

O default de `timezone` é `America/Sao_Paulo`. Num canal em inglês isso desloca
a publicação em várias horas, silenciosamente — o `validar()` avisa quando o
`default_language` começa com `en` e o fuso ficou no default.

### 3. Tags somam no máximo 500 caracteres

O teto é a soma de **todas** as tags mais as vírgulas que as separam. Estourar
devolve HTTP 400 `invalidTags` com a mensagem "The request metadata specifies
invalid video keywords" — que não menciona comprimento, então o erro parece ser
de caractere inválido. Custou um render de 2h57m em 22/09/2026 (547 chars).

O `_tags_dentro_do_limite` corta a cauda preservando a ordem (as primeiras tags
são as de maior valor de SEO), e o `validar()` avisa antes.

---

## Escopos OAuth

`libs/YouTube.SCOPES` tem os 10 escopos: Data API v3 (incluindo
`youtube.upload`, `youtube.readonly`, `youtubepartner`) e Analytics
(`yt-analytics.readonly`, `yt-analytics-monetary.readonly`).

**O token em disco manda, não a constante.** `_get_credentials()` carrega as
credenciais com os escopos gravados no próprio arquivo de token
(`_escopos_do_token()`), não com os 10 de `SCOPES`. Isto é essencial: pedir ao
Google a renovação com escopos que o `refresh_token` não cobre falha com
`invalid_scope: Bad Request` — e um canal que fazia upload normalmente pararia
de funcionar só por causa da constante ter crescido.

O que um token de escopo único (`auth/youtube`) ainda faz: upload, playlists,
Data API e **a maior parte do Analytics**. O que perde: as métricas monetárias
(`estimatedRevenue`, `cpm`, …), que devolvem 401 e entram em `erros[]` sem
derrubar a coleta. Confira com:

```bash
curl -H "Authorization: Bearer $JWT" localhost:8000/youtube/{slug}/token
```

A resposta traz `pode_ler_analytics` e `precisa_regerar` — é o que diferencia um
token que só sobe vídeo de um que também lê receita. Para ampliar, regere o
token numa máquina com navegador:

```python
from libs.YouTube import YouTube
YouTube(params={"token_file_name": "/caminho/token.json"}).generate_token()
```

Isso faz backup em `.bak` antes de sobrescrever e aplica `chmod 600`.

> **Não existe endpoint para gerar token.** O fluxo OAuth abre um navegador e
> espera um clique, o que não cabe numa request HTTP. `GET /token` apenas
> diagnostica — nunca dispara consentimento.

### Onde ficam os tokens

Cada canal aponta o seu em `channels_config/{slug}.json`:

```jsonc
"youtube": {
  "token_file_name": "/home/.../Blood and Paperwork/credentials/youtube_token.json"
}
```

Caminho absoluto fica onde está (nos repos dos canais); nome simples resolve em
`videomaker/tokens/` — o `api/youtube/service.py` fixa `token_dir` nesse
caminho absoluto, porque o default do `YouTube.py` é o relativo `"tokens"` e o
processo da API, diferente do pipeline, não faz `chdir` para `videomaker/`.

A fonte de verdade é o **arquivo JSON**, não a tabela
`app_channels` — o `seed_channels.py` copia o JSON para o banco uma única vez e
pula o que já existe, então o banco pode estar velho.

---

## Endpoints

Todos exigem JWT de usuário (`Authorization: Bearer ...`).

### Coleta de dados do canal

```bash
# Job (default): devolve job_id, acompanhe em GET /jobs/{id}
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"inicio":"2026-08-01"}' \
  localhost:8000/youtube/psychology_of_the_gospel/sync

# Para cron/scripts: X-Service-Token em vez de JWT (que expira em 15 min).
# Sempre síncrono — o cron precisa do código de saída e do resumo no log.
curl -X POST -H "X-Service-Token: $SERVICE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"path":"/caminho/do/canal/data/canal.json","inicio":"2026-08-01"}' \
  localhost:8000/youtube/internal/psychology_of_the_gospel/sync

# Síncrono: espera na request e devolve o resumo
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"inicio":"2026-08-01"}' \
  "localhost:8000/youtube/psychology_of_the_gospel/sync?wait=true"
```

Coleta canal + **todos** os vídeos (inclusive privados e agendados) + playlists
+ analytics de canal e de cada vídeo (tráfego, geografia, dispositivos,
retenção, receita) e grava num JSON.

| Campo | Default | O que faz |
|---|---|---|
| `path` | `videomaker/output/analytics/{slug}.json` | destino do JSON; relativo resolve a partir de `videomaker/`. É assim que a coleta cai na pasta do canal (o cron do PoG passa `data/canal.json`) |
| `inicio` | `2020-01-01` | início da janela do Analytics |
| `fim` | hoje | fim da janela |
| `com_analytics_por_video` | `true` | `false` corta 6 queries por vídeo (bem mais rápido, só metadados) |

São ~6 requisições de Analytics **por vídeo**, então um canal com 34 vídeos leva
~1min20s com analytics completo e ~8s sem. Por isso o default é job: mais que
isso estoura o timeout de um cliente HTTP.

A escrita é atômica (`.tmp` + `os.replace`): uma queda no meio não deixa um JSON
truncado no lugar do snapshot anterior.

```bash
# Relê o último snapshot
curl -H "$AUTH" localhost:8000/youtube/{slug}/analytics
curl -H "$AUTH" "localhost:8000/youtube/{slug}/analytics?resumo=true"   # sem a lista de vídeos
```

> O cron do Psychology of the Gospel usa a rota interna e passa
> `path` apontando para `PoG/data/canal.json` — o formato do JSON é o mesmo de
> antes da centralização, então os docs de research do canal que leem esse
> arquivo continuam valendo.

**Uma consulta recusada não derruba a coleta.** O Analytics nega queries por
motivos que variam por canal (sem monetização, dados insuficientes,
`subscribedStatus` devolvendo 500). A chave fica `null` e o motivo entra em
`erros[]` do JSON. Confira `consultas_recusadas` no resumo.

Vazio não é erro: `monetizacao: []` num canal não monetizado e `retencao: []`
num vídeo sem watch time suficiente são respostas legítimas da API.

> Por que o `search(forMine=True)` existe além da playlist de uploads: a
> playlist não lista vídeos privados. No PoG isso é a diferença entre 26 e 34
> vídeos.

### Upload

```bash
# Dry-run: checa metadados sem subir nada
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"video_path":"/caminho/video.mp4","title":"Título"}' \
  localhost:8000/youtube/{slug}/validate

# Sobe (job)
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"video_path":"/caminho/video.mp4"}' \
  localhost:8000/youtube/{slug}/upload
```

O corpo aceita qualquer campo do bloco `youtube` como override; o que vier nulo
mantém o valor do `channels_config`. O upload valida antes de começar e devolve
**422** com a lista de problemas se algo estiver errado — sem gastar banda.

O envio é **resumável em blocos de 10MB**, com backoff exponencial e até 12
tentativas seguidas. Uma queda de conexão retoma de onde parou em vez de
reiniciar: num MP4 de 800MB isso é a diferença entre repetir um bloco e perder
meia hora de upload. O `request` é reusado entre tentativas de propósito —
recriá-lo começaria do zero e poderia gerar um vídeo duplicado no canal.

```bash
# Reenvia a thumbnail de um vídeo que já está no canal (síncrono)
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"video_id":"abc123"}' localhost:8000/youtube/{slug}/thumbnail
```

### Playlists

```bash
curl -H "$AUTH" localhost:8000/youtube/{slug}/playlists

# Idempotente: título existente é reaproveitado ("criada": false)
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"titulo":"The Last Page","descricao":"..."}' \
  localhost:8000/youtube/{slug}/playlists

# Idempotente: vídeo já presente não entra de novo ("adicionado": false)
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"video_id":"abc123"}' \
  localhost:8000/youtube/{slug}/playlists/{playlist_id}/items
```

A API do YouTube aceita de bom grado duas playlists homônimas e o mesmo vídeo
repetido, então a checagem é nossa.

---

## Validação antes do render

`UnifiedVideoEngine` roda `validar(check_video=False)` **antes** de renderizar,
junto da validação dos blocos de IA. Metadado inválido aborta o vídeo ali, com a
lista de problemas.

Isso existe porque antes a primeira vez que um metadado era olhado era dentro do
`upload()` — depois de 6 a 8 horas de render num vídeo longo. Título com 104
chars, tag estourada ou token OAuth ausente só apareciam no fim.

O caso mais traiçoeiro é o token: sem ele, `_get_credentials()` chama
`generate_token()`, que abre um navegador e **bloqueia esperando o clique**. Num
render de madrugada ou disparado por job, isso trava para sempre — depois do
render inteiro. A checagem é um `os.path.exists`.

O que `validar()` cobre:

| Checagem | Por quê |
|---|---|
| título ≤ 100 chars, não vazio | o YouTube corta |
| descrição ≤ 5000 chars | a API recusa |
| soma das tags ≤ 500 chars | HTTP 400 `invalidTags` com mensagem enganosa |
| thumbnail existe e < 2MB | o YouTube recusa acima disso |
| `publish_at` não está no passado | publicaria na hora |
| `publish_at` não está a < 15min | o upload pode não terminar a tempo |
| `publish_at` exige `private` | senão o agendamento é ignorado |
| `timezone` não é o default BR em canal `en` | desloca a publicação |
| token existe em disco | senão abre navegador e trava |

`check_video=False` ignora a existência do MP4, para validar antes de o arquivo
existir.

---

## Dependências

A API importa as libs do videomaker, então `api/requirements.txt` declara
`google-api-python-client`, `google-auth` e `google-auth-oauthlib` nas **mesmas
versões** do `videomaker/requirements.txt` — o mesmo token OAuth é lido pelos
dois lados.
