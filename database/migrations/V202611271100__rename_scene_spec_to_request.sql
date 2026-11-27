-- Padroniza com app_contents.request: cena como chegou no pedido.
ALTER TABLE `app_content_scenes`
  RENAME COLUMN `spec` TO `request`,
  RENAME COLUMN `spec_hash` TO `request_hash`;
