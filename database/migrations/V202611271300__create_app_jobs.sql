-- Fila de tarefas (prepare, render...) lida pelo worker.
-- status: pending | running | done | failed
CREATE TABLE `app_jobs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `content_id` int NOT NULL,
  `scene_id` int DEFAULT NULL,
  `type` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempts` int NOT NULL DEFAULT '0',
  `error` text COLLATE utf8mb4_unicode_ci,
  `started_at` datetime(3) DEFAULT NULL,
  `finished_at` datetime(3) DEFAULT NULL,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `app_jobs_status_created_idx` (`status`, `created_at`),
  KEY `app_jobs_content_id_idx` (`content_id`),
  KEY `app_jobs_scene_id_idx` (`scene_id`),
  CONSTRAINT `app_jobs_content_id_fkey` FOREIGN KEY (`content_id`) REFERENCES `app_contents` (`id`) ON DELETE CASCADE,
  CONSTRAINT `app_jobs_scene_id_fkey` FOREIGN KEY (`scene_id`) REFERENCES `app_content_scenes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
