"""Database module for storing chat history with user authentication and validation."""

import sqlite3
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).resolve().parent / "chat_history.db"


def init_db() -> None:
    """Initialize database with required tables including user management."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    
    # Chat sessions table with user reference
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_end TIMESTAMP,
            message_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            user_message TEXT NOT NULL,
            bot_reply TEXT NOT NULL,
            filtered_user_message TEXT,
            is_blocked INTEGER DEFAULT 0,
            elapsed_time REAL,
            max_tokens INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    """)
    
    # Metadata table for storing additional info
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    """)
    
    # Audit log for all database operations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(username: str, password: str) -> dict:
    """Register a new user. Returns user info or error."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        password_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO users (username, password_hash)
            VALUES (?, ?)
        """, (username, password_hash))
        
        user_id = cursor.lastrowid
        
        # Log action
        cursor.execute("""
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, ?, ?)
        """, (user_id, "USER_REGISTERED", f"User {username} registered"))
        
        conn.commit()
        conn.close()
        
        return {"success": True, "user_id": user_id, "username": username}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Username already exists"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def login_user(username: str, password: str) -> dict:
    """Authenticate user and return session token. Returns user info or error."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        password_hash = hash_password(password)
        cursor.execute("""
            SELECT id, username FROM users 
            WHERE username = ? AND password_hash = ?
        """, (username, password_hash))
        
        user = cursor.fetchone()
        
        if not user:
            # Log failed attempt
            cursor.execute("""
                INSERT INTO audit_log (action, details)
                VALUES (?, ?)
            """, ("LOGIN_FAILED", f"Failed login attempt for {username}"))
            conn.commit()
            conn.close()
            return {"success": False, "error": "Invalid credentials"}
        
        user_id, username = user
        
        # Update last login
        cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
        
        # Create new session token
        session_token = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO chat_sessions (user_id, session_token)
            VALUES (?, ?)
        """, (user_id, session_token))
        
        session_id = cursor.lastrowid
        
        # Log successful login
        cursor.execute("""
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, ?, ?)
        """, (user_id, "USER_LOGIN", f"User {username} logged in"))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "user_id": user_id,
            "username": username,
            "session_id": session_id,
            "session_token": session_token,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def verify_session(session_token: str) -> Optional[dict]:
    """Verify session token and return session/user info if valid."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cs.id, cs.user_id, u.username, cs.session_start
            FROM chat_sessions cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.session_token = ? AND cs.session_end IS NULL
        """, (session_token,))
        
        session = cursor.fetchone()
        conn.close()
        
        if not session:
            return None
        
        return {
            "session_id": session[0],
            "user_id": session[1],
            "username": session[2],
            "session_start": session[3],
        }
    except Exception as e:
        print(f"Error verifying session: {e}")
        return None


def create_session_for_user(user_id: int) -> str:
    """Create a new chat session for a user. Returns session token."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        session_token = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO chat_sessions (user_id, session_token)
            VALUES (?, ?)
        """, (user_id, session_token))
        
        # Log action
        cursor.execute("""
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, ?, ?)
        """, (user_id, "SESSION_CREATED", f"New session created"))
        
        conn.commit()
        conn.close()
        
        return session_token
    except Exception as e:
        print(f"Error creating session: {e}")
        raise


def create_session() -> int:
    """Create a new chat session and return session ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (session_start) VALUES (CURRENT_TIMESTAMP)")
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def save_message(
    session_id: int,
    user_message: str,
    bot_reply: str,
    filtered_user_message: Optional[str] = None,
    is_blocked: bool = False,
    elapsed_time: float = 0.0,
    max_tokens: int = 0,
) -> int:
    """Save a single message exchange to the database with validation."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verify session exists and belongs to a valid user
        cursor.execute("""
            SELECT user_id FROM chat_sessions WHERE id = ? AND session_end IS NULL
        """, (session_id,))
        
        session_check = cursor.fetchone()
        if not session_check:
            raise ValueError(f"Invalid or ended session: {session_id}")
        
        user_id = session_check[0]
        
        # Insert message
        cursor.execute("""
            INSERT INTO chat_messages 
            (session_id, user_message, bot_reply, filtered_user_message, is_blocked, elapsed_time, max_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, user_message, bot_reply, filtered_user_message, 1 if is_blocked else 0, elapsed_time, max_tokens))
        
        message_id = cursor.lastrowid
        
        # Update message count
        cursor.execute("UPDATE chat_sessions SET message_count = message_count + 1 WHERE id = ?", (session_id,))
        
        # Log action
        cursor.execute("""
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, ?, ?)
        """, (user_id, "MESSAGE_SAVED", f"Message {message_id} saved in session {session_id}"))
        
        conn.commit()
        conn.close()
        
        return message_id
    except Exception as e:
        print(f"Error saving message: {e}")
        raise


def save_metadata(session_id: int, key: str, value: str) -> None:
    """Save metadata with validation."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verify session exists
        cursor.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,))
        session_check = cursor.fetchone()
        if not session_check:
            raise ValueError(f"Invalid session: {session_id}")
        
        user_id = session_check[0]
        
        cursor.execute("""
            INSERT INTO metadata (session_id, key, value)
            VALUES (?, ?, ?)
        """, (session_id, key, value))
        
        # Log action
        cursor.execute("""
            INSERT INTO audit_log (user_id, action, details)
            VALUES (?, ?, ?)
        """, (user_id, "METADATA_SAVED", f"Metadata {key}={value} for session {session_id}"))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving metadata: {e}")
        raise


def end_session(session_id: int) -> None:
    """Mark a chat session as ended."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE chat_sessions SET session_end = CURRENT_TIMESTAMP WHERE id = ?
        """, (session_id,))
        
        # Get user_id for logging
        cursor.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,))
        result = cursor.fetchone()
        if result:
            user_id = result[0]
            cursor.execute("""
                INSERT INTO audit_log (user_id, action, details)
                VALUES (?, ?, ?)
            """, (user_id, "SESSION_ENDED", f"Session {session_id} ended"))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error ending session: {e}")


def get_session_history(session_id: int) -> list[dict]:
    """Retrieve all messages from a specific session."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, user_message, bot_reply, is_blocked, elapsed_time, timestamp
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "user_message": row[1],
                "bot_reply": row[2],
                "is_blocked": bool(row[3]),
                "elapsed_time": row[4],
                "timestamp": row[5],
            }
            for row in rows
        ]
    except Exception as e:
        print(f"Error getting session history: {e}")
        return []


def get_user_sessions(user_id: int) -> list[dict]:
    """Retrieve all chat sessions for a specific user."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, session_start, session_end, message_count
            FROM chat_sessions
            WHERE user_id = ?
            ORDER BY session_start DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "session_start": row[1],
                "session_end": row[2],
                "message_count": row[3],
            }
            for row in rows
        ]
    except Exception as e:
        print(f"Error getting user sessions: {e}")
        return []


def get_session_metadata(session_id: int) -> dict:
    """Retrieve metadata for a specific session."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT key, value
            FROM metadata
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error getting session metadata: {e}")
        return {}


def get_audit_log(user_id: Optional[int] = None, limit: int = 100) -> list[dict]:
    """Retrieve audit log entries."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if user_id:
            cursor.execute("""
                SELECT id, user_id, action, details, timestamp
                FROM audit_log
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, limit))
        else:
            cursor.execute("""
                SELECT id, user_id, action, details, timestamp
                FROM audit_log
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "user_id": row[1],
                "action": row[2],
                "details": row[3],
                "timestamp": row[4],
            }
            for row in rows
        ]
    except Exception as e:
        print(f"Error getting audit log: {e}")
        return []


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
