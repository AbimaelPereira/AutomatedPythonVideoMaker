import sys
import os
import re
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sqlmodel import Session
from database import get_session
from middleware.auth import get_current_user
from auth.models import User

# Garante que videomaker/ é importável
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "videomaker"))
from reelscutter import ReelsCutter

router = APIRouter()

VIDEOMAKER_DIR = Path(__file__).parent.parent.parent / "videomaker"


def _make_cutter(channel_name: str, config: dict) -> ReelsCutter:
    return ReelsCutter(
        channel_name=config.get("channel_name", channel_name),
        temp_dir=str(VIDEOMAKER_DIR / "temp"),
        jsons_dir=str(VIDEOMAKER_DIR / "jsons"),
        min_words=config.get("min_words", 12),
        max_words=config.get("max_words", 18),
        min_duration=config.get("min_duration", 55),
        max_duration=config.get("max_duration", 85),
    )


class TranscriptRequest(BaseModel):
    url: str

class ProcessRequest(BaseModel):
    url: str
    video_id: str
    transcription_text: str
    channel_name: str = "default"
    config: dict = {}

class GenerateRequest(BaseModel):
    audio_path: str
    clips: list[dict]
    channel_name: str = "default"
    config: dict = {}

class SaveJsonsRequest(BaseModel):
    json_path: str
    clips: list[dict]


@router.post("/transcript")
def transcript(body: TranscriptRequest, _: User = Depends(get_current_user)):
    try:
        cutter = ReelsCutter(channel_name="default", temp_dir=str(VIDEOMAKER_DIR / "temp"),
                             jsons_dir=str(VIDEOMAKER_DIR / "jsons"))
        return cutter.get_transcript(body.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process")
def process(body: ProcessRequest, _: User = Depends(get_current_user)):
    try:
        cutter = _make_cutter(body.channel_name, body.config)
        return cutter.process(body.url, body.video_id, body.transcription_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
def generate(body: GenerateRequest, _: User = Depends(get_current_user)):
    try:
        cutter = _make_cutter(body.channel_name, body.config)
        raw = cutter.generate(body.audio_path, body.clips)

        results = []
        for i, r in enumerate(raw):
            original_clip = body.clips[i] if i < len(body.clips) else {}
            if "error" in r:
                results.append({"clip_number": r["clip_number"], "clip": original_clip, "error": r["error"]})
            else:
                doc = r["data"]
                audio_file = doc.get("global_settings", {}).get("tts", {}).get("audio_file", "")
                results.append({
                    "clip_number": r["clip_number"],
                    "clip": original_clip,
                    "audio": Path(audio_file).name,
                    "json": doc,
                })

        video_id = Path(body.audio_path).stem
        json_path = cutter.save_consolidated(video_id, raw)
        return {"results": results, "json_path": json_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-jsons")
def save_jsons(body: SaveJsonsRequest, _: User = Depends(get_current_user)):
    try:
        with open(body.json_path, "w", encoding="utf-8") as f:
            json.dump(body.clips, f, ensure_ascii=False, indent=2)
        return {"path": body.json_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio")
def serve_audio(path: str, token: str, request: Request, session: Session = Depends(get_session)):
    from auth.service import decode_access_token
    from jose import JWTError
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token inválido")

    if not session.get(User, user_id):
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_size = os.path.getsize(path)
    range_header = request.headers.get("Range")

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end   = int(m.group(2)) if m.group(2) else file_size - 1
            end   = min(end, file_size - 1)
            length = end - start + 1

            def stream_range():
                with open(path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                stream_range(),
                status_code=206,
                media_type="audio/mpeg",
                headers={
                    "Content-Range":  f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges":  "bytes",
                    "Content-Length": str(length),
                },
            )

    def stream():
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        stream(),
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges":  "bytes",
            "Content-Length": str(file_size),
        },
    )
