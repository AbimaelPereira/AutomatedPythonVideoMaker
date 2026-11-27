-- Saída da cena: MP4 sem áudio (vídeo) ou PNG (imagem). Mesmo nome do app_contents.
ALTER TABLE `app_content_scenes`
  RENAME COLUMN `video_key` TO `output_key`;
