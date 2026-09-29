# Nigerian Voice Assistant — Phase 1 prototype

Speak Yoruba, Hausa, Igbo, or Nigerian English into your laptop; hear a reply in the same language.
See [PRD.md](PRD.md) for the plan.

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
First start takes ~1–2 min to load all models into the GPU.

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

## 5. Build the test set
Every turn is saved on the server in `server/logs/`: the input audio, the reply audio, and a row in `turns.jsonl` with the detected language, transcript, reply and per-stage timings. Aim for 20–30 turns per language, then have a native speaker score them (see PRD §7).

Pull the logs down with:
```bash
scp -P <port> -r root@<gpu-host>:~/server/logs ./logs
```

## Knobs (env vars on the server)
| Var | Default | What |
|---|---|---|
| `LLM_4BIT` | `auto` | `1` / `0` to force 4-bit or fp16 |
| `LLM_MAX_TOKENS` | `150` | Cap reply length |
| `VOICE_ENGLISH` / `VOICE_YORUBA` / `VOICE_HAUSA` / `VOICE_IGBO` | idera / yoruba_male2 / hausa_female1 / igbo_female2 | YarnGPT voices |

YarnGPT voices — English: idera, chinenye, jude, emma, umar, joke, zainab, osagie, remi, tayo · Yoruba: yoruba_male2, yoruba_female2, yoruba_female1 · Igbo: igbo_female2, igbo_male2, igbo_female1 · Hausa: hausa_female1, hausa_female2, hausa_male2, hausa_male1

## Stop paying
Stop or terminate the GPU instance when you're done — rented GPUs bill by the hour even when idle.
