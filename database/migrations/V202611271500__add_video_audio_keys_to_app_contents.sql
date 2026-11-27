-- Vídeo e áudio renderizados separados; output_key passa a ser o mux dos dois.
-- video_key: cenas concatenadas sem áudio. audio_key: faixa final (narração + música + SFX).
ALTER TABLE `app_contents`
  ADD COLUMN `video_key` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER `settings`,
  ADD COLUMN `audio_key` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER `video_key`;
