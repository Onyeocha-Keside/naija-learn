# Free GPU demo setup

The notebook is prepared, but no GPU session has been allocated or tested from this workspace. You must sign into Kaggle, enable an available GPU and run the cells. This uses the actual NCAIR/N-ATLaS/YarnGPT models; there are no prerecorded AI replies or placeholder answers.

1. Open https://www.kaggle.com/code and import `Naija_Learn_Free_GPU.ipynb` using the notebook import/upload option.
2. In notebook settings, enable Internet and GPU T4 x2 if available. Complete any account verification requested by Kaggle. Quotas and availability are account-dependent.
3. Accept the Hugging Face model conditions listed in the notebook. Add your read token as the Kaggle secret `HF_TOKEN`, enabling notebook access to it. The hidden input prompt is an alternative.
4. Run cells in order. The notebook contains this repository's current server and web files, so you do not need to publish code or upload a dataset first.
5. Let the real text-and-speech warmup finish. Play the generated audio in the notebook to confirm speech output before recording.
6. Run the HTTPS cell and open the printed URL, then record a short learning question. Anyone with this temporary URL can access it; keep it private and stop the tunnel when finished. Check the transcript, answer and spoken audio. First use of each language downloads its recogniser.
7. Rehearse, then record your 3–5 minute video. End the server/tunnel with the final cell and stop the GPU session when finished.

A single T4 is supported as a configuration target using 4-bit LLM weights and one cached ASR model, but fit and latency still need a real GPU test. On dual T4, N-ATLaS uses GPU 0 and ASR/TTS use GPU 1. Each GPU's memory remains separate. The notebook checks for CUDA and fails clearly when no GPU is assigned.

The temporary HTTPS link is for testing. Notebook quota, network restrictions, gate approvals, upstream checkpoint download limits and session resets can prevent a demo. Logs and direct audio-upload test cells help diagnose those cases. This is not production hosting.

Regenerate the notebook after changing server code:

```bash
python3 tools/build_gpu_notebook.py
```

The generator only embeds an explicit set of server source files and web assets. It excludes `.env`, logs, recordings, repository metadata, tokens, vendor code and model weights. Notebook outputs are initially empty. Clear outputs containing private information before sharing a notebook.

Free Colab is an alternative for notebook-based model experiments, but its restrictions on bypassing the notebook UI make it unsuitable for this external-web-app demo workflow.

Sources: [Kaggle notebooks](https://www.kaggle.com/docs/notebooks), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/), [Colab FAQ](https://research.google.com/colaboratory/faq.html), [N-ATLaS](https://huggingface.co/NCAIR1/N-ATLaS), [YarnGPT2](https://huggingface.co/saheedniyi/YarnGPT2).
