CREATE TABLE `app_brand_users` (
  `brand_id` int NOT NULL,
  `user_id` int NOT NULL,
  `role` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'owner',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`brand_id`, `user_id`),
  KEY `app_brand_users_user_id_idx` (`user_id`),
  CONSTRAINT `app_brand_users_brand_id_fkey` FOREIGN KEY (`brand_id`) REFERENCES `app_brands` (`id`) ON DELETE CASCADE,
  CONSTRAINT `app_brand_users_user_id_fkey` FOREIGN KEY (`user_id`) REFERENCES `app_users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
