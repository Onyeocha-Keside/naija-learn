# Copy this entire file into ONE new code cell in the existing Kaggle notebook.
# It updates the app and restarts only its server. The GPU session, token,
# downloaded weights and existing HTTPS tunnel remain in place.
import base64, io, os, subprocess, sys, time, zipfile
from pathlib import Path
import requests

if "WORK" not in globals() or "server_process" not in globals():
    raise RuntimeError("Run this inside the existing demo notebook session, where the server was started.")

PATCH = (
    "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"
    "AF0nAAASAAAAc2VydmVyL3BpcGVsaW5lLnB5tVptc9s2Ev6uX4FjphMypVlJcXOtW/WqOI7jqV8ytuNeTufhwCQkoaZABgDtqDnf"
    "b79dAHyVnKadOX0wSWCxWOzrA8Ce513lPGGk4AXLuGB7hJYpzwkXZOcnklGxKOmCkaNX+Dm9OMfH8fEJPi4vL/Bh6fNSR4PBeSlI"
    "yiVLdLYmOieaKU1yQSiZ84ztDQj8irVeQlM1YVSsiaKrImPRPb0js50dnJSsc1ne0OuB53kDvipyqckiqd5yVb1JVr2pdd2o+YoN"
    "5jJfkZRqmmRUKaaI66ybQpCJZWlNyHBYi8p8DyqeolyBoFQRUdTT5DJZ2uFaUqHmuVwxWU/km9VOS52/ZlSXkh18BLIERoV1z0me"
    "sux1Lqeow32Uis95QjXPxSbRPi0VzY5Pmp7L/JYJ/jtzHF9yraYifbkGte/nYs4Xtv3XJVcFk8giFylH7jQ7ZILJ1kyO6K3ME6YU"
    "ChkM7OIyRqXgYBO3sOPp6eFFSDQIIOMCKAo9GLw5OD8gE7BMVFC9jMAJBF0xv/qmNwqffhyjI8RxEAzAYLaPC8Wk9odhPfq3nAsf"
    "OYbEu2MizaUXBIQ8IYrpsojUkiRZLsCma5BsUWiyZNJZ3LVExit1pZ9KdKPnWmtXY+Qp8g90jxzsDseDwauDq6N9t44F00zc+d7h"
    "23exbfdAnKRM6d7QCwYQC/E28qYdyO1LMIBQ2UrctLeIX12+f4t0xr+ieZZTPXph5oPwm5DRi3g4HBqW5nu8a74HT8jJycXOMUTq"
    "0cUZScBpFAGXJHrJyG4dyYrcM6LKAtURDYA63j97dXABfD55TCy8PYKPjKslrhaiEFtsMGLDkpbYsERXxG9+k+M3X8DzYWCEPAF+"
    "x4ah8auaHZCd7k+PzkffnPIFk5yKaZIwoVl6UE1oB7jZGvr3pmEHmFckdv6G4g1+twmMQE3/EXy67gfU1JlgEP0fWUrubPYDF6lz"
    "ncqNzjAYlaYCUkteilSBSgW2gMiR0f7VGZhr60JbFjZE8cHp4fHRxRujsRTCzgv6a90Y8v7s/N3LqTMC0MQrmrFxPbDSwMa4N9N3"
    "F1NnKkXjOcNxo3qcU8zGsKPDl2dGPOh3g8xkoC5I99aosNTahDvTy2N64RkPqjvnNGE3eX77zWqldjKe7ozGLzyjq5pE0SVjqeBr"
    "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"
 )
# Stop the process owned by this notebook; do not touch other processes.
if server_process.poll() is None:
    server_process.terminate()
    try:
        server_process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        server_process.kill()
        server_process.wait(timeout=10)
with zipfile.ZipFile(io.BytesIO(base64.b64decode(PATCH))) as archive:
    for name in archive.namelist():
        if name not in {"server/app.py", "server/learning.py", "server/pipeline.py", "server/web/app.js", "server/web/sw.js"}:
            raise RuntimeError("Unexpected patch file")
        target = WORK / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))
SERVER = WORK / "server"
os.environ["LLM_MAX_TOKENS"] = "80"
server_log = open(WORK / "server.log", "w")
server_process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=SERVER, env=os.environ.copy(), stdout=server_log, stderr=subprocess.STDOUT,
)
for _ in range(40):
    if server_process.poll() is not None:
        raise RuntimeError((WORK / "server.log").read_text()[-5000:])
    try:
        if requests.get("http://127.0.0.1:8000/health", timeout=2).ok:
            break
    except requests.RequestException:
        pass
    time.sleep(1)
else:
    raise RuntimeError("Server restart failed. Inspect server.log.")
os.environ["LLM_MAX_TOKENS"] = "80"
print("Patch installed. Warming the real tutor from cached weights…")
response = requests.post("http://127.0.0.1:8000/learn", data={
    "question": "Explain one half in two short sentences.", "lang": "english", "subject": "maths", "with_audio": "false",
}, timeout=1800)
if not response.ok:
    print((WORK / "server.log").read_text()[-5000:])
    raise RuntimeError(response.text)
print("Tutor ready:", response.json()["reply"])
# This diagnostic uses the earlier generated WAV, not a user's microphone recording.
previous_audio = WORK / "first-spoken-answer.wav"
if previous_audio.exists():
    print("Checking speech recognition on the previous generated audio…")
    with previous_audio.open("rb") as recording:
        check = requests.post("http://127.0.0.1:8000/talk", files={"audio": ("speech.wav", recording, "audio/wav")},
            data={"lang": "english", "subject": "maths", "with_audio": "false"}, timeout=1800)
    if check.ok:
        print("Speech recognised:", check.json()["transcript"])
    else:
        print("Speech recognition failed:", check.status_code, check.text)
        print((WORK / "server.log").read_text()[-5000:])
print("Repair installed. Open your existing demo URL and hard-refresh (Cmd+Shift+R on Mac).")
print("Record once, wait for the written answer, then press Play in the answer section.")
if "demo_url" in globals():
    print("Demo URL:", demo_url)
