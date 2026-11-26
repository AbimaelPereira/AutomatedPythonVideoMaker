CREATE TABLE `app_content_chapters` (
  `id` int NOT NULL AUTO_INCREMENT,
  `content_id` int NOT NULL,
  `position` int NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `settings` json DEFAULT NULL,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `app_content_chapters_content_position_key` (`content_id`, `position`),
  CONSTRAINT `app_content_chapters_content_id_fkey` FOREIGN KEY (`content_id`) REFERENCES `app_contents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
