from __future__ import annotations

import io
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from gpt4all import GPT4All

from translate import translate_en_to_sk, translate_sk_to_en
from safety import filter_model_reply, filter_user_message
from text_speach import synthesize_mp3_bytes
from db import (
    init_db, create_session, save_message, save_metadata, end_session, 
    get_user_sessions, get_session_history, get_user_history, verify_session, login_user, 
    register_user, create_session_for_user, get_audit_log
)
MODEL_URL = (
    "https://huggingface.co/TheBloke/dolphin-2.6-mistral-7B-GGUF/resolve/main/"
    "dolphin-2.6-mistral-7b.Q4_K_M.gguf"
)
MODEL_FILENAME = "dolphin-2.6-mistral-7b.Q4_K_M.gguf"
SYSTEM_PROMPT = "You are teacher who helps students with their questions. You answer in a clear and concise manner, providing examples when helpful. Always be polite and encouraging."

app = Flask(__name__)
_model: GPT4All | None = None
_model_lock = threading.Lock()

# Session storage: token -> session info
_sessions: dict[str, dict] = {}

# Initialize database on startup
init_db()

whole_history = [["Toto je cela historia chatu aby si vedel, toto si nevsimaj. odpovedaj iba na otazku ktoru ti pouzivatel polozil ako poslednu, v zozname mas to prve co sa clovek pyta a druhe je to co si odpoverd"]]
last_history_bot =[]
last_history_user = [] 
temporary_history = []


def get_model_path() -> Path:
    base_dir = Path(__file__).resolve().parent
    return base_dir / "models" / MODEL_FILENAME


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


def clean_model_output(text: str) -> str:
    tokens = (
        "<|assistant|>",
        "<|user|>",
        "<|system|>",
        "<|používateľ|>",
        "<|asistent|>",
    )
    cleaned = text
    for token in tokens:
        cleaned = cleaned.replace(token, "")
    return cleaned.strip()


def get_model() -> GPT4All:
    global _model
    if _model is not None:
        return _model
    model_path = get_model_path()
    download_model(model_path)
    print("Loading model... (first time can take a while)")
    _model = GPT4All(
        MODEL_FILENAME,
        model_path=str(model_path.parent),
        allow_download=False,
    )
    return _model


def generate_reply(session_token: str, user_text: str) -> dict[str, Any]:
    global temporary_history, whole_history
    
    # Verify session
    session = verify_session(session_token)
    if not session:
        return {
            "reply": "Neplatná relácia. Prosím prihláste sa.",
            "elapsed": 0.0,
            "max_tokens": 0,
            "blocked": True,
        }
    
    session_id = session["session_id"]
    allowed, filtered_message = filter_user_message(user_text)
    
    if not allowed:
        result = {
            "reply": filtered_message,
            "elapsed": 0.0,
            "max_tokens": 0,
            "blocked": True,
        }
        # Save blocked message to database
        try:
            save_message(
                session_id,
                user_text,
                filtered_message,
                filtered_user_message=filtered_message,
                is_blocked=True,
                elapsed_time=0.0,
                max_tokens=0,
            )
        except Exception as e:
            print(f"Error saving blocked message: {e}")
        return result

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
    cleaned = clean_model_output(str(text))
    
    reply = translate_en_to_sk(cleaned)
    reply = filter_model_reply(reply)

    # Save message to database
    try:
        save_message(
            session_id,
            user_text,
            reply,
            filtered_user_message=filtered_message,
            is_blocked=False,
            elapsed_time=elapsed,
            max_tokens=max_tokens,
        )
    except Exception as e:
        print(f"Error saving message: {e}")

   
    return {
        "reply": reply,
        "elapsed": elapsed,
        "max_tokens": max_tokens,
        "blocked": False,

    }
   


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/register", methods=["POST"])
def api_register() -> Any:
    """Register a new user."""
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    try:
        result = register_user(username, password)
        if result["success"]:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/login", methods=["POST"])
def api_login() -> Any:
    """Authenticate user and create session."""
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    try:
        result = login_user(username, password)
        if result["success"]:
            # Store session info
            _sessions[result["session_token"]] = {
                "user_id": result["user_id"],
                "username": result["username"],
                "session_id": result["session_id"],
            }
            return jsonify(result), 200
        else:
            return jsonify(result), 401
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/logout", methods=["POST"])
def api_logout() -> Any:
    """Logout user and end session."""
    payload = request.get_json(silent=True) or {}
    session_token = str(payload.get("session_token", "")).strip()
    
    if not session_token:
        return jsonify({"error": "Session token required"}), 400
    
    try:
        session = verify_session(session_token)
        if session:
            end_session(session["session_id"])
            if session_token in _sessions:
                del _sessions[session_token]
            return jsonify({"success": True, "message": "Logged out"}), 200
        else:
            return jsonify({"error": "Invalid session"}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
   


@app.route("/api/tts", methods=["POST"])
def api_tts() -> Any:
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"error": "Missing text."}), 400
    try:
        audio_bytes = synthesize_mp3_bytes(text)
    except Exception as exc:  # pragma: no cover - surface errors to UI
        return jsonify({"error": str(exc)}), 500
    if not audio_bytes:
        return jsonify({"error": "No audio generated."}), 500

    return send_file(
        io.BytesIO(audio_bytes),
        mimetype="audio/mpeg",
        as_attachment=False,
        download_name="tts.mp3",
    )


@app.route("/api/generate", methods=["POST"])
def api_generate() -> Any:
    payload = request.get_json(silent=True) or {}
    session_token = str(payload.get("session_token", "")).strip()
    message = str(payload.get("message", "")).strip()
    
    if not session_token:
        return jsonify({"error": "Session token required."}), 400
    if not message:
        return jsonify({"error": "Missing message."}), 400
    
    try:
        result = generate_reply(session_token, message)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["GET"])
def api_history() -> Any:
    """Retrieve chat history for the current user across all sessions."""
    session_token = request.args.get("session_token", "").strip()
    
    if not session_token:
        return jsonify({"error": "Session token required."}), 400
    
    try:
        session = verify_session(session_token)
        if not session:
            return jsonify({"error": "Invalid session."}), 400
        
        history = get_user_history(session["user_id"])
        return jsonify({
            "session_id": session["session_id"],
            "username": session["username"],
            "messages": history
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/sessions", methods=["GET"])
def api_sessions() -> Any:
    """Retrieve all chat sessions for the current user."""
    session_token = request.args.get("session_token", "").strip()
    
    if not session_token:
        return jsonify({"error": "Session token required."}), 400
    
    try:
        session = verify_session(session_token)
        if not session:
            return jsonify({"error": "Invalid session."}), 400
        
        sessions = get_user_sessions(session["user_id"])
        return jsonify({"sessions": sessions})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/audit", methods=["GET"])
def api_audit() -> Any:
    """Retrieve audit log for the current user."""
    session_token = request.args.get("session_token", "").strip()
    
    if not session_token:
        return jsonify({"error": "Session token required."}), 400
    
    try:
        session = verify_session(session_token)
        if not session:
            return jsonify({"error": "Invalid session."}), 400
        
        audit_log = get_audit_log(session["user_id"], limit=50)
        return jsonify({"audit_log": audit_log})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    # Database is already initialized at module level
    download_model(get_model_path())
    app.run(host="127.0.0.1", port=5000, debug=False)




