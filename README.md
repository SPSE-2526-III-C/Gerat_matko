# Local AI model runner (no admin)

This folder gives you a **free, offline, text‑only** model that you can download and run locally on Windows without admin rights.

It uses:
- **Mistral 7B Instruct (GGUF)** – larger, higher‑quality model
- **gpt4all** – local inference runtime with prebuilt Windows wheels

## ✅ Requirements
- **Python 3.9–3.12 (64‑bit)** (user install is OK)
- Enough RAM (4GB+ recommended)

## Setup

Install dependencies:

```powershell
py -3.11 -m pip install -r requirements.txt
```

## Run

```powershell
py -3.11 run_local_model.py
```

You will get a simple **input → output** loop in the terminal.

## Web UI (Flask)

Spustí lokálne HTML okno s progres barom.

```powershell
py -3.11 web_app.py
```

Potom otvor v prehliadači: `http://127.0.0.1:5000`

## Notes
- The model file (~4.1GB) downloads automatically into `models/` on first run.
- During generation, a progress bar shows token count and ETA in the console.
- If download is slow, try a wired connection or run it later.
- Vulgarity filter blocks messages with offensive words and returns a short safe reply.

## Troubleshooting
- If you see an import error for `gpt4all`, run the install command again.
- If installation fails, make sure you are using a **64‑bit** Python.
