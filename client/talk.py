"""Push-to-talk client for the laptop.

    python talk.py                      # auto-detect language
    python talk.py --lang yoruba        # skip language ID
    python talk.py --file question.wav  # send a file instead of the mic

Press Enter to start recording, Enter again to stop. Ctrl+C to quit.
"""
import argparse
import base64
import io
import queue
import time

import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

SR = 16_000


def record() -> bytes:
    q = queue.Queue()
    input("\n[Enter] to talk...")
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=lambda d, *_: q.put(d.copy())):
        input("Recording... [Enter] to stop")
    audio = np.concatenate(list(q.queue)) if not q.empty() else np.zeros((0, 1), np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV")
    return buf.getvalue()


def send(server: str, wav: bytes, lang: str | None):
    t = time.time()
    resp = requests.post(
        f"{server}/talk",
        files={"audio": ("in.wav", wav, "audio/wav")},
        data={"lang": lang} if lang else {},
        timeout=300,
    )
    rtt = time.time() - t
    if resp.status_code != 200:
        print(f"error {resp.status_code}: {resp.text}")
        return
    r = resp.json()
    print(f"  language:   {r['language']} {r['lid_scores'] or '(forced)'}")
    print(f"  you said:   {r['transcript']}")
    print(f"  reply:      {r['reply']}")
    print(f"  timings:    {r['timings']}  | round trip {rtt:.1f}s")
    audio, sr = sf.read(io.BytesIO(base64.b64decode(r["audio_b64"])), dtype="float32")
    sd.play(audio, sr)
    sd.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--lang", choices=["english", "yoruba", "hausa", "igbo"])
    ap.add_argument("--file")
    args = ap.parse_args()

    requests.get(f"{args.server}/health", timeout=10).raise_for_status()
    print(f"Connected to {args.server}")

    if args.file:
        with open(args.file, "rb") as f:
            send(args.server, f.read(), args.lang)
        return
    try:
        while True:
            send(args.server, record(), args.lang)
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
