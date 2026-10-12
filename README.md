# Naija Learn — voice-first education PWA

Ask learning questions in Yoruba, Hausa, Igbo or Nigerian English and read or hear an answer in the same language. A buildless phone web interface is served by FastAPI. The earlier smart-speaker PRD is historical; this README describes the current education implementation.

## Free GPU test and video

See [the demo setup](demos/FREE_GPU_DEMO.md) and import [the self-contained Kaggle notebook](demos/Naija_Learn_Free_GPU.ipynb). It includes this app's source, uses real model weights, checks speech generation and opens a temporary HTTPS link for recording. You must start an available Kaggle GPU session and provide your own Hugging Face model access. No GPU session has been connected from this workspace.

`LOW_VRAM=auto` uses lazy language-ID and a one-model ASR cache on GPUs with less than 20 GB memory. `LOW_VRAM=1` forces that mode. `GPU_DEVICE`, `ASR_DEVICE` and `TTS_DEVICE` can place N-ATLaS and speech models on separate GPUs; the notebook configures dual T4s automatically. YarnGPT synthesis uses fp16 for T4 compatibility. The larger-GPU loading path is retained. Short replies (1–3 sentences, with an 80-token default cap) reduce the amount of speech to synthesise. Real memory fit, latency and speech quality remain to be measured.

## Local preview without a GPU

Use Python 3.12 for the verified web setup. From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r server/web-requirements.txt
cd server
TUTOR_ENABLED=0 uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`. The interface, lessons and quizzes work; tutor requests explain that inference is disabled. This mode does not simulate AI answers. For real voice/text tutoring, use the full GPU setup below and leave `TUTOR_ENABLED` at its default of `1`.

## Phone web app

Start the server from `server/`:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000` on the laptop (the documented SSH tunnel still works). For a phone, deploy the GPU server behind an HTTPS reverse proxy and open its URL. Phone microphone access and PWA installation need a supported browser and HTTPS. An SSH tunnel on the laptop does not make the app accessible to other phones.

- Choose language, subject, learning level and explanation / practice / answer-checking mode.
- Record up to 60 seconds or upload an audio file under 4 MB. FFmpeg (installed by `setup.sh`) decodes WAV, WebM/Opus and other supported phone formats.
- Type a question if recording is unavailable. The standard text form also works without JavaScript.
- Turn off spoken answers for lower data use. Text-only requests skip speech synthesis.
- Install through the browser where supported. The app shell and three English starter lessons are cached after the first visit; AI answers and quiz submissions require connectivity; offline mode supports reading cached lessons only. Personal answers and recordings are not cached by the service worker.
- Read `/lessons` and submit the three starter quizzes without JavaScript or GPU inference.
- On basic browsers, text questions redirect to a queued thinking page that checks every four seconds. Results expire after 15 minutes; server restarts clear them. Use one Uvicorn worker for this process-local pilot queue.
- Each turn is independent. For answer checking, include the original question and your attempt.

Feature-phone support is progressive: basic HTML forms first, optional audio and PWA features where supported. Actual target-device testing remains necessary. The interface labels and starter lessons currently use English; the tutor supports the four selected response languages. No curriculum certification, retrieval corpus, learner accounts or conversation memory is implemented.

Models load on the first inference request, so the interface can start without CUDA, model weights or the YarnGPT vendor files. `/health` reports web-server availability and `models_loaded`; it does not certify inference readiness. Full inference still needs the GPU setup below. A single inference lock protects GPU memory; concurrent requests receive a retry message.

## Relationship to the v2 technical design

`Feature_Phone_Learning_App_Technical_Design.docx` is the larger phased design being developed separately. This implementation is the first working slice in the existing FastAPI repository: phone interface, PWA shell, English starter lessons and quizzes, education tutor options, and a bounded basic-browser text-job queue. It does not yet implement the proposed Django migration, accounts/guardian consent flows, SMS, teacher dashboards, BKT/Leitner progress, reviewed multilingual content, RAG, distributed workers, prerecorded lesson audio or measured 2G performance targets. The existing model stack and laptop smoke-test client are retained.

## Voice requests through the demo tunnel

The enhanced browser submits voice and text questions with `queued=true`, receives HTTP 202 with a job ID, and polls `GET /jobs/{id}?format=json`. GPU work runs separately from the HTTP connection, so initial model downloads and speech generation do not hold a tunnel request open. The answer includes a visible audio player and a prompt to press Play. Legacy clients and notebook smoke tests retain synchronous requests by omitting `queued`.

For an already-running older Kaggle session, copy all of `demos/repair_voice_demo.py` into a new code cell and run it. It updates the API, browser assets and tutor prompt, restarts the notebook-owned server and checks cached model loading. It also tests ASR against the earlier generated WAV if present; this is a diagnostic, not real-user validation. The GPU runtime, token and existing tunnel remain in place. Hard-refresh the web page afterward. A fresh notebook generated by `tools/build_gpu_notebook.py` includes the fix.

## API

- `POST /learn`: form fields `question` (1–1,000 characters), `lang`, `subject`, `level`, `mode`, `with_audio` (default false), `format` (`json` or `html`).
- `POST /talk`: multipart `audio`, optional `lang` (omitted means automatic detection), and the same learning options; `with_audio` defaults true for the existing laptop client.
- Subjects: `general`, `maths`, `english`, `science`, `social`. Levels: `primary`, `junior`, `everyday`. Modes: `explain`, `practice`, `check`.

Server content logging is off by default. With informed tester consent, set `SAVE_TURNS=1` to append transcripts, answers and timings to `server/logs/turns.jsonl`. Raw input recordings are not retained by this version. Avoid putting personal details in questions. This is a prototype without accounts or rate limiting; use controlled pilot access before a public rollout.

## Verification

API tests use a fake tutor (no model downloads) and real FFmpeg decoding when available:

```bash
pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
node --check server/web/app.js
node --check server/web/sw.js
node tests/test_web.js
```

These checks verify routes, basic-browser HTML escaping, text-only inference, validation, concurrency, prompt selection, queued basic-browser answers, lesson quizzes and browser-audio decoding. They do not establish language quality or real feature-phone compatibility.

```
laptop (client/talk.py)  ──HTTP over SSH tunnel──►  GPU box (server/)
  mic → wav                                          MMS-LID → NCAIR ASR → N-ATLaS → YarnGPT2
  speaker ◄── wav + transcript/reply/timings ◄──
```

## 1. Before you rent the GPU (one time)
1. Create a Hugging Face account and a **read token**: https://huggingface.co/settings/tokens
2. Open each model page while logged in and click **Agree / Request access** (approval is automatic):
   - https://huggingface.co/NCAIR1/Yoruba-ASR
   - https://huggingface.co/NCAIR1/Hausa-ASR
   - https://huggingface.co/NCAIR1/Igbo-ASR
   - https://huggingface.co/NCAIR1/NigerianAccentedEnglish
   - https://huggingface.co/NCAIR1/N-ATLaS

## 2. Rent the GPU
- Any NVIDIA GPU with **24 GB+** VRAM (RTX 4090, A5000, L4, A10, …). With < 40 GB the LLM loads in 4-bit automatically; with ≥ 40 GB (A6000, A100) it runs full fp16.
- Use a **PyTorch** template (RunPod "PyTorch 2.x", or a Vast.ai PyTorch image).
- Give it **~60 GB disk** for model weights.
- Make sure you can SSH in.

## 3. Set up the server (on the GPU box)
```bash
# copy the server folder up, from your laptop:
scp -P <port> -r server root@<gpu-host>:~/

# then on the GPU box:
cd ~/server
export HF_TOKEN=hf_xxx
./setup.sh                          # installs deps, downloads ~25 GB of models (5–15 min)

# quick offline test with any wav file:
python pipeline.py some_audio.wav

# start the server:
uvicorn app:app --host 127.0.0.1 --port 8000
```
The first inference request loads all models into the GPU and may take several minutes.

## 4. Talk to it (on your laptop)
In one terminal, open a tunnel to the server (keeps the server private — nothing is exposed to the internet):
```bash
ssh -p <port> -N -L 8000:localhost:8000 root@<gpu-host>
```
In another:
```bash
cd client
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python talk.py                 # Enter to start, Enter to stop
python talk.py --lang hausa    # skip language detection
```
macOS will ask for microphone permission for your terminal the first time.

## 5. Validate with learners
Use [education_test_questions.md](education_test_questions.md) for educational tasks. Have native speakers and teachers assess usable transcripts, answer correctness, speech clarity and learning usefulness. Record actual target phone/browser combinations and connection failures. `test_questions.md` contains older general-assistant prompts and is retained for reference.

## Knobs (env vars on the server)
| Var | Default | What |
|---|---|---|
| `LLM_4BIT` | `auto` | `1` / `0` to force 4-bit or fp16 |
| `LLM_MAX_TOKENS` | `80` | Cap reply length |
| `VOICE_ENGLISH` / `VOICE_YORUBA` / `VOICE_HAUSA` / `VOICE_IGBO` | idera / yoruba_male2 / hausa_female1 / igbo_female2 | YarnGPT voices |

YarnGPT voices — English: idera, chinenye, jude, emma, umar, joke, zainab, osagie, remi, tayo · Yoruba: yoruba_male2, yoruba_female2, yoruba_female1 · Igbo: igbo_female2, igbo_male2, igbo_female1 · Hausa: hausa_female1, hausa_female2, hausa_male2, hausa_male1

## Stop paying
Stop or terminate the GPU instance when you're done — rented GPUs bill by the hour even when idle.
