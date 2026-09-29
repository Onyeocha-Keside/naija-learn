# PRD — Nigerian Voice Assistant (working name)

## 1. What we're building
An Alexa-style smart speaker that understands and replies in **Yoruba, Hausa, Igbo, and Nigerian-accented English**. The user speaks in any of the four; the device answers out loud **in the same language**.

## 2. Why
Mainstream voice assistants handle Nigerian languages poorly or not at all, and struggle with Nigerian accents. Open models from NCAIR (ASR, N-ATLaS) and YarnGPT (TTS) now make a local-first alternative possible.

## 3. Users
- Primary: Nigerian households, including people more comfortable in their native language than English.
- Early: us, plus a small group of native-speaker testers (at least one per language).

## 4. Core user flow
1. User says the wake word.
2. Device listens until the user stops talking.
3. System detects the language → transcribes → generates a reply in the same language → speaks it.
4. Device returns to idle.

## 5. System pipeline
```
ESP32-S3 (wake word, mic, speaker)
   ⇅ WebSocket audio stream
Server:
   VAD / endpointing
   → Language ID (yo / ha / ig / en)
   → NCAIR ASR (Yoruba-ASR | Hausa-ASR | Igbo-ASR | NigerianAccentedEnglish)
   → LLM: N-ATLaS 8B (reply in detected language)
   → TTS: YarnGPT2 (same language)
   → stream audio back
```
Prototype uses plain HTTP (one request per turn) over an SSH tunnel; Phase 2 moves to a WebSocket stream for the ESP32.

**Note on tone marks:** YarnGPT romanizes its input to plain a–z before speaking, so Yoruba/Igbo tone marks are ignored by the TTS. Tones in the spoken reply come from what YarnGPT learned, not from the text. Tone marks still matter for readable transcripts and LLM understanding.

## 6. Scope

### In (v1)
- 4 languages in, same language out
- Single-turn Q&A and simple conversation
- Wake word + push-to-talk fallback
- Sentence-by-sentence streaming of LLM output → TTS

### Out (for now)
- Barge-in / echo cancellation
- Smart-home control, timers, music, integrations
- Multi-turn memory across sessions
- Handling code-switching perfectly (we measure it, don't solve it yet)
- Offline / on-device inference

## 7. Success metrics
| Metric | Prototype target | Real-use target |
|---|---|---|
| Language ID accuracy | ≥ 90% | ≥ 95% |
| Transcript usable (native speaker judgement) | ≥ 80% | ≥ 90% |
| Reply correct language + natural (native speaker, 1–5) | avg ≥ 3.5 | avg ≥ 4 |
| End of speech → first audio | < 5 s | < 2.5 s |
| Cost per interaction | ~free | < ₦5 |

## 8. Phases

### Phase 1 — Prototype (laptop, no hardware)
**Goal:** prove the language chain works end-to-end, especially LLM → YarnGPT quality in native languages.
- Python script: laptop mic → LID → ASR → N-ATLaS → YarnGPT → laptop speaker
- Compute: **rented 24 GB+ GPU** (decided); laptop client talks to it over an SSH tunnel
- TTS: YarnGPT2 open weights, self-hosted on the same GPU (Apache-2.0)
- LLM: N-ATLaS (4-bit on < 40 GB GPUs); compare against a general API LLM on the same transcripts
- Code: `server/` (pipeline + HTTP API), `client/talk.py` (push-to-talk); every turn logged for scoring
- Deliverable: working demo + a scored test set (≈20–30 utterances per language)
- **Exit criteria:** hits prototype targets above; native speakers say replies are understandable

### Phase 2 — Real use (hardware + hosted server)
**Goal:** a physical device a tester can use at home daily.
- Server: all models self-hosted on **one rented 24 GB GPU** (RunPod / Vast.ai class), behind a WebSocket API
- YarnGPT: switch to **self-hosted open weights** (don't depend on hosted API; check license)
- Hardware: ESP32-S3 (S3-BOX-3 to start, or ESP32-S3 + INMP441 mic + MAX98357A amp + speaker)
- Wake word on-device (ESP-SR / microWakeWord), stock word first, custom later
- Latency work: fast endpointing, warm models, streaming TTS
- Deliverable: 3–5 devices with testers for 2 weeks
- **Exit criteria:** hits real-use targets; testers use it unprompted

## 9. Key risks
| Risk | Mitigation |
|---|---|
| LLM writes weak Yoruba/Hausa/Igbo | Test early in Phase 1; compare N-ATLaS vs API LLM. N-ATLaS's own card notes Yoruba is its weakest language |
| NCAIR license (ASR + N-ATLaS): research license, **1,000 active end-user cap**, commercial use needs a separate license from Awarri; attribution required | Fine for prototype + pilot; talk to Awarri before scaling past pilot |
| Wrong language detected → wrong ASR | Fallback: run all 4 ASR in parallel, pick highest confidence |
| Code-switching breaks ASR | Measure in test set; decide approach after Phase 1 |
| Latency too high | Streaming TTS, short replies, warm GPU |
| YarnGPT API terms change (acquired by Bluechip, Jun 2026) | Self-host open weights in Phase 2 |
| Model licenses restrict commercial use | Check each model card before Phase 2 |

## 10. Open questions
- Product name and wake word?
- Should the reply ever switch to English (e.g., user asks for it)?
