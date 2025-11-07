from libs.TemplateMaster import TemplateMaster
import json
import os

if __name__ == "__main__":
    with open("json_teste.json", "r", encoding="utf-8") as f:
        json_list = json.load(f)

    for json_data in json_list:
        #convert to dict
        json_data = dict(json_data)

        
        video_config = {
            "slug": json_data.slug,
            "output_folder": "output/" + json_data.slug,
            "output_ratio": json_data.output_ratio,
        }

        tm = TemplateMaster(video_config)
        tm.validate_configs()


        audio_narration, subtitle_clips = tm.narration_subtitles(json_data.tts)

        final = subtitle_clips
        final.set_audio(audio_narration)

        final.write_videofile(
            os.path.join(tm.output_folder, tm.slug + ".mp4"),
            codec="libx264",
            audio_codec="aac",
            fps=24,
            threads=5,
            temp_audiofile=os.path.join(tm.output_folder, "temp-audio.m4a"),
            remove_temp=True,
            bitrate="4000k",
            preset="superfast",
        )
