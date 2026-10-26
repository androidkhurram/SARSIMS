"""Shared compare/list/details handlers for HTTP, MCP stdio, and Azure MCP."""

from __future__ import annotations

import json
import logging

from ksa_sim.advisor import compare_sim_packages
from ksa_sim.constants import ACCURACY_NOTICE, OFF_TOPIC_REPLY
from ksa_sim.off_topic import is_filter_follow_up, is_off_topic, off_topic_payload

logger = logging.getLogger(__name__)


def _as_filters(value) -> dict | None:
    if not value:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None
    return None


def run_advisor(
    request: str,
    previous_filters=None,
    *,
    require_clarification: bool = True,
) -> dict:
    try:
        return compare_sim_packages(
            request,
            previous_filters=_as_filters(previous_filters),
            require_clarification=require_clarification,
        )
    except Exception:
        logger.exception("SIM advisor failed")
        return {
            "error": "The SIM package search failed.",
            "accuracy_notice": ACCURACY_NOTICE,
        }


def handle_compare(
    request: str,
    *,
    previous_filters=None,
) -> dict:
    """Run one chat turn: refuse, clarify, or rank official visitor packages."""
    text = (request or "").strip()
    if not text:
        return {"error": "request is required"}
    prior = _as_filters(previous_filters)
    if is_off_topic(text) and not (prior and is_filter_follow_up(text)):
        result = off_topic_payload()
        result["mcp_tool"] = "refuse_off_topic"
        return result
    result = run_advisor(text, prior, require_clarification=True)
    result["mcp_tool"] = (
        "refuse_off_topic" if result.get("off_topic") else "compare_sim_packages"
    )
    return result


def handle_list_packages(
    service_type: str = "both",
    trip_days: int = 7,
    budget_sar: str = "any",
) -> dict:
    service = (service_type or "both").strip().lower()
    if service not in {"data", "voice", "both"}:
        service = "both"
    try:
        days = int(trip_days)
    except (TypeError, ValueError):
        days = 7
    budget = str(budget_sar or "any").strip()
    if budget.lower() in {"", "any", "none"}:
        budget_text = "any budget"
    else:
        budget_text = f"under {budget} SAR"
    request = (
        f"{service} tourist SIM for {days} days {budget_text} "
        "currently available in Saudi Arabia"
    )
    result = run_advisor(request, require_clarification=False)
    result["list_mode"] = True
    result["mcp_tool"] = "list_active_sim_packages"
    return result


def handle_package_details(package_query: str) -> dict:
    query = (package_query or "").strip()
    if not query:
        return {"error": "package_query is required."}
    if is_off_topic(query):
        result = off_topic_payload()
        result["mcp_tool"] = "refuse_off_topic"
        return result
    request = (
        f"{query} tourist SIM Saudi Arabia current price plan currently available any budget"
    )
    result = run_advisor(request, require_clarification=False)
    result["details_mode"] = True
    result["mcp_tool"] = "get_package_details"
    return result


def handle_refuse(request: str) -> dict:
    return {
        "off_topic": True,
        "request": request,
        "message": OFF_TOPIC_REPLY,
        "packages": [],
        "mcp_tool": "refuse_off_topic",
    }
