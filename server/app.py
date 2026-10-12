"""Same-origin learning PWA and inference API. Models load on first request."""
import base64
import html
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from learning import LANGS, SUBJECTS, LEVELS, MODES
from lessons import LESSONS

HERE = Path(__file__).resolve().parent
MAX_UPLOAD = 4 * 1024 * 1024
MAX_SECONDS = 60
app = FastAPI(title="Naija Learn")
app.mount("/static", StaticFiles(directory=HERE / "web"), name="static")
pipeline = None
inference_lock = threading.Lock()
# A bounded, process-local pilot queue; run one server worker. No learner accounts.
job_lock = threading.Lock()
jobs = {}
job_slots = threading.BoundedSemaphore(8)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="learning-tutor")
JOB_TTL = 15 * 60


def get_pipeline():
    global pipeline
    if pipeline is None:
        from pipeline import Pipeline
        pipeline = Pipeline()
    return pipeline


def options(lang, subject, level, mode, auto=False):
    if lang not in LANGS and not (auto and lang is None):
        raise HTTPException(400, "Choose a supported language.")
    if subject not in SUBJECTS or level not in LEVELS or mode not in MODES:
        raise HTTPException(400, "Choose a valid subject, level and learning task.")


def decode_audio(raw):
    import numpy as np
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input"
        source.write_bytes(raw)
        try:
            result = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(source), "-t", str(MAX_SECONDS + 1),
                 "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"],
                capture_output=True, timeout=20, check=True,
            )
        except FileNotFoundError:
            raise HTTPException(503, "Audio processing is unavailable. Please type your question.")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise HTTPException(400, "Could not read this recording. Try another file or type your question.")
    samples = np.frombuffer(result.stdout, dtype="<f4").copy()
    if not 4800 <= len(samples) <= MAX_SECONDS * 16000:
        raise HTTPException(400, "Record between 0.3 and 60 seconds of speech.")
    return samples


def infer(kind, value, lang, subject, level, mode, with_audio):
    if os.getenv("TUTOR_ENABLED", "1") == "0":
        raise HTTPException(503, "The tutor is not enabled on this server. You can still read lessons and try quizzes.")
    if not inference_lock.acquire(blocking=False):
        raise HTTPException(503, "The tutor is busy. Please try again shortly.")
    try:
        samples = decode_audio(value) if kind == "voice" else None
        p = get_pipeline()
        if kind == "voice":
            r = p.run(samples, lang, subject, level, mode, with_audio)
            row = {"language": r.language, "lid_scores": r.lid_scores, "transcript": r.transcript,
                   "reply": r.reply, "timings": r.timings}
            audio = r.audio
        else:
            start = time.monotonic()
            reply = p.respond(value, lang, subject, level, mode)
            row = {"language": lang, "lid_scores": {}, "transcript": value, "reply": reply,
                   "timings": {"llm": round(time.monotonic() - start, 2)}}
            audio = p.speak(reply, lang) if with_audio else None
            row["timings"]["total"] = round(time.monotonic() - start, 2)
        row.update(id=uuid.uuid4().hex, subject=subject, level=level, mode=mode)
        if with_audio and audio is not None and len(audio):
            import soundfile as sf
            buf = io.BytesIO()
            sf.write(buf, audio, 24000, format="WAV")
            row["audio_b64"] = base64.b64encode(buf.getvalue()).decode()
        if os.getenv("SAVE_TURNS") == "1":
            logs = HERE / "logs"
            logs.mkdir(exist_ok=True)
            with (logs / "turns.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({k: v for k, v in row.items() if k != "audio_b64"}, ensure_ascii=False) + "\n")
        return row
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        logging.exception("Learning request failed")
        raise HTTPException(503, "The tutor could not answer right now. Please try again shortly.")
    finally:
        inference_lock.release()


@app.get("/")
def home():
    return FileResponse(HERE / "web" / "index.html")


@app.get("/sw.js")
def worker():
    return FileResponse(HERE / "web" / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {"ok": True, "models_loaded": pipeline is not None, "tutor_enabled": os.getenv("TUTOR_ENABLED", "1") != "0"}


@app.post("/talk")
async def talk(audio: UploadFile = File(...), lang: str | None = Form(None), subject: str = Form("general"),
               level: str = Form("primary"), mode: str = Form("explain"), with_audio: bool = Form(True)):
    options(lang, subject, level, mode, auto=True)
    raw = await audio.read(MAX_UPLOAD + 1)
    await audio.close()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Recording is too large. Use a file under 4 MB.")
    return await run_in_threadpool(infer, "voice", raw, lang, subject, level, mode, with_audio)


@app.post("/learn")
async def learn(question: str = Form(...), lang: str = Form("english"), subject: str = Form("general"),
                level: str = Form("primary"), mode: str = Form("explain"), with_audio: bool = Form(False),
                format: str = Form("json")):
    try:
        options(lang, subject, level, mode)
        question = question.strip()
        if not question or len(question) > 1000:
            raise HTTPException(400, "Enter a question between 1 and 1,000 characters.")
        if format == "html":
            job_id = enqueue(question, lang, subject, level, mode, with_audio)
            return RedirectResponse("/jobs/" + job_id, status_code=303)
        row = await run_in_threadpool(infer, "text", question, lang, subject, level, mode, with_audio)
    except HTTPException as exc:
        if format == "html":
            return HTMLResponse(basic_page("Please try again", str(exc.detail)), status_code=exc.status_code)
        raise
    return row


def basic_page(question, reply):
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Naija Learn · Answer</title><link rel="stylesheet" href="/static/style.css"><body><main>'
            '<a href="/">← Ask another question</a><h1>Your learning answer</h1><h2>' + html.escape(question) +
            '</h2><p>' + html.escape(reply) + '</p><p>Check important facts with your teacher or learning materials.</p></main></body></html>')


def enqueue(question, lang, subject, level, mode, with_audio):
    if not job_slots.acquire(blocking=False):
        raise HTTPException(503, "The tutor queue is full. Read a lesson and try again shortly.")
    job_id = uuid.uuid4().hex
    with job_lock:
        now = time.monotonic()
        for old_id, job in list(jobs.items()):
            if job["state"] != "pending" and now - job["updated"] > JOB_TTL:
                del jobs[old_id]
        # Bound retained results even when requests arrive faster than expiry.
        while len(jobs) >= 128:
            finished = [key for key, job in jobs.items() if job["state"] != "pending"]
            if not finished:
                break
            del jobs[finished[0]]
        jobs[job_id] = {"state": "pending", "question": question, "updated": now}
    try:
        executor.submit(complete_job, job_id, question, lang, subject, level, mode, with_audio)
    except RuntimeError:
        with job_lock:
            jobs.pop(job_id, None)
        job_slots.release()
        raise HTTPException(503, "The tutor is restarting. Try again shortly.")
    return job_id


def complete_job(job_id, question, lang, subject, level, mode, with_audio):
    try:
        result = infer("text", question, lang, subject, level, mode, with_audio)
        update = {"state": "done", "result": result}
    except HTTPException as exc:
        update = {"state": "failed", "error": str(exc.detail)}
    except Exception:
        logging.exception("Tutor job failed")
        update = {"state": "failed", "error": "The tutor could not answer. Please try again."}
    finally:
        job_slots.release()
    with job_lock:
        jobs[job_id].update(update, updated=time.monotonic())


@app.get("/jobs/{job_id}")
def job_page(job_id: str):
    with job_lock:
        job = jobs.get(job_id)
        if not job or (job["state"] != "pending" and time.monotonic() - job["updated"] > JOB_TTL):
            jobs.pop(job_id, None)
            return HTMLResponse(basic_page("Answer unavailable", "This answer expired or the server restarted. Please ask again."), status_code=404, headers={"Cache-Control": "no-store"})
        job = dict(job)
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if job["state"] == "pending":
        page = basic_page("Thinking…", "Your question is queued. This page checks again every four seconds. You can also use the link below.")
        page = page.replace('<title>', '<meta http-equiv="refresh" content="4"><title>', 1)
        page = page.replace('</main>', '<p><a href="/jobs/' + html.escape(job_id) + '">Check again</a></p><p><a href="/lessons">Read a lesson while you wait</a></p></main>')
        return HTMLResponse(page, headers=headers)
    if job["state"] == "failed":
        return HTMLResponse(basic_page(job["question"], job["error"]), headers=headers)
    result = job["result"]
    page = basic_page(job["question"], result["reply"])
    if result.get("audio_b64"):
        page = page.replace('</main>', '<audio controls preload="none" src="data:audio/wav;base64,' + result["audio_b64"] + '"></audio></main>')
    return HTMLResponse(page, headers=headers)


def lesson_page(title, body):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + html.escape(title) + ' · Naija Learn</title><link rel="stylesheet" href="/static/style.css"></head><body><main>'
            '<a href="/" accesskey="0">0 · Home / Ask the tutor</a><h1>' + html.escape(title) + '</h1>' + body + '</main></body></html>')


@app.get("/lessons")
def lesson_list():
    body = '<p>Short English starter lessons. Read a lesson, then try its check question. No microphone or AI connection is needed.</p><ul>'
    for index, (key, lesson) in enumerate(LESSONS.items(), 1):
        body += '<li><a accesskey="' + str(index) + '" href="/lessons/' + key + '">' + str(index) + ' · ' + html.escape(lesson["title"]) + '</a></li>'
    return HTMLResponse(lesson_page("Choose a lesson", body + '</ul>'))


@app.get("/lessons/{lesson_id}")
def read_lesson(lesson_id: str):
    lesson = LESSONS.get(lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found.")
    body = '<p class="eyebrow">' + html.escape(lesson["subject"]) + '</p><p>' + html.escape(lesson["text"]) + '</p><h2>Check your understanding</h2>'
    body += '<form method="post" action="/lessons/' + lesson_id + '/check"><p>' + html.escape(lesson["question"]) + '</p>'
    for i, choice in enumerate(lesson["choices"], 1):
        body += '<label><input type="radio" name="choice" value="' + str(i) + '" accesskey="' + str(i) + '" required> ' + str(i) + ' · ' + html.escape(choice) + '</label>'
    body += '<button type="submit">Check answer</button></form><p><a href="/lessons">Back to lessons</a></p>'
    return HTMLResponse(lesson_page(lesson["title"], body))


@app.post("/lessons/{lesson_id}/check")
def check_lesson(lesson_id: str, choice: int = Form(...)):
    lesson = LESSONS.get(lesson_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found.")
    if not 1 <= choice <= len(lesson["choices"]):
        raise HTTPException(400, "Choose one of the listed answers.")
    title = "That is correct!" if choice == lesson["correct"] else "Have another look"
    body = '<p>' + html.escape(lesson["explanation"]) + '</p><p><a href="/lessons/' + lesson_id + '">Read this lesson again</a></p><p><a href="/lessons">Choose another lesson</a></p>'
    return HTMLResponse(lesson_page(title, body))
