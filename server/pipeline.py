"""Voice pipeline: audio in -> language ID -> ASR -> LLM -> TTS -> audio out.

Run directly to test on a file:
    python pipeline.py sample.wav [--lang yoruba]
"""
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import torch
from transformers import (
    AutoFeatureExtractor,
    AutoModelForAudioClassification,
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    WhisperForConditionalGeneration,
    WhisperProcessor,
)

from learning import LANGS, tutor_prompt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))  # setup.sh clones yarngpt here
from yarngpt.audiotokenizer import AudioTokenizerV2  # noqa: E402

DEVICE = "cuda"
DTYPE = torch.float16
ASR_SR = 16_000
TTS_SR = 24_000

# MMS-LID ISO codes for the 4 languages we support.
LID_CODES = {"eng": "english", "yor": "yoruba", "hau": "hausa", "ibo": "igbo"}

ASR_MODELS = {
    "english": "NCAIR1/NigerianAccentedEnglish",
    "yoruba": "NCAIR1/Yoruba-ASR",
    "hausa": "NCAIR1/Hausa-ASR",
    "igbo": "NCAIR1/Igbo-ASR",
}

# One fixed voice per language so the assistant sounds consistent.
TTS_VOICES = {
    "english": os.getenv("VOICE_ENGLISH", "idera"),
    "yoruba": os.getenv("VOICE_YORUBA", "yoruba_male2"),
    "hausa": os.getenv("VOICE_HAUSA", "hausa_female1"),
    "igbo": os.getenv("VOICE_IGBO", "igbo_female2"),
}

LLM_MODEL = "NCAIR1/N-ATLaS"
LID_MODEL = "facebook/mms-lid-126"
TTS_MODEL = "saheedniyi/YarnGPT2"
WAVTOKENIZER_CONFIG = os.path.join(HERE, "vendor", "wavtokenizer_mediumdata_frame75_3s_nq1_code4096_dim512_kmeans200_attn.yaml")
WAVTOKENIZER_CKPT = os.path.join(HERE, "vendor", "wavtokenizer_large_speech_320_24k.ckpt")


@dataclass
class Result:
    language: str
    lid_scores: dict
    transcript: str
    reply: str
    audio: np.ndarray  # float32 mono at TTS_SR
    timings: dict = field(default_factory=dict)


class Pipeline:
    def __init__(self):
        t0 = time.time()
        self._load_lid()
        self._load_asr()
        self._load_llm()
        self._load_tts()
        print(f"[pipeline] all models loaded in {time.time() - t0:.0f}s")

    # ---------- loading ----------

    def _load_lid(self):
        self.lid_fe = AutoFeatureExtractor.from_pretrained(LID_MODEL)
        self.lid = AutoModelForAudioClassification.from_pretrained(LID_MODEL, torch_dtype=DTYPE).to(DEVICE).eval()
        label2id = self.lid.config.label2id
        # Only compare the 4 languages we support; ignore the other 122.
        self.lid_ids = {lang: label2id[code] for code, lang in LID_CODES.items()}

    def _load_asr(self):
        self.asr = {}
        for lang, name in ASR_MODELS.items():
            proc = WhisperProcessor.from_pretrained(name)
            model = WhisperForConditionalGeneration.from_pretrained(name, torch_dtype=DTYPE).to(DEVICE).eval()
            self.asr[lang] = (proc, model)

    def _load_llm(self):
        self.llm_tok = AutoTokenizer.from_pretrained(LLM_MODEL)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        # 8B in fp16 is ~16 GB; on a 24 GB card that leaves too little room for the rest.
        use_4bit = os.getenv("LLM_4BIT", "auto")
        use_4bit = vram_gb < 40 if use_4bit == "auto" else use_4bit == "1"
        kwargs = {"device_map": DEVICE}
        if use_4bit:
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=DTYPE, bnb_4bit_quant_type="nf4"
            )
        else:
            kwargs["torch_dtype"] = DTYPE
        self.llm = AutoModelForCausalLM.from_pretrained(LLM_MODEL, **kwargs).eval()
        print(f"[pipeline] LLM loaded ({'4-bit' if use_4bit else 'fp16'}, GPU has {vram_gb:.0f} GB)")

    def _load_tts(self):
        self.tts_tok = AudioTokenizerV2(TTS_MODEL, WAVTOKENIZER_CKPT, WAVTOKENIZER_CONFIG)
        self.tts = AutoModelForCausalLM.from_pretrained(TTS_MODEL, torch_dtype="auto").to(DEVICE).eval()

    # ---------- stages ----------

    @torch.inference_mode()
    def detect_language(self, audio: np.ndarray) -> tuple[str, dict]:
        inputs = self.lid_fe(audio, sampling_rate=ASR_SR, return_tensors="pt").to(DEVICE)
        logits = self.lid(input_values=inputs.input_values.to(DTYPE)).logits[0]
        sub = torch.stack([logits[i] for i in self.lid_ids.values()]).float().softmax(-1)
        scores = {lang: round(p.item(), 3) for lang, p in zip(self.lid_ids, sub)}
        return max(scores, key=scores.get), scores

    @torch.inference_mode()
    def transcribe(self, audio: np.ndarray, lang: str) -> str:
        proc, model = self.asr[lang]
        feats = proc(audio, sampling_rate=ASR_SR, return_tensors="pt").input_features.to(DEVICE, DTYPE)
        ids = model.generate(feats, max_new_tokens=200)
        return proc.batch_decode(ids, skip_special_tokens=True)[0].strip()

    @torch.inference_mode()
    def respond(self, transcript: str, lang: str, subject="general", level="primary", mode="explain") -> str:
        messages = [
            {"role": "system", "content": tutor_prompt(lang.capitalize(), subject, level, mode)},
            {"role": "user", "content": transcript},
        ]
        text = self.llm_tok.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False, date_string=datetime.now().strftime("%d %b %Y")
        )
        inputs = self.llm_tok(text, return_tensors="pt", add_special_tokens=False).to(DEVICE)
        out = self.llm.generate(
            **inputs,
            max_new_tokens=int(os.getenv("LLM_MAX_TOKENS", "150")),
            do_sample=True,
            temperature=0.1,
            repetition_penalty=1.12,
            pad_token_id=self.llm_tok.eos_token_id,
        )
        return self.llm_tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()

    @torch.inference_mode()
    def speak(self, text: str, lang: str) -> np.ndarray:
        # YarnGPT degrades on long inputs, so synthesise sentence by sentence.
        chunks = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()] or [text]
        pause = np.zeros(int(0.25 * TTS_SR), dtype=np.float32)
        pieces = []
        for chunk in chunks:
            prompt = self.tts_tok.create_prompt(chunk, lang=lang, speaker_name=TTS_VOICES[lang])
            input_ids = self.tts_tok.tokenize_prompt(prompt)
            out = self.tts.generate(
                input_ids=input_ids,
                temperature=0.1,
                repetition_penalty=1.1,
                max_length=4000,
            )
            codes = self.tts_tok.get_codes(out)
            if not codes:
                continue
            pieces += [self.tts_tok.get_audio(codes).squeeze().numpy().astype(np.float32), pause]
        return np.concatenate(pieces) if pieces else pause

    # ---------- full turn ----------

    def run(self, audio: np.ndarray, force_lang: str | None = None, subject="general", level="primary", mode="explain", with_audio=True) -> Result:
        timings = {}

        def timed(name, fn, *args):
            t = time.time()
            out = fn(*args)
            torch.cuda.synchronize()
            timings[name] = round(time.time() - t, 2)
            return out

        if force_lang:
            lang, scores = force_lang, {}
        else:
            lang, scores = timed("lid", self.detect_language, audio)
        transcript = timed("asr", self.transcribe, audio, lang)
        if not transcript:
            raise ValueError("No speech was recognised. Try again or type your question.")
        reply = timed("llm", self.respond, transcript, lang, subject, level, mode)
        out_audio = timed("tts", self.speak, reply, lang) if with_audio else np.zeros(0, dtype=np.float32)
        timings["total"] = round(sum(timings.values()), 2)
        return Result(lang, scores, transcript, reply, out_audio, timings)


if __name__ == "__main__":
    import argparse

    import librosa
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--lang", choices=LANGS)
    ap.add_argument("--out", default="reply.wav")
    args = ap.parse_args()

    audio, _ = librosa.load(args.wav, sr=ASR_SR, mono=True)
    p = Pipeline()
    r = p.run(audio, args.lang)
    sf.write(args.out, r.audio, TTS_SR)
    print(f"language:   {r.language} {r.lid_scores}")
    print(f"transcript: {r.transcript}")
    print(f"reply:      {r.reply}")
    print(f"timings:    {r.timings}")
    print(f"saved:      {args.out}")
