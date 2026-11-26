CREATE TABLE `app_brand_account_youtube` (
  `id` int NOT NULL AUTO_INCREMENT,
  `brand_id` int NOT NULL,
  `channel_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `channel_title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `access_token` text COLLATE utf8mb4_unicode_ci,
  `refresh_token` text COLLATE utf8mb4_unicode_ci,
  `token_expires_at` datetime(3) DEFAULT NULL,
  `default_privacy` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'private',
  `default_category_id` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `app_brand_account_youtube_channel_id_key` (`channel_id`),
  KEY `app_brand_account_youtube_brand_id_idx` (`brand_id`),
  CONSTRAINT `app_brand_account_youtube_brand_id_fkey` FOREIGN KEY (`brand_id`) REFERENCES `app_brands` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
