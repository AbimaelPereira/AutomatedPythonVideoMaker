-- Token preso a 1 usuário + 1 marca. Guarda só o sha256; o token puro é exibido uma vez.
CREATE TABLE `app_api_tokens` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `brand_id` int NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `prefix` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_used_at` datetime(3) DEFAULT NULL,
  `expires_at` datetime(3) DEFAULT NULL,
  `revoked_at` datetime(3) DEFAULT NULL,
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `app_api_tokens_token_hash_key` (`token_hash`),
  KEY `app_api_tokens_brand_user_idx` (`brand_id`, `user_id`),
  CONSTRAINT `app_api_tokens_brand_user_fkey` FOREIGN KEY (`brand_id`, `user_id`) REFERENCES `app_brand_users` (`brand_id`, `user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
