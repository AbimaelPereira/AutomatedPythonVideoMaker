-- Documenta tabelas e colunas com COMMENT. Só comentários: tipos, defaults e nulidade iguais aos atuais.

-- ---------------------------------------------------------------- marcas
ALTER TABLE `app_brands`
  COMMENT = 'Marca que publica conteúdo (ex.: um canal dark). Guarda os padrões de criação herdados por todo conteúdo dela.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `slug` varchar(100) NOT NULL COMMENT 'Identificador legível e único da marca (ex.: devocional_com_jesus).',
  MODIFY `name` varchar(255) NOT NULL COMMENT 'Nome de exibição da marca.',
  MODIFY `description` text COMMENT 'Descrição livre da marca (nicho, tom, público).',
  MODIFY `defaults` json DEFAULT NULL COMMENT 'Padrões de criação (TTS, legenda, fundo, transições, output...). Primeiro nível da mesclagem: brand.defaults > content.settings > chapter.settings > scene.request.',
  MODIFY `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '1 = ativa; 0 = desativada. Marca não é apagada, só desativada.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

ALTER TABLE `app_brand_account_youtube`
  COMMENT = 'Canal do YouTube ligado a uma marca, com as credenciais OAuth para upload.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `brand_id` int NOT NULL COMMENT 'FK app_brands.id: marca dona do canal.',
  MODIFY `channel_id` varchar(64) NOT NULL COMMENT 'ID do canal no YouTube (UC...). Único.',
  MODIFY `channel_title` varchar(255) DEFAULT NULL COMMENT 'Nome do canal no YouTube (informativo).',
  MODIFY `access_token` text COMMENT 'Access token OAuth atual (curta duração).',
  MODIFY `refresh_token` text COMMENT 'Refresh token OAuth, usado para renovar o access_token.',
  MODIFY `token_expires_at` datetime(3) DEFAULT NULL COMMENT 'Quando o access_token expira.',
  MODIFY `default_privacy` varchar(20) NOT NULL DEFAULT 'private' COMMENT 'Privacidade padrão dos uploads: private | unlisted | public.',
  MODIFY `default_category_id` varchar(10) DEFAULT NULL COMMENT 'ID de categoria do YouTube usado por padrão nos uploads (ex.: 22 = People & Blogs).',
  MODIFY `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '1 = canal em uso; 0 = desligado (não recebe uploads).',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

ALTER TABLE `app_brand_account_instagram`
  COMMENT = 'Conta do Instagram ligada a uma marca, com o token de publicação.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `brand_id` int NOT NULL COMMENT 'FK app_brands.id: marca dona da conta.',
  MODIFY `ig_user_id` varchar(64) NOT NULL COMMENT 'ID do usuário Instagram (Graph API). Único.',
  MODIFY `username` varchar(255) DEFAULT NULL COMMENT '@ da conta (informativo).',
  MODIFY `access_token` text COMMENT 'Token de acesso da Graph API (longa duração).',
  MODIFY `token_expires_at` datetime(3) DEFAULT NULL COMMENT 'Quando o access_token expira.',
  MODIFY `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '1 = conta em uso; 0 = desligada (não recebe publicações).',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

-- ---------------------------------------------------------------- usuários e acesso
ALTER TABLE `app_users`
  COMMENT = 'Pessoa que usa a API.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `email` varchar(255) NOT NULL COMMENT 'E-mail de login. Único.',
  MODIFY `name` varchar(255) DEFAULT NULL COMMENT 'Nome de exibição.',
  MODIFY `password_hash` varchar(255) DEFAULT NULL COMMENT 'Hash da senha. NULL = usuário sem login por senha (só token).',
  MODIFY `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '1 = pode acessar; 0 = bloqueado.',
  MODIFY `last_login_at` datetime(3) DEFAULT NULL COMMENT 'Último login por senha.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

ALTER TABLE `app_brand_users`
  COMMENT = 'Quais usuários têm acesso a quais marcas, e com qual papel. PK composta (brand_id, user_id).',
  MODIFY `brand_id` int NOT NULL COMMENT 'FK app_brands.id.',
  MODIFY `user_id` int NOT NULL COMMENT 'FK app_users.id.',
  MODIFY `role` varchar(20) NOT NULL DEFAULT 'owner' COMMENT 'Papel do usuário na marca. Hoje só owner; a API valida.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o acesso foi concedido.';

ALTER TABLE `app_api_tokens`
  COMMENT = 'Token de API preso a 1 usuário + 1 marca (FK composta em app_brand_users). Guarda só o sha256; o token puro é exibido uma vez.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `user_id` int NOT NULL COMMENT 'Usuário dono do token (parte da FK app_brand_users).',
  MODIFY `brand_id` int NOT NULL COMMENT 'Marca que o token pode acessar (parte da FK app_brand_users).',
  MODIFY `name` varchar(100) DEFAULT NULL COMMENT 'Rótulo livre para identificar o uso (ex.: worker, n8n).',
  MODIFY `prefix` varchar(16) NOT NULL COMMENT 'Começo do token em texto puro, para reconhecer qual é sem expor o resto.',
  MODIFY `token_hash` char(64) NOT NULL COMMENT 'sha256 (hex) do token completo. Único; é o que a API compara.',
  MODIFY `last_used_at` datetime(3) DEFAULT NULL COMMENT 'Última requisição autenticada com este token.',
  MODIFY `expires_at` datetime(3) DEFAULT NULL COMMENT 'Validade. NULL = não expira.',
  MODIFY `revoked_at` datetime(3) DEFAULT NULL COMMENT 'Quando foi revogado. NULL = ativo.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o token foi criado.';

-- ---------------------------------------------------------------- conteúdo
ALTER TABLE `app_contents`
  COMMENT = 'Um vídeo ou uma imagem de uma marca: o pedido, o estado do processamento e as chaves dos arquivos gerados.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna (não exposta na API).',
  MODIFY `uid` char(26) NOT NULL COMMENT 'ULID: identificador público do conteúdo na API. Único.',
  MODIFY `brand_id` int NOT NULL COMMENT 'FK app_brands.id: marca do conteúdo (sem cascade: marca com conteúdo não é apagada).',
  MODIFY `requested_by_user_id` int DEFAULT NULL COMMENT 'FK app_users.id: quem fez o pedido. NULL se o usuário foi apagado.',
  MODIFY `title` varchar(255) NOT NULL COMMENT 'Título interno do conteúdo (não é o título da publicação).',
  MODIFY `type` varchar(20) NOT NULL COMMENT 'video | image. Define as etapas (jobs) do pipeline.',
  MODIFY `status` varchar(20) NOT NULL DEFAULT 'draft' COMMENT 'Etapa atual do conteúdo, derivada dos jobs. Valores em docs/reestruturacao.md; a API valida.',
  MODIFY `request` json NOT NULL COMMENT 'Pedido original inteiro, como chegou na API. Nunca é alterado.',
  MODIFY `settings` json DEFAULT NULL COMMENT 'brand.defaults + configurações do pedido, mesclados e congelados no momento do pedido.',
  MODIFY `video_key` varchar(512) DEFAULT NULL COMMENT 'Chave no storage do vídeo concatenado SEM áudio (concat_video). NULL em imagem.',
  MODIFY `audio_key` varchar(512) DEFAULT NULL COMMENT 'Chave no storage da faixa de áudio final: narração + música + SFX (render_audio). NULL em imagem.',
  MODIFY `output_key` varchar(512) DEFAULT NULL COMMENT 'Chave no storage do arquivo final: MP4 (mux de video_key + audio_key) ou PNG (render_image).',
  MODIFY `error` text COMMENT 'Última mensagem de erro do conteúdo. NULL quando não há falha.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o pedido foi recebido.',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

ALTER TABLE `app_content_chapters`
  COMMENT = 'Capítulo opcional de um conteúdo (vídeo longo). Agrupa cenas; short não tem capítulo.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `content_id` int NOT NULL COMMENT 'FK app_contents.id.',
  MODIFY `position` int NOT NULL COMMENT 'Ordem do capítulo no conteúdo (1, 2, 3...). Único por conteúdo.',
  MODIFY `title` varchar(255) DEFAULT NULL COMMENT 'Título do capítulo (pode virar o chapter do YouTube).',
  MODIFY `settings` json DEFAULT NULL COMMENT 'Configurações que valem para todas as cenas do capítulo. Mesclagem: content.settings > chapter.settings > scene.request.',
  MODIFY `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | rendering | rendered | failed. A API valida.',
  MODIFY `error` text COMMENT 'Última mensagem de erro do capítulo. NULL quando não há falha.',
  MODIFY `render_ms` int DEFAULT NULL COMMENT 'Tempo (ms) do render do capítulo, para achar gargalos.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

ALTER TABLE `app_content_scenes`
  COMMENT = 'Cena de um conteúdo: pedido da cena, insumos resolvidos pelo prepare e arquivos renderizados.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `content_id` int NOT NULL COMMENT 'FK app_contents.id.',
  MODIFY `chapter_id` int DEFAULT NULL COMMENT 'FK app_content_chapters.id (mesmo conteúdo, FK composta). NULL quando o conteúdo não tem capítulos.',
  MODIFY `position` int NOT NULL COMMENT 'Ordem global da cena no conteúdo (1, 2, 3...), independente de capítulo. Único por conteúdo.',
  MODIFY `request` json NOT NULL COMMENT 'Cena como chegou no pedido (narração, visuais, motion...).',
  MODIFY `request_hash` char(64) DEFAULT NULL COMMENT 'sha256 do request da cena. Mudou o hash = a cena precisa de novo prepare e render.',
  MODIFY `resolved` json DEFAULT NULL COMMENT 'Saída do prepare: a cena com todos os insumos já gerados (só chaves do storage, duração, timestamps). Entrada do videomaker.',
  MODIFY `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'Etapa atual da cena, derivada dos jobs. Valores em docs/reestruturacao.md; a API valida.',
  MODIFY `preview_key` varchar(512) DEFAULT NULL COMMENT 'Chave no storage do preview de baixa qualidade da cena (job preview).',
  MODIFY `output_key` varchar(512) DEFAULT NULL COMMENT 'Chave no storage da saída da cena: MP4 SEM áudio (render_video) ou PNG (render_image).',
  MODIFY `preview_ms` int DEFAULT NULL COMMENT 'Tempo (ms) do último preview da cena.',
  MODIFY `render_ms` int DEFAULT NULL COMMENT 'Tempo (ms) do último render da cena.',
  MODIFY `error` text COMMENT 'Última mensagem de erro da cena. NULL quando não há falha.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

ALTER TABLE `app_jobs`
  COMMENT = 'Fila de tarefas lida pelo worker. Um job = uma etapa do pipeline de um conteúdo ou de uma cena. Plano e dependências em docs/reestruturacao.md (Jobs do conteúdo).',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `content_id` int NOT NULL COMMENT 'FK app_contents.id: conteúdo a que o job pertence.',
  MODIFY `scene_id` int DEFAULT NULL COMMENT 'FK app_content_scenes.id: cena do job. NULL = job do conteúdo inteiro (render_audio, concat_video, mux...).',
  MODIFY `type` varchar(30) NOT NULL COMMENT 'Etapa: prepare | preview | render_video | render_audio | concat_video | mux | render_image. A API valida.',
  MODIFY `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | running | done | failed.',
  MODIFY `attempts` int NOT NULL DEFAULT '0' COMMENT 'Quantas vezes o worker já tentou executar.',
  MODIFY `error` text COMMENT 'Mensagem de erro da última tentativa. NULL quando não há falha.',
  MODIFY `started_at` datetime(3) DEFAULT NULL COMMENT 'Início da última execução.',
  MODIFY `finished_at` datetime(3) DEFAULT NULL COMMENT 'Fim da última execução (done ou failed).',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o job foi criado (entra na fila).',
  MODIFY `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Última alteração do registro (automático).';

-- ---------------------------------------------------------------- legado (destino pendente na reestruturação)
ALTER TABLE `app_remote_assets`
  COMMENT = 'LEGADO: grupo de mídias remotas (ex.: banco de vídeos de fundo) usado pelo type remote_asset. Destino pendente na reestruturação.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `name` varchar(255) NOT NULL COMMENT 'Nome de exibição do grupo.',
  MODIFY `slug` varchar(255) NOT NULL COMMENT 'Identificador do grupo, usado no JSON de vídeo. Único.',
  MODIFY `description` text COMMENT 'Descrição livre do grupo.',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.',
  MODIFY `updated_at` datetime(3) NOT NULL COMMENT 'Última alteração (preenchida pela aplicação, sem default).';

ALTER TABLE `app_remote_assets_midia`
  COMMENT = 'LEGADO: cada mídia (URL) de um grupo de app_remote_assets.',
  MODIFY `id` int NOT NULL AUTO_INCREMENT COMMENT 'PK interna.',
  MODIFY `id_asset` int NOT NULL COMMENT 'FK app_remote_assets.id: grupo da mídia.',
  MODIFY `url` text NOT NULL COMMENT 'URL pública do arquivo.',
  MODIFY `type` varchar(20) NOT NULL DEFAULT 'unknown' COMMENT 'image | video | unknown (inferido pela extensão da URL).',
  MODIFY `extension` varchar(20) DEFAULT NULL COMMENT 'Extensão do arquivo (jpg, mp4...).',
  MODIFY `is_invalid` tinyint(1) NOT NULL DEFAULT '0' COMMENT '1 = URL quebrada ou mídia inválida; não é sorteada.',
  MODIFY `last_used` datetime(3) DEFAULT NULL COMMENT 'Última vez que a mídia foi usada (para rodízio, evitando repetição).',
  MODIFY `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Quando o registro foi criado.';
