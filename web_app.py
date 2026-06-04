from __future__ import annotations

import io
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import psutil
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
)
from llama_cpp import Llama

# Importy z tvojich lokálnych modulov
from db import (
    init_db,
    save_message,
    end_session,
    get_user_sessions,
    get_user_history,
    verify_session,
    login_user,
    register_user,
    get_audit_log,
)
from safety import (
    filter_model_reply,
    filter_user_message,
)
from text_speach import synthesize_mp3_bytes

# =========================================================
# CONFIG
# =========================================================

MODEL_URL = (
    "https://huggingface.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive/resolve/main/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-IQ2_M.gguf"
)

MODEL_FILENAME = (
    "Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-IQ2_M.gguf"
)
SYSTEM_PROMPT = """
You are an AI teacher assistant for Slovak students.

Rules:
- ALWAYS answer in Slovak language.
- NEVER mix Czech language.
- Explain things clearly and naturally.
- Use short and educational responses.
- Use examples when useful.
- Be friendly and helpful.
- If user asks school question: explain step by step.
- Avoid repeating yourself.
- Never generate nonsense.
- Keep answers coherent and natural.
"""

# =========================================================
# FLASK & GLOBALS
# =========================================================

app = Flask(__name__)

_model: GPT4All | None = None
_model_lock = threading.Lock()
_sessions: dict[str, dict] = {}

MODEL_READY = False
MODEL_LOADING = False

# Inicializácia databázy pri štarte aplikácie
init_db()

# 🛠️ AUTOMATICKÝ PATCH PRE CHÝBAJÚCU TABUĽKU A ZÁMOK DATABÁZY
def _aplikuj_db_patch():
    import sqlite3
    import db
    
    # Skúsime zistiť názov súboru databázy priamo z modulu db
    db_name = "databaza.db"  # predvolený fallback
    for attr in ["DB_FILE", "DB_NAME", "DATABASE", "db_name", "db_file"]:
        if hasattr(db, attr):
            db_name = getattr(db, attr)
            break
            
    # Ak súbor neexistuje pod týmto názvom, skúsime nájsť akýkoľvek .db v priečinku
    if not Path(db_name).exists():
        najdene_db = list(Path(".").glob("*.db")) + list(Path(".").glob("*.sqlite"))
        if najdene_db:
            db_name = str(najdene_db[0])

    try:
        # timeout=30.0 bráni chybe "database is locked" pri viacerých vláknach
        conn = sqlite3.connect(db_name, timeout=30.0)
        cursor = conn.cursor()
        
        # Vytvorenie chýbajúcej tabuľky chat_sessions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_token TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print(f"ℹ️ [DB PATCH] Tabuľka chat_sessions bola úspešne overená/vytvorená v: {db_name}")
    except Exception as e:
        print(f"⚠️ [DB PATCH] Nepodarilo sa aplikovať záplatu: {e}")

_aplikuj_db_patch()

# =========================================================
# SYSTEM MONITORING
# =========================================================

def get_system_stats():
    try:
        process = psutil.Process(os.getpid())
        cpu_percent = psutil.cpu_percent(interval=None)
        ram_mb = process.memory_info().rss / 1024 / 1024
        return {
            "cpu": round(cpu_percent, 1),
            "ram": round(ram_mb, 1),
        }
    except Exception:
        return {"cpu": 0, "ram": 0}

# =========================================================
# MODEL PATH & DOWNLOAD
# =========================================================

def get_model_path() -> Path:
    base_dir = Path(__file__).resolve().parent
    return base_dir / "models" / MODEL_FILENAME


def download_model(model_path: Path):
    model_path.parent.mkdir(parents=True, exist_ok=True)

    if model_path.exists():
        return

    print("\n⬇️ Sťahujem AI model (môže to chvíľu trvať)... \n")
    try:
        with urllib.request.urlopen(MODEL_URL) as response:
            total = response.length or 0
            downloaded = 0
            chunk_size = 1024 * 1024

            with open(model_path, "wb") as out_file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)

                    if total:
                        percent = int(downloaded * 100 / total)
                        bar_len = 30
                        filled = int(bar_len * percent / 100)
                        bar = "█" * filled + "-" * (bar_len - filled)
                        print(f"\r[{bar}] {percent}%", end="", flush=True)
        print("\n✅ Model stiahnutý.\n")
    except Exception as e:
        print(f"\n❌ Chyba pri sťahovaní modelu: {e}\n")
        raise e

# =========================================================
# LOAD MODEL & ASYNC INIT
# =========================================================

def get_model() -> GPT4All:
    global _model, MODEL_READY
    if _model is not None:
        return _model

    model_path = get_model_path()
    download_model(model_path)

    print("🧠 Načítavam AI model do pamäte...\n")
    _model = GPT4All(
        MODEL_FILENAME,
        model_path=str(model_path.parent),
        allow_download=False,
    )
    MODEL_READY = True
    print("✅ Model úspešne pripravený.\n")
    return _model


def init_model_async():
    global MODEL_LOADING, MODEL_READY
    if MODEL_READY or MODEL_LOADING:
        return

    MODEL_LOADING = True

    def loader():
        global MODEL_READY, MODEL_LOADING
        try:
            get_model()
        except Exception as e:
            print(f"❌ Zlyhala asynchrónna inicializácia modelu: {e}")
        finally:
            model_loading = False

    threading.Thread(target=loader, daemon=True).start()

# =========================================================
# HELPERS FOR PROMPT & TOKENS
# =========================================================

def build_prompt(user_text: str):
    return f"<s>[INST]\n{SYSTEM_PROMPT}\n\nPoužívateľ:\n{user_text}\n[/INST]\n"


def clean_model_output(text: str):
    remove = ["</s>", "<s>", "[INST]", "[/INST]"]
    cleaned = text
    for token in remove:
        cleaned = cleaned.replace(token, "")
    return cleaned.strip()


def calculate_max_tokens(user_text: str):
    length = len(user_text)
    if length < 15:
        return 48
    if length < 80:
        return 96
    if length < 250:
        return 160
    return 256


def get_question_difficulty(prompt: str):
    chars = len(prompt)
    if chars < 150:
        return "ĽAHKÁ"
    if chars < 500:
        return "STREDNÁ"
    if chars < 1200:
        return "ŤAŽKÁ"
    return "EXTRÉMNA"

# =========================================================
# CORE GENERATE REPLY
# =========================================================

def generate_reply(session_token: str, user_text: str) -> dict[str, Any]:
    global MODEL_READY

    if not MODEL_READY:
        return {
            "reply": "AI model sa stále načítava na pozadí. Skúste to znova o chvíľu.",
            "elapsed": 0,
            "max_tokens": 0,
            "blocked": True,
        }

    session = verify_session(session_token)
    if not session:
        return {
            "reply": "Neplatná alebo vypršaná relácia (session).",
            "elapsed": 0,
            "max_tokens": 0,
            "blocked": True,
        }

    session_id = session["session_id"]

    # Bezpečnostný filter na vstupe
    allowed, filtered_message = filter_user_message(user_text)
    if not allowed:
        return {
            "reply": filtered_message,
            "elapsed": 0,
            "max_tokens": 0,
            "blocked": True,
        }

    prompt = build_prompt(filtered_message)
    max_tokens = calculate_max_tokens(filtered_message)
    difficulty = get_question_difficulty(prompt)

    print("\n" + "="*50)
    print("🧠 GENEROVANIE ODPOVEDE")
    print("="*50)
    print(f"👤 Používateľ: {session.get('username', 'Neznámy')}")
    print(f"❓ Náročnosť:  {difficulty}")
    print(f"🎯 Max tokenov: {max_tokens}")
    print("="*50 + "\n")

    generated_tokens = []
    token_count = 0
    stats = {"cpu": 0, "ram": 0}
    start = time.perf_counter()

    with _model_lock:
        model = get_model()
        
        # Streamovanie tokenov do konzoly pre vizuálny prehľad výkonu
        for token in model.generate(
            prompt,
            max_tokens=max_tokens,
            temp=0.45,
            top_k=40,
            top_p=0.92,
            repeat_penalty=1.12,
            repeat_last_n=64,
            streaming=True,
        ):
            generated_tokens.append(token)
            token_count += 1

            if token_count % 10 == 0:
                stats = get_system_stats()

            progress = min((token_count / max_tokens) * 100, 100)
            bar_length = 20
            filled = int(bar_length * progress / 100)
            bar = "█" * filled + "-" * (bar_length - filled)
            elapsed_now = time.perf_counter() - start
            tps = token_count / max(elapsed_now, 0.001)

            print(
                f"\r[{bar}] {progress:5.1f}% | Tok: {token_count}/{max_tokens} | "
                f"CPU: {stats['cpu']}% | RAM: {stats['ram']} MB | TPS: {tps:.1f}",
                end="",
                flush=True,
            )

    text = "".join(generated_tokens)
    elapsed = time.perf_counter() - start
    cleaned = clean_model_output(text)

    if cleaned.startswith("Používateľ:"):
        cleaned = cleaned.replace("Používateľ:", "", 1).strip()

    # Filtrovanie výstupu pred odoslaním
    cleaned = filter_model_reply(cleaned)

    print("\n\n" + "="*50)
    print("✅ GENEROVANIE DOKONČENÉ")
    print("="*50)
    print(f"⏱️ Čas: {elapsed:.2f}s | 🧩 Tokeny: {token_count}")
    final_stats = get_system_stats()
    print(f"🔥 Koncové CPU: {final_stats['cpu']}% | 💾 RAM: {final_stats['ram']} MB")
    print("="*50 + "\n")

    try:
        save_message(
            session_id,
            user_text,
            cleaned,
            filtered_user_message=filtered_message,
            is_blocked=False,
            elapsed_time=elapsed,
            max_tokens=max_tokens,
        )
    except Exception as e:
        print(f"DB ERROR: {e}")

    return {
        "reply": cleaned,
        "elapsed": round(elapsed, 2),
        "max_tokens": max_tokens,
        "blocked": False,
    }

# =========================================================
# FLASK ROUTES (WEB & API)
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/init-model", methods=["POST"])
def api_init_model():
    global MODEL_READY, MODEL_LOADING
    if MODEL_READY:
        return jsonify({"success": True, "ready": True})
    if MODEL_LOADING:
        return jsonify({"success": False, "loading": True}), 409

    init_model_async()
    return jsonify({"success": True, "loading": True})


@app.route("/api/model-status", methods=["GET"])
def api_model_status():
    return jsonify({
        "ready": MODEL_READY,
        "loading": MODEL_LOADING
    })


@app.route("/api/register", methods=["POST"])
def api_register():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Užívateľské meno a heslo sú povinné."}), 400

    try:
        result = register_user(username, password)
        if result.get("success"):
            return jsonify(result), 201
        return jsonify(result), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/login", methods=["POST"])
def api_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Užívateľské meno a heslo sú povinné."}), 400

    try:
        result = login_user(username, password)
        if result.get("success"):
            _sessions[result["session_token"]] = {
                "user_id": result["user_id"],
                "username": result["username"],
                "session_id": result["session_id"],
            }
            return jsonify(result), 200
        return jsonify(result), 401
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/logout", methods=["POST"])
def api_logout():
    payload = request.get_json(silent=True) or {}
    session_token = str(payload.get("session_token", "")).strip()

    if not session_token:
        return jsonify({"error": "Token relácie chýba."}), 400

    try:
        session = verify_session(session_token)
        if session:
            end_session(session["session_id"])
            if session_token in _sessions:
                del _sessions[session_token]
            return jsonify({"success": True}), 200
        return jsonify({"error": "Neplatná relácia."}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/generate", methods=["POST"])
def api_generate():
    payload = request.get_json(silent=True) or {}
    session_token = str(payload.get("session_token", "")).strip()
    message = str(payload.get("message", "")).strip()

    if not session_token:
        return jsonify({"error": "Chýba token relácie (session_token)."}), 400
    if not message:
        return jsonify({"error": "Správa nesmie byť prázdna."}), 400

    try:
        result = generate_reply(session_token, message)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["GET"])
def api_history():
    session_token = request.args.get("session_token", "").strip()

    if not session_token:
        return jsonify({"error": "Chýba token relácie."}), 400

    try:
        session = verify_session(session_token)
        if not session:
            return jsonify({"error": "Neplatná relácia."}), 400

        history = get_user_history(session["user_id"])
        return jsonify({
            "session_id": session["session_id"],
            "username": session["username"],
            "messages": history,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/sessions", methods=["GET"])
def api_sessions():
    session_token = request.args.get("session_token", "").strip()

    if not session_token:
        return jsonify({"error": "Chýba token relácie."}), 400

    try:
        session = verify_session(session_token)
        if not session:
            return jsonify({"error": "Neplatná relácia."}), 400

        sessions = get_user_sessions(session["user_id"])
        return jsonify({"sessions": sessions})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/audit", methods=["GET"])
def api_audit():
    session_token = request.args.get("session_token", "").strip()

    if not session_token:
        return jsonify({"error": "Chýba token relácie."}), 400

    try:
        session = verify_session(session_token)
        if not session:
            return jsonify({"error": "Neplatná relácia."}), 400

        audit_log = get_audit_log(session["user_id"], limit=50)
        return jsonify({"audit_log": audit_log})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/tts", methods=["POST"])
def api_tts():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()

    if not text:
        return jsonify({"error": "Chýba text pre syntézu."}), 400

    try:
        audio_bytes = synthesize_mp3_bytes(text)
        if not audio_bytes:
            return jsonify({"error": "Nepodarilo sa vygenerovať žiaden zvuk."}), 500

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="tts.mp3",
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 ŠTARTOVANIE FLASK SERVERA")
    print("🌍 Adresa: http://127.0.0.1:5000")
    print("="*50 + "\n")

    # Automatické asynchrónne spustenie načítania modelu pri štarte aplikácie
    init_model_async()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
    )