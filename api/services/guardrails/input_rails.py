"""
input_rails.py — Phase 13: Input Rail (Prompt Injection & Jailbreak Detection).

Blocks known prompt injection and jailbreak patterns before they reach the main LLM.
Uses regex pattern matching + keyword heuristics (no external ML model required).

Usage:
    from api.services.guardrails.input_rails import check_input, InputVerdict
    verdict = check_input(user_message)
    if verdict.blocked:
        return {"error": verdict.reason}
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class InputVerdict:
    blocked: bool
    reason: Optional[str] = None
    pattern_matched: Optional[str] = None


# ── Prompt injection patterns ────────────────────────────────────────────────
# These catch direct attempts to override system instructions.

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # System prompt override attempts
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
     "Attempted system prompt override"),
    (r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
     "Attempted system prompt override"),
    (r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
     "Attempted system prompt override"),
    (r"you\s+are\s+now\s+(a|an)\s+",
     "Attempted role hijacking"),
    (r"new\s+instructions?\s*:",
     "Attempted instruction injection"),
    (r"system\s*:\s*",
     "Attempted system message injection"),
    (r"\[system\]",
     "Attempted system message injection"),
    (r"<\s*system\s*>",
     "Attempted system message injection"),

    # DAN-style jailbreaks
    (r"do\s+anything\s+now",
     "DAN-style jailbreak attempt"),
    (r"jailbreak",
     "Jailbreak attempt (explicit mention)"),
    (r"bypass\s+(all\s+)?(safety|content|security)\s+(filters?|restrictions?|rules?)",
     "Safety bypass attempt"),

    # Prompt leaking
    (r"(reveal|show|print|output|repeat)\s+(your|the)\s+(system|initial|original)\s+(prompt|instructions?)",
     "Prompt leaking attempt"),
    (r"what\s+(are|is)\s+your\s+(system|initial|original)\s+(prompt|instructions?)",
     "Prompt leaking attempt"),
    (r"repeat\s+(everything|all)\s+(above|before)",
     "Prompt leaking attempt"),

    # Encoding/obfuscation attacks
    (r"(base64|rot13|hex)\s+(encode|decode)",
     "Encoding-based evasion attempt"),
]

# ── Jailbreak keyword heuristics ─────────────────────────────────────────────
# High-confidence keywords that strongly indicate malicious intent.

_JAILBREAK_KEYWORDS: set[str] = {
    "DAN", "jailbreak", "prompt injection",
    "ignore previous", "ignore instructions",
    "you are now", "act as if",
}

# ── Compiled patterns ────────────────────────────────────────────────────────
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in _INJECTION_PATTERNS
]


def check_input(message: str) -> InputVerdict:
    """Check user input for prompt injection and jailbreak patterns.

    Args:
        message: The raw user input string.

    Returns:
        InputVerdict with blocked=True if a pattern is detected.
    """
    if not message or not message.strip():
        return InputVerdict(blocked=False)

    # Check regex patterns
    for compiled, reason in _COMPILED_PATTERNS:
        if compiled.search(message):
            return InputVerdict(
                blocked=True,
                reason=reason,
                pattern_matched=compiled.pattern,
            )

    # Check keyword heuristics (case-insensitive)
    msg_lower = message.lower()
    for keyword in _JAILBREAK_KEYWORDS:
        if keyword.lower() in msg_lower:
            return InputVerdict(
                blocked=True,
                reason=f"Jailbreak keyword detected: {keyword}",
                pattern_matched=keyword,
            )

    return InputVerdict(blocked=False)
