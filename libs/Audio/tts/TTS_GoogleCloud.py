            result = worker.model.transcribe(
                audio_path,
                word_timestamps=True,
                language=self.whisper_language,
                initial_prompt=self.text or None,
            )