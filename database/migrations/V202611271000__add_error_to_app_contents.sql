-- Erro de etapas do conteúdo inteiro (junção final, upload).
ALTER TABLE `app_contents`
  ADD COLUMN `error` text COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER `output_key`;
