"""CLI tool for viewing and managing chat history from database."""

import argparse
from pathlib import Path
from tabulate import tabulate
from db import get_all_sessions, get_session_history, get_session_metadata


def print_sessions() -> None:
    """Print all chat sessions."""
    sessions = get_all_sessions()
    if not sessions:
        print("No chat sessions found.")
        return
    
    table_data = [
        [
            s["id"],
            s["session_start"],
            s["session_end"] or "ONGOING",
            s["message_count"],
        ]
        for s in sessions
    ]
    
    print("\n=== Chat Sessions ===")
    print(tabulate(
        table_data,
        headers=["ID", "Start Time", "End Time", "Message Count"],
        tablefmt="grid",
    ))
    print()


def print_session_details(session_id: int) -> None:
    """Print detailed history of a specific session."""
    metadata = get_session_metadata(session_id)
    history = get_session_history(session_id)
    
    if not history:
        print(f"No messages found for session {session_id}.")
        return
    
    print(f"\n=== Session {session_id} Details ===")
    if metadata:
        print("\nMetadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")
    
    print(f"\nTotal messages: {len(history)}")
    print("\n=== Messages ===\n")
    
    for i, msg in enumerate(history, 1):
        status = "🔒 BLOCKED" if msg["is_blocked"] else "✓"
        print(f"[{i}] {status} | {msg['timestamp']}")
        print(f"    User: {msg['user_message'][:100]}...")
        if not msg["is_blocked"]:
            print(f"    Bot:  {msg['bot_reply'][:100]}...")
            print(f"    Response time: {msg['elapsed_time']:.2f}s | Tokens: {msg['max_tokens']}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View and manage chat history from database.",
    )
    parser.add_argument(
        "--sessions",
        action="store_true",
        help="List all chat sessions",
    )
    parser.add_argument(
        "--session",
        type=int,
        metavar="ID",
        help="Show detailed history for a specific session",
    )
    
    args = parser.parse_args()
    
    if args.sessions:
        print_sessions()
    elif args.session:
        print_session_details(args.session)
    else:
        print_sessions()


if __name__ == "__main__":
    main()
