-- app_brand_users: papel por marca não será usado; vínculo usuário↔marca basta.
ALTER TABLE `app_brand_users`
  DROP COLUMN `role`;

-- preview da cena é um PNG rápido (pose de repouso), não MP4.
ALTER TABLE `app_content_scenes`
  MODIFY `preview_key` varchar(512) DEFAULT NULL COMMENT 'Chave no storage do preview da cena: PNG de baixa qualidade (pose de repouso), rápido, para revisar antes do render (job preview).';
