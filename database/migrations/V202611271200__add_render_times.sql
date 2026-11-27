-- Tempo gasto (ms) em cada etapa do videomaker, para achar gargalos.
ALTER TABLE `app_content_scenes`
  ADD COLUMN `preview_ms` int DEFAULT NULL AFTER `video_key`,
  ADD COLUMN `render_ms` int DEFAULT NULL AFTER `preview_ms`;

ALTER TABLE `app_content_chapters`
  ADD COLUMN `render_ms` int DEFAULT NULL AFTER `error`;
