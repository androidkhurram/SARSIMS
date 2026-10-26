"""Merge follow-ups with previous successful filters."""

from __future__ import annotations

import re

from ksa_sim.parse import ParsedRequest

_RESET = re.compile(
    r"\b(?:"
    r"new search|start over|start again|reset|from scratch|"
    r"forget(?:\s+(?:that|previous|all))?|clear(?:\s+(?:filters|session))?"
    r")\b",
    re.IGNORECASE,
)
_REFINEMENT = re.compile(
    r"\b(?:"
    r"instead|also|same|still|keep|change|switch|update|narrow|"
    r"cheaper|more data|maximum data|max data|less expensive|what about|how about|try|"
    r"but (?:for|with)|just (?:show)|any budget|under \d+"
    r")\b",
    re.IGNORECASE,
)
_NEW_PRODUCT = re.compile(r"\b(?:sim|esim|e-sim|package|plan)\b", re.IGNORECASE)
_SESSION_KEYS = (
    "service_type",
    "trip_days",
    "budget_sar",
    "allow_any_budget",
    "providers",
    "allow_any_provider",
    "sim_form",
    "sort_by",
)


def is_reset_request(request: str) -> bool:
    return bool(_RESET.search(request or ""))


def should_merge_with_previous(
    request: str,
    current: ParsedRequest,
    previous: dict | None,
) -> bool:
    if not previous:
        return False
    if is_reset_request(request):
        return False
    if _REFINEMENT.search(request or ""):
        return True
    missing_duration = current.trip_days is None
    missing_budget = current.budget_sar is None and not current.allow_any_budget
    # "data only sim" is a new product ask — clarify days/budget instead of
    # inheriting them from the previous search.
    if _NEW_PRODUCT.search(request or "") and (missing_duration or missing_budget):
        return False
    complete = (
        bool(current.service_type)
        and current.trip_days is not None
        and (current.budget_sar is not None or current.allow_any_budget)
    )
    return not complete


def session_filters(interpreted: dict | None) -> dict:
    if not interpreted:
        return {}
    cleaned = {}
    for key in _SESSION_KEYS:
        if key not in interpreted:
            continue
        value = interpreted[key]
        if value is None or value == [] or value is False:
            continue
        cleaned[key] = value
    return cleaned


def parsed_from_filters(filters: dict | None) -> ParsedRequest:
    data = session_filters(filters)
    parsed = ParsedRequest()
    parsed.service_type = data.get("service_type")
    parsed.trip_days = data.get("trip_days")
    parsed.budget_sar = data.get("budget_sar")
    parsed.allow_any_budget = bool(data.get("allow_any_budget"))
    parsed.providers = list(data.get("providers") or [])
    parsed.allow_any_provider = bool(data.get("allow_any_provider"))
    parsed.sim_form = data.get("sim_form")
    parsed.sort_by = data.get("sort_by")
    return parsed


def merge_parsed(current: ParsedRequest, previous: dict | None) -> ParsedRequest:
    base = parsed_from_filters(previous)
    if current.error:
        return current

    if current.service_type:
        base.service_type = current.service_type
    if current.trip_days is not None:
        base.trip_days = current.trip_days
    if current.allow_any_budget:
        base.allow_any_budget = True
        base.budget_sar = None
    elif current.budget_sar is not None:
        base.allow_any_budget = False
        base.budget_sar = current.budget_sar
    if current.allow_any_provider:
        base.allow_any_provider = True
        base.providers = []
    elif current.providers:
        base.providers = list(current.providers)
        base.allow_any_provider = False
    if current.sim_form:
        base.sim_form = current.sim_form
    if current.sort_by:
        base.sort_by = current.sort_by
    base.raw = current.raw or base.raw
    return base
