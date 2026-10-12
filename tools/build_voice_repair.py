import base64, io
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT = Path(__file__).resolve().parents[1]
import os
os.chdir(ROOT)
paths=['server/app.py','server/learning.py','server/pipeline.py','server/web/app.js','server/web/sw.js']
b=io.BytesIO()
with ZipFile(b,'w',ZIP_DEFLATED) as z:
 for path in paths: z.write(path,path)
payload=base64.b64encode(b.getvalue()).decode()
script='''# Copy this entire file into ONE new code cell in the existing Kaggle notebook.
# It updates the app and restarts only its server. The GPU session, token,
# downloaded weights and existing HTTPS tunnel remain in place.
import base64, io, os, subprocess, sys, time, zipfile
from pathlib import Path
import requests

if "WORK" not in globals() or "server_process" not in globals():
    raise RuntimeError("Run this inside the existing demo notebook session, where the server was started.")

PATCH = (
'''
for i in range(0,len(payload),100): script+='    "'+payload[i:i+100]+'"\n'
script+=''' )
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
'''
compile(script,'repair_voice_demo.py','exec')
Path('demos/repair_voice_demo.py').write_text(script)
print('Repair cell created; source compiles; updates the API, tutor pipeline/prompt and browser assets.')
