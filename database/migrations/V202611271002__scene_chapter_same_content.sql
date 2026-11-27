-- Garante no banco que a cena só aponta para capítulo do mesmo conteúdo.
ALTER TABLE `app_content_chapters`
  ADD UNIQUE KEY `app_content_chapters_id_content_key` (`id`, `content_id`);

ALTER TABLE `app_content_scenes`
  DROP FOREIGN KEY `app_content_scenes_chapter_id_fkey`;

ALTER TABLE `app_content_scenes`
  DROP INDEX `app_content_scenes_chapter_id_idx`,
  ADD KEY `app_content_scenes_chapter_content_idx` (`chapter_id`, `content_id`),
  ADD CONSTRAINT `app_content_scenes_chapter_content_fkey`
    FOREIGN KEY (`chapter_id`, `content_id`)
    REFERENCES `app_content_chapters` (`id`, `content_id`) ON DELETE CASCADE;
