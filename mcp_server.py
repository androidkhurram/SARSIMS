#!/usr/bin/env python3
"""Stdio MCP server: KSA SIM package comparison for international travellers.

Plan facts live behind these tools. Clients must not invent prices.
Every successful search is an official operator website check, not a live-price guarantee.
"""

from __future__ import annotations

import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from ksa_sim.advisor import compare_sim_packages as run_compare
from ksa_sim.constants import ACCURACY_NOTICE, OFF_TOPIC_REPLY
from ksa_sim.env import load_env
from ksa_sim.off_topic import is_off_topic, off_topic_payload

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
load_env()

mcp = FastMCP(
    "ksa-sim",
    instructions=(
        "Mandatory MCP tools for ranking currently available Saudi Arabia (KSA) "
        "tourist/visitor SIM packages for international travellers. Use tools for "
        "all price/plan claims. Facts come only from official operator websites "
        "(STC, Mobily, Zain, Lebara, Virgin Mobile). Exclude discontinued packages. "
        "Ask clarifying follow-ups when needs_clarification is returned. Reuse "
        "session_filters as previous_filters for continuity. Off-topic requests "
        "must use refuse_off_topic. Always surface accuracy_notice: prices/promos "
        "are tied to the latest official-site check and are not a guarantee of "
        f"real-time promo accuracy without a fresh refresh/source check. {ACCURACY_NOTICE}"
    ),
    log_level="ERROR",
)


def _filters(previous_filters: str) -> dict | None:
    if not previous_filters:
        return None
    try:
        loaded = json.loads(previous_filters)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _run(request: str, previous_filters: str = "", require_clarification: bool = True) -> dict:
    try:
        return run_compare(
            request,
            previous_filters=_filters(previous_filters),
            require_clarification=require_clarification,
        )
    except Exception:
        logging.exception("SIM MCP tool failed")
        return {
            "error": "The SIM package search failed.",
            "accuracy_notice": ACCURACY_NOTICE,
        }


@mcp.tool()
def compare_sim_packages(request: str, previous_filters: str = "") -> str:
    """Compare and rank currently available KSA SIM packages for travellers.

    Pass the user's sentence unchanged. Before searching, the server may require
    service type (data / voice / both), trip length in days, and budget in SAR.
    If any are missing, the response sets needs_clarification with one follow-up
    question — ask the user that question, then call again with the original
    request plus the missing detail. After a successful search, reuse
    session_filters as previous_filters for refinements. Irrelevant requests
    return the fixed off-topic message. Results include accuracy_notice because
    real-time promo accuracy is not guaranteed without a fresh source check.
    Every call checks official operator websites only.
    """
    return json.dumps(_run(request, previous_filters, require_clarification=True))


@mcp.tool()
def list_active_sim_packages(
    service_type: str = "both",
    trip_days: int = 7,
    budget_sar: str = "any",
) -> str:
    """List currently advertised KSA tourist/visitor SIM packages from official sites.

    Uses only active-looking results (discontinued/expired wording is dropped).
    Defaults: data+voice, 7 days, any budget. Always includes accuracy_notice.
    """
    service = (service_type or "both").strip().lower()
    if service not in {"data", "voice", "both"}:
        service = "both"
    budget = (budget_sar or "any").strip()
    if budget.lower() in {"", "any", "none"}:
        budget_text = "any budget"
    else:
        budget_text = f"under {budget} SAR"
    request = (
        f"{service} tourist SIM for {int(trip_days)} days {budget_text} "
        "currently available in Saudi Arabia"
    )
    result = _run(request, require_clarification=False)
    result["list_mode"] = True
    return json.dumps(result)


@mcp.tool()
def get_package_details(package_query: str) -> str:
    """Look up one current KSA SIM package by name, provider, or source wording.

    Performs a fresh official-site check. Returns ranked matching candidates
    plus accuracy_notice. Off-topic queries get the fixed refusal.
    """
    query = (package_query or "").strip()
    if not query:
        return json.dumps({"error": "package_query is required."})
    if is_off_topic(query):
        return json.dumps(off_topic_payload())
    request = (
        f"{query} tourist SIM Saudi Arabia current price plan currently available any budget"
    )
    result = _run(request, require_clarification=False)
    result["details_mode"] = True
    return json.dumps(result)


@mcp.tool()
def refuse_off_topic(request: str) -> str:
    """Return the fixed refusal when the user asks for non-SIM information.

    Use when the question is outside KSA SIM / voice / data packages from
    service providers (visa, hotels, weather, etc.).
    """
    return json.dumps(
        {
            "off_topic": True,
            "request": request,
            "message": OFF_TOPIC_REPLY,
            "packages": [],
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
