CREATE TABLE `app_contents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `uid` char(26) COLLATE utf8mb4_unicode_ci NOT NULL,
  `brand_id` int NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `request` json NOT NULL,
  `settings` json DEFAULT NULL,
  `output_key` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `app_contents_uid_key` (`uid`),
  KEY `app_contents_brand_id_idx` (`brand_id`),
  KEY `app_contents_status_idx` (`status`),
  CONSTRAINT `app_contents_brand_id_fkey` FOREIGN KEY (`brand_id`) REFERENCES `app_brands` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
