from __future__ import annotations

import re
import unicodedata

SAFE_REPLY = (
    "Hej! Som tvoj učiteľ, spravaj sa! Bud dobrý chlapček!"
)

BANNED_WORDS = {
    "kokot",
    "pica",
    "píča",
    "kurva",
    "kurvy",
    "jebat",
    "jeb",
    "debil",
    "debilny",
    "debilný",
    "idiot",
    "piča",
    "fuck",
    "shit",
    "bitch",
    "nigga",
    "nigger",
    "čurák",
    "čurak",
    "prijebanec",
    "skurveny",
    "sičurak",
    "lgbt",
    "gay",
    "lesba"
    
    
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text(text: str) -> str:
    lowered = text.lower()
    return _strip_accents(lowered)


def contains_banned_words(text: str) -> bool:
    if not text:
        return False
    normalized = normalize_text(text)
    for word in BANNED_WORDS:
        pattern = rf"\b{re.escape(normalize_text(word))}\b"
        if re.search(pattern, normalized):
            return True
    return False


def filter_user_message(message: str) -> tuple[bool, str]:
    if contains_banned_words(message):
        return False, SAFE_REPLY
    return True, message


def filter_model_reply(reply: str) -> str:
    if contains_banned_words(reply):
        return SAFE_REPLY
    return reply
