ALTER TABLE `app_contents`
  ADD COLUMN `requested_by_user_id` int DEFAULT NULL AFTER `brand_id`,
  ADD KEY `app_contents_requested_by_user_id_idx` (`requested_by_user_id`),
  ADD CONSTRAINT `app_contents_requested_by_user_id_fkey` FOREIGN KEY (`requested_by_user_id`) REFERENCES `app_users` (`id`) ON DELETE SET NULL;
