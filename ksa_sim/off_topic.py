"""Detect requests outside KSA SIM / voice / data package scope."""

from __future__ import annotations

import re

from ksa_sim.constants import OFF_TOPIC_REPLY

# Strong SIM signals — presence means the ask is in scope.
_SIM_TOPIC = re.compile(
    r"\b(?:"
    r"sim|esim|e-sim|prepaid|stc|mobily|zain|lebara|virgin|"
    r"roaming|recharge|top[- ]?up|"
    r"(?:data|voice)\s+(?:plan|package|bundle|sim)|"
    r"(?:plan|package|bundle)\s+(?:for\s+)?(?:data|voice)|"
    r"tourist\s+sim|visitor\s+sim|travell?er\s+sim"
    r")\b",
    re.IGNORECASE,
)

_FILTER_FOLLOW_UP = re.compile(
    r"\b(?:"
    r"day|days|budget|change|instead|update|switch|cheaper|"
    r"sar|provider|esim|data|voice|gb|maximum|any budget"
    r")\b",
    re.IGNORECASE,
)


def is_filter_follow_up(request: str) -> bool:
    text = (request or "").strip()
    if not text:
        return False
    if _OFF_TOPIC.search(text):
        return False
    return bool(_FILTER_FOLLOW_UP.search(text))


_OFF_TOPIC = re.compile(
    r"\b(?:"
    r"visa|iqama|passport|hotel|flight|airline|uber|careem|"
    r"restaurant|weather|crypto|stock|bitcoin|recipe|"
    r"homework|essay|code this|write a poem|"
    r"bank account|mortgage|insurance polic"
    r")\b",
    re.IGNORECASE,
)


def is_off_topic(request: str) -> bool:
    text = (request or "").strip()
    if not text:
        return False
    if _SIM_TOPIC.search(text):
        return False
    if _OFF_TOPIC.search(text):
        return True
    # Short replies during clarification are usually on-topic fragments.
    if len(text.split()) <= 6:
        return False
    # Longer asks with no SIM signal are out of scope.
    return True


def off_topic_payload() -> dict:
    return {
        "off_topic": True,
        "message": OFF_TOPIC_REPLY,
        "packages": [],
    }
