"""Bundle current allowlisted app source into a self-contained Kaggle demo notebook."""
import base64
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = ['app.py', 'pipeline.py', 'learning.py', 'lessons.py', 'requirements.txt', 'setup.sh']
buf = io.BytesIO()
with ZipFile(buf, 'w', ZIP_DEFLATED) as archive:
    for name in FILES:
        archive.write(ROOT / 'server' / name, 'server/' + name)
    for path in sorted((ROOT / 'server' / 'web').iterdir()):
        if path.is_file() and path.suffix in {'.html', '.css', '.js', '.json', '.svg', '.png'}:
            archive.write(path, 'server/web/' + path.name)
payload = base64.b64encode(buf.getvalue()).decode()
cells = []
def md(text):
    cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(keepends=True)})
def code(text):
    cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': text.splitlines(keepends=True)})

md('''# Naija Learn — free GPU voice demo

This notebook contains the current app source. Use it for an interactive test and a short video, not permanent hosting. No fake answers are supplied.

**Before running:**
1. Import this notebook at https://www.kaggle.com/code . Sign in; enable **Internet** and **GPU T4 x2** (or an available NVIDIA GPU). GPU eligibility/availability depends on your account.
2. On Hugging Face, accept access conditions for `NCAIR1/N-ATLaS`, `NCAIR1/Yoruba-ASR`, `NCAIR1/Hausa-ASR`, `NCAIR1/Igbo-ASR`, and `NCAIR1/NigerianAccentedEnglish`.
3. Add a Kaggle secret named `HF_TOKEN` with a read token permitted to access those gated models; enable access for this notebook. Alternatively use the hidden prompt in cell 3. Do not paste your token into chat or notebook source.
4. Run cells in order. Setup downloads large model files and can take time. Restarting a session may require downloading them again.

The app is the same PWA, served by the notebook GPU. A temporary Cloudflare HTTPS link allows recording from your phone or laptop. Anyone with the link can access this temporary demo; keep it private and stop the tunnel afterward. The link ends when the tunnel or runtime stops. No Cloudflare account is needed. Keep this notebook and outputs private during testing.
''')
code('''import os, sys, platform
import torch
from pathlib import Path

if not torch.cuda.is_available():
    raise RuntimeError("Enable a GPU in Kaggle Settings → Accelerator before continuing.")
for i in range(torch.cuda.device_count()):
    print(f"GPU {i}: {torch.cuda.get_device_name(i)} · {torch.cuda.get_device_properties(i).total_memory / 1e9:.1f} GB")
print("Python:", platform.python_version(), "Torch:", torch.__version__)
os.environ.update(LOW_VRAM="1", LLM_4BIT="1", LLM_MAX_TOKENS="80", DOWNLOAD_ALL_MODELS="0", TUTOR_ENABLED="1", SAVE_TURNS="0", HF_HUB_DISABLE_XET="1", GPU_DEVICE="cuda:0")
# Dual T4 memory is not pooled. Place speech models on the second GPU explicitly.
if torch.cuda.device_count() > 1:
    os.environ.update(ASR_DEVICE="cuda:1", TTS_DEVICE="cuda:1")
else:
    os.environ.update(ASR_DEVICE="cuda:0", TTS_DEVICE="cuda:0")
WORK = Path("/kaggle/working/naija-learn-demo")
WORK.mkdir(parents=True, exist_ok=True)
''')
code('''import base64, io, zipfile
PAYLOAD = "''' + payload + '''"
with zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD))) as archive:
    for name in archive.namelist():
        target = (WORK / name).resolve()
        if not target.is_relative_to(WORK.resolve()):
            raise RuntimeError("Unexpected archive path")
    archive.extractall(WORK)
SERVER = WORK / "server"
print("App source unpacked.")
''')
code('''from getpass import getpass
try:
    from kaggle_secrets import UserSecretsClient
    token = UserSecretsClient().get_secret("HF_TOKEN")
except Exception:
    token = getpass("Hugging Face read token (hidden): ")
if not token.strip():
    raise RuntimeError("A Hugging Face token with model access is required.")
os.environ["HF_TOKEN"] = token.strip()
del token
print("Token configured without displaying it.")
''')
code('''import subprocess
# Uses the notebook's preinstalled CUDA PyTorch; does not install a second torch build.
subprocess.run(["bash", str(SERVER / "setup.sh")], check=True, env=os.environ.copy())
# If imports later fail after replacing a preloaded library, restart the notebook
# kernel and rerun cells 1–3 and 5 onward; the unpacked files remain in this session.
print("Setup complete.")
''')
code('''from huggingface_hub import hf_hub_download
# Small configuration requests catch missing gate approvals before loading weights.
for model in ["NCAIR1/N-ATLaS", "NCAIR1/NigerianAccentedEnglish", "NCAIR1/Hausa-ASR", "NCAIR1/Igbo-ASR", "NCAIR1/Yoruba-ASR"]:
    hf_hub_download(model, "config.json", token=os.environ["HF_TOKEN"])
print("Model access checks passed.")
''')
code('''import time, requests
# Stop only the server process started by this notebook when rerunning the cell.
if "server_process" in globals() and server_process.poll() is None:
    server_process.terminate()
    server_process.wait(timeout=20)
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
    raise RuntimeError("Server did not start. Inspect server.log below.")
print("Web app running. Next, load and check the real tutor.")
''')
code('''# Model loading happens once here, before you record your video.
print("Downloading/loading real N-ATLaS and YarnGPT models; please wait…")
response = requests.post("http://127.0.0.1:8000/learn", data={
    "question": "Explain one half using an orange.", "lang": "english",
    "subject": "maths", "level": "primary", "mode": "explain", "with_audio": "true",
}, timeout=1800)
if not response.ok:
    print((WORK / "server.log").read_text()[-5000:])
    raise RuntimeError(f"Tutor test failed: {response.status_code} {response.text}")
result = response.json()
print("Real model reply:", result["reply"])
print("Timings:", result["timings"])
if not result.get("audio_b64"):
    raise RuntimeError("Text worked but no speech was generated. Inspect server.log.")
from IPython.display import Audio, display
import base64
speech_bytes = base64.b64decode(result["audio_b64"])
(WORK / "first-spoken-answer.wav").write_bytes(speech_bytes)
display(Audio(speech_bytes))
''')
code('''# Verify ASR → tutor → TTS with a WAV you record and upload to the notebook.
# Use Kaggle's file upload / input tools, then enter its file path. Leave blank to
# test voice directly through the HTTPS page in the next cell instead.
audio_path = input("Optional path to a recorded question WAV (blank to skip): ").strip()
if audio_path:
    language = input("Language: english / hausa / igbo / yoruba: ").strip().lower()
    if language not in {"english", "hausa", "igbo", "yoruba"}:
        raise ValueError("Choose one of the four supported languages.")
    with open(audio_path, "rb") as recording:
        voice_response = requests.post("http://127.0.0.1:8000/talk", files={"audio": ("question.wav", recording, "audio/wav")},
            data={"lang": language, "subject": "maths", "level": "primary", "with_audio": "true"}, timeout=1800)
    if not voice_response.ok:
        print((WORK / "server.log").read_text()[-5000:])
        raise RuntimeError(voice_response.text)
    voice_result = voice_response.json()
    print("Recognised:", voice_result["transcript"])
    print("Answer:", voice_result["reply"])
    print("Timings:", voice_result["timings"])
    display(Audio(base64.b64decode(voice_result["audio_b64"])))
''')
code('''# Temporary HTTPS for your short demo. Anyone with the URL can access it.
import re, urllib.request
cloudflared = WORK / "cloudflared"
if not cloudflared.exists():
    urllib.request.urlretrieve("https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", cloudflared)
    cloudflared.chmod(0o755)
if "tunnel_process" in globals() and tunnel_process.poll() is None:
    tunnel_process.terminate()
    tunnel_process.wait(timeout=20)
tunnel_log = open(WORK / "tunnel.log", "w")
tunnel_process = subprocess.Popen([str(cloudflared), "tunnel", "--protocol", "http2", "--url", "http://127.0.0.1:8000"],
    stdout=tunnel_log, stderr=subprocess.STDOUT)
for _ in range(90):
    log = (WORK / "tunnel.log").read_text()
    match = re.search(r"https://[a-z0-9-]+\\.trycloudflare\\.com", log)
    if match:
        demo_url = match.group(0)
        break
    if tunnel_process.poll() is not None:
        raise RuntimeError(log[-4000:])
    time.sleep(1)
else:
    raise RuntimeError("No tunnel URL appeared. Inspect tunnel.log; notebook network restrictions may block tunnels.")
print("Open this URL to test and record your demo:", demo_url)
print("Select a language, record a short question, then play the answer. First use of each ASR language downloads its model.")
''')
md('''## Record a 3–5 minute video

1. Introduce the education use case and show the phone layout.
2. Open a lesson and submit its quiz to show the non-AI learning core.
3. Select a language you speak, allow microphone access, record a short learning question, and play the actual spoken response.
4. Show a typed question with spoken output disabled to demonstrate low-data access.
5. Explain that this is a temporary GPU test and that target feature phones, languages and teacher-reviewed content still need validation.

Do one full rehearsal before recording. Do not show tokens, inbox PINs or private participant information. Stop the runtime afterward; the link is temporary and free GPU quota is limited.

## Troubleshooting
- No GPU: enable an available accelerator; account verification may be needed. Do not create extra accounts to evade quotas.
- 401/403: accept each gated model's conditions using the same Hugging Face account as the token. Check read permissions.
- CUDA out of memory: check `LOW_VRAM=1` and `LLM_4BIT=1`. On dual T4, confirm ASR/TTS use `cuda:1`. Restart the session if a failed load retained memory; prefer one demo language first. Fitting all stages on a single free GPU has not been verified.
- Library import conflict: restart the kernel after installation, rerun configuration/token/server cells, and inspect `server.log`.
- WavTokenizer download fails: the upstream model uses a Google Drive checkpoint; quota/network restrictions can block it. Retry later instead of substituting an unrelated checkpoint.
- Cloudflare tunnel blocked: use the notebook audio upload/test cells for real inference; a live phone-web demo requires a network that allows the temporary tunnel.
- Microphone blocked: open the HTTPS link in a supported browser and allow recording; upload audio or type if needed.
- Link stopped working: check that the GPU session and both server/tunnel processes are still running.
''')
code('''# Inspect these logs if a cell fails. Tokens are not intentionally printed.
# Review logs before sharing them or including them in your recording.
print((WORK / "server.log").read_text()[-5000:] if (WORK / "server.log").exists() else "No server log yet.")
''')
code('''# Run when finished to stop the temporary service, then stop the Kaggle session.
for name in ["tunnel_process", "server_process"]:
    process = globals().get(name)
    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=20)
print("Demo processes stopped. End the GPU session in Kaggle.")
''')
notebook = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python'},
}, 'cells': cells}
for index, cell in enumerate(cells):
    cell['id'] = f'naija-demo-{index:02d}'
    if cell['cell_type'] == 'code':
        compile(''.join(cell['source']), f'cell-{index}', 'exec')
output = ROOT / 'demos' / 'Naija_Learn_Free_GPU.ipynb'
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(notebook, indent=2) + '\n')
print(f'Notebook built: {output.name}; {len(FILES)} core server files plus web assets; code cells compile.')
