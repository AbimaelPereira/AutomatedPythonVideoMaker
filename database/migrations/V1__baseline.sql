-- Baseline: estrutura do banco em 2026-11-26 (gerada de anonimo_prod)
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE `app_channels` (
  `id` int NOT NULL AUTO_INCREMENT,
  `slug` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `config` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` int NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `app_jobs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `id_user` int NOT NULL,
  `type` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `config` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `output` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `id_user` (`id_user`),
  CONSTRAINT `app_jobs_ibfk_1` FOREIGN KEY (`id_user`) REFERENCES `si_users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `app_remote_assets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `slug` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `app_remote_assets_slug_key` (`slug`),
  KEY `app_remote_assets_slug_idx` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `app_remote_assets_midia` (
  `id` int NOT NULL AUTO_INCREMENT,
  `id_asset` int NOT NULL,
  `url` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unknown',
  `extension` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_invalid` tinyint(1) NOT NULL DEFAULT '0',
  `last_used` datetime(3) DEFAULT NULL,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `app_remote_assets_midia_id_asset_idx` (`id_asset`),
  CONSTRAINT `app_remote_assets_midia_id_asset_fkey` FOREIGN KEY (`id_asset`) REFERENCES `app_remote_assets` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `app_videos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `youtube_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `channel_id` int DEFAULT NULL,
  `slug` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `tags` text COLLATE utf8mb4_unicode_ci,
  `category_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `duration_seconds` float DEFAULT NULL,
  `thumbnail_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `transcript` text COLLATE utf8mb4_unicode_ci,
  `privacy_status` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `published_at` datetime DEFAULT NULL,
  `views` int DEFAULT NULL,
  `likes` int DEFAULT NULL,
  `comments` int DEFAULT NULL,
  `shares` int DEFAULT NULL,
  `subscribers_gained` int DEFAULT NULL,
  `subscribers_lost` int DEFAULT NULL,
  `impressions` int DEFAULT NULL,
  `impressions_ctr_rate` float DEFAULT NULL,
  `average_view_duration` float DEFAULT NULL,
  `average_view_percentage` float DEFAULT NULL,
  `estimated_minutes_watched` float DEFAULT NULL,
  `audience_retention_data` text COLLATE utf8mb4_unicode_ci,
  `top_countries` text COLLATE utf8mb4_unicode_ci,
  `age_group_data` text COLLATE utf8mb4_unicode_ci,
  `traffic_source_types` text COLLATE utf8mb4_unicode_ci,
  `metrics_updated_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `r2_files` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_app_videos_youtube_id` (`youtube_id`),
  KEY `channel_id` (`channel_id`),
  CONSTRAINT `app_videos_ibfk_1` FOREIGN KEY (`channel_id`) REFERENCES `app_channels` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `si_groups` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `permissions` json DEFAULT NULL,
  `status` int NOT NULL DEFAULT '1',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `si_modules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `id_parent` int DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `slug` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `icon` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` int NOT NULL DEFAULT '1',
  `order_by` int NOT NULL DEFAULT '1',
  `show_in_menu` int NOT NULL DEFAULT '1',
  `actions` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `si_modules_id_parent_idx` (`id_parent`),
  CONSTRAINT `si_modules_id_parent_fkey` FOREIGN KEY (`id_parent`) REFERENCES `si_modules` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `si_refresh_tokens` (
  `id` int NOT NULL AUTO_INCREMENT,
  `token` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `id_user` int NOT NULL,
  `expires_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_si_refresh_tokens_token` (`token`),
  KEY `id_user` (`id_user`),
  CONSTRAINT `si_refresh_tokens_ibfk_1` FOREIGN KEY (`id_user`) REFERENCES `si_users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE `si_users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` int NOT NULL DEFAULT '1',
  `id_group` int DEFAULT NULL,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `si_users_email_key` (`email`),
  KEY `si_users_id_group_idx` (`id_group`),
  CONSTRAINT `si_users_id_group_fkey` FOREIGN KEY (`id_group`) REFERENCES `si_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
