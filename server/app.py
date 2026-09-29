"""HTTP server wrapping the pipeline.

    POST /talk   multipart: audio=<wav file>, lang=<optional: english|yoruba|hausa|igbo>
                 -> JSON {language, lid_scores, transcript, reply, timings, audio_b64 (wav, 24 kHz)}
    GET  /health

Every turn is saved to logs/ (input wav, reply wav, and a line in turns.jsonl)
so we can build and score the Phase 1 test set.
"""
import base64
import io
import json
import os
import uuid
from datetime import datetime

import librosa
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from pipeline import ASR_SR, LANGS, TTS_SR, Pipeline

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

app = FastAPI()
pipeline = Pipeline()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/talk")
async def talk(audio: UploadFile = File(...), lang: str | None = Form(None)):
    if lang and lang not in LANGS:
        raise HTTPException(400, f"lang must be one of {LANGS}")
    raw = await audio.read()
    try:
        samples, _ = librosa.load(io.BytesIO(raw), sr=ASR_SR, mono=True)
    except Exception as e:
        raise HTTPException(400, f"could not read audio: {e}")
    if len(samples) < ASR_SR * 0.3:
        raise HTTPException(400, "audio too short")

    r = pipeline.run(samples, lang)

    buf = io.BytesIO()
    sf.write(buf, r.audio, TTS_SR, format="WAV")
    reply_wav = buf.getvalue()

    turn_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    with open(os.path.join(LOG_DIR, f"{turn_id}-in.wav"), "wb") as f:
        f.write(raw)
    with open(os.path.join(LOG_DIR, f"{turn_id}-out.wav"), "wb") as f:
        f.write(reply_wav)
    row = {
        "id": turn_id,
        "forced_lang": lang,
        "language": r.language,
        "lid_scores": r.lid_scores,
        "transcript": r.transcript,
        "reply": r.reply,
        "timings": r.timings,
    }
    with open(os.path.join(LOG_DIR, "turns.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {**row, "audio_b64": base64.b64encode(reply_wav).decode()}
