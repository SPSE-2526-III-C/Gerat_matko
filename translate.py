from __future__ import annotations

from deep_translator import GoogleTranslator


def _translate(text: str, source: str, target: str) -> str:
    if not text.strip():
        return text
    try:
        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception:
        return text


def translate_en_to_sk(text: str) -> str:
    """Translate English text to Slovak."""
    return _translate(text, source="en", target="sk")


def translate_sk_to_en(text: str) -> str:
    """Translate Slovak text to English."""
    return _translate(text, source="sk", target="en")


def demo() -> None:
    """Simple demo for both directions."""
    en_text = "Hello, how are you?"
    sk_text = "Ahoj, ako sa máš?"

    print(f"EN → SK: {en_text} -> {translate_en_to_sk(en_text)}")
    print(f"SK → EN: {sk_text} -> {translate_sk_to_en(sk_text)}")


if __name__ == "__main__":
    demo()
    