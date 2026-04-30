from __future__ import annotations

import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from gpt4all import GPT4All

from translate import translate_en_to_sk, translate_sk_to_en
from safety import filter_model_reply, filter_user_message

MODEL_URL = (
    "https://huggingface.co/bartowski/ChatHercules-2.5-Mistral-7B-GGUF/resolve/main/"
    "ChatHercules-2.5-Mistral-7B.Q4_K_M.gguf"
)
MODEL_FILENAME = "ChatHercules-2.5-Mistral-7B.Q4_K_M.gguf"
SYSTEM_PROMPT = "You are a helpful assistant."

app = Flask(__name__)
_model: GPT4All | None = None
_model_lock = threading.Lock()


def download_model(model_path: Path) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if model_path.exists():
        return
    print(f"Downloading model to {model_path} ...")
    with urllib.request.urlopen(MODEL_URL) as response, open(model_path, "wb") as out_file:
        total = response.length or 0
        downloaded = 0
        chunk_size = 1024 * 1024
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            if total:
                percent = downloaded * 100 // total
                print(f"  {percent}%", end="\r", flush=True)
    print("Download complete.")


def build_prompt(user_text: str) -> str:
    return (
        f"<|system|>\n{SYSTEM_PROMPT}\n"
        f"<|user|>\n{user_text}\n"
        "<|assistant|>\n"
    )


def get_model() -> GPT4All:
    global _model
    if _model is not None:
        return _model
    base_dir = Path(__file__).resolve().parent
    model_path = base_dir / "models" / MODEL_FILENAME
    download_model(model_path)
    print("Loading model... (first time can take a while)")
    _model = GPT4All(
        MODEL_FILENAME,
        model_path=str(model_path.parent),
        allow_download=False,
    )
    return _model


def generate_reply(user_text: str) -> dict[str, Any]:
    allowed, filtered_message = filter_user_message(user_text)
    if not allowed:
        return {
            "reply": filtered_message,
            "elapsed": 0.0,
            "max_tokens": 0,
            "blocked": True,
        }

    prompt = build_prompt(translate_sk_to_en(filtered_message))
    max_tokens = max(256, len(user_text) // 3)

    start = time.perf_counter()
    with _model_lock:
        model = get_model()
        text = model.generate(
            prompt,
            max_tokens=max_tokens,
            temp=0.7,
        )
    elapsed = time.perf_counter() - start
    reply = translate_en_to_sk(str(text).strip())
    reply = filter_model_reply(reply)
    return {
        "reply": reply,
        "elapsed": elapsed,
        "max_tokens": max_tokens,
        "blocked": False,
    }
