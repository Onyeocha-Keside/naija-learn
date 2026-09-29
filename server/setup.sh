#!/usr/bin/env bash
# One-time setup on the rented GPU box (Ubuntu + CUDA + PyTorch image, e.g. RunPod "PyTorch 2.x").
set -euo pipefail
cd "$(dirname "$0")"

apt-get update -qq && apt-get install -y -qq git ffmpeg libsndfile1 libportaudio2 build-essential >/dev/null || \
  echo "apt-get failed (not root?) - make sure git, ffmpeg and libsndfile are installed"

pip install -q -r requirements.txt

mkdir -p vendor
[ -d vendor/yarngpt ] || git clone -q https://github.com/saheedniyi02/yarngpt.git vendor/yarngpt

cd vendor
[ -f wavtokenizer_mediumdata_frame75_3s_nq1_code4096_dim512_kmeans200_attn.yaml ] || \
  wget -q https://huggingface.co/novateur/WavTokenizer-medium-speech-75token/resolve/main/wavtokenizer_mediumdata_frame75_3s_nq1_code4096_dim512_kmeans200_attn.yaml
[ -f wavtokenizer_large_speech_320_24k.ckpt ] || gdown -q 1-ASeEkrn4HY49yZWHTASgfGFNXdVnLTt
cd ..

# NCAIR models are gated: accept the terms on each model page first, then log in.
if [ -z "${HF_TOKEN:-}" ]; then
  echo "Set HF_TOKEN (huggingface.co/settings/tokens) and re-run, or run: huggingface-cli login"
  exit 1
fi

# Pre-download all weights so the first request isn't slow.
python - <<'PY'
from huggingface_hub import snapshot_download
for repo in ["NCAIR1/Yoruba-ASR", "NCAIR1/Hausa-ASR", "NCAIR1/Igbo-ASR",
             "NCAIR1/NigerianAccentedEnglish", "NCAIR1/N-ATLaS",
             "facebook/mms-lid-126", "saheedniyi/YarnGPT2"]:
    print("downloading", repo)
    skip = ["optimizer.pt", "rng_state_*", "scheduler.pt", "training_args.bin", "*.msgpack", "*.h5"]
    if repo == "facebook/mms-lid-126":
        skip.append("pytorch_model.bin")  # same weights as model.safetensors
    snapshot_download(repo, ignore_patterns=skip)
PY
echo "Setup done. Start the server with:  uvicorn app:app --host 127.0.0.1 --port 8000"
