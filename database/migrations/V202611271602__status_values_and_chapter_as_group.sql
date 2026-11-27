-- Capítulo é só agrupamento (título + settings, ex.: música própria); não renderiza nada sozinho.
ALTER TABLE `app_content_chapters`
  DROP COLUMN `status`,
  DROP COLUMN `error`,
  DROP COLUMN `render_ms`;

-- Status definidos (docs/reestruturacao.md). Conteúdo começa em queued (antes: draft).
ALTER TABLE `app_contents`
  MODIFY `status` varchar(20) NOT NULL DEFAULT 'queued' COMMENT 'queued | preparing | prepared | rendering | rendered | failed. Derivado dos jobs; publicação tem status próprio fora daqui. A API valida.';

ALTER TABLE `app_content_scenes`
  MODIFY `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | preparing | prepared | previewed | rendering | rendered | failed. Derivado dos jobs da cena. A API valida.';
