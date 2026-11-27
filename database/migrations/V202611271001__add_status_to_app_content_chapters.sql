-- Status do render do capítulo: pending | rendering | rendered | failed.
ALTER TABLE `app_content_chapters`
  ADD COLUMN `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' AFTER `settings`,
  ADD COLUMN `error` text COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER `status`;
