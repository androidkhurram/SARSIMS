"""Azure Functions HTTP + MCP host for the KSA SIM advisor.

HTTP: chat UI at GET / and POST /api/compare.
MCP: Azure Functions MCP webhook for AI Foundry agents
(https://<app>.azurewebsites.net/runtime/webhooks/mcp/sse).
"""

from __future__ import annotations

import json
import logging

import azure.functions as func

from ksa_sim.env import load_env
from ksa_sim.web_api import (
    handle_compare,
    handle_list_packages,
    handle_package_details,
    handle_refuse,
)
from local_ui import PAGE

load_env()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _cors() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _json(payload: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status,
        mimetype="application/json",
        headers=_cors(),
    )


def _tool_properties(*fields: tuple[str, str, str]) -> str:
    return json.dumps(
        [
            {
                "propertyName": name,
                "propertyType": kind,
                "description": description,
            }
            for name, kind, description in fields
        ]
    )


def _mcp_arguments(context) -> dict:
    if isinstance(context, dict):
        payload = context
    else:
        try:
            payload = json.loads(context or "{}")
        except json.JSONDecodeError:
            return {}
    if not isinstance(payload, dict):
        return {}
    arguments = payload.get("arguments")
    return arguments if isinstance(arguments, dict) else payload


def _index_page() -> func.HttpResponse:
    return func.HttpResponse(PAGE, mimetype="text/html; charset=utf-8", headers=_cors())


@app.route(route="", methods=["GET"])
def index(req: func.HttpRequest) -> func.HttpResponse:
    return _index_page()


@app.route(route="index.html", methods=["GET"])
def index_html(req: func.HttpRequest) -> func.HttpResponse:
    return _index_page()


@app.route(route="api/status", methods=["GET"])
def status(req: func.HttpRequest) -> func.HttpResponse:
    return _json({"source": "official_operator_websites"})


@app.route(route="api/compare", methods=["POST", "OPTIONS"])
def compare(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors())
    try:
        data = req.get_json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    request = str(data.get("request") or "").strip()
    prior = data.get("previous_filters")
    if not isinstance(prior, dict):
        prior = None
    if not request:
        return _json({"error": "request is required"}, 400)
    try:
        result = handle_compare(request, previous_filters=prior)
    except Exception:
        logging.exception("KSA SIM compare failed")
        return _json({"error": "The SIM package search failed."}, 500)
    return _json(result)


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="compare_sim_packages",
    description=(
        "Compare currently available KSA tourist/visitor SIM packages from official "
        "operator websites (STC, Mobily, Zain, Lebara, Virgin Mobile). Pass the "
        "traveller's sentence unchanged. Ask follow-ups when needs_clarification is "
        "returned. Reuse session_filters as previous_filters. Results are a source "
        "check, not a live promo guarantee."
    ),
    toolProperties=_tool_properties(
        ("request", "string", "Traveller request, for example: voice only SIM for 14 days any budget"),
        (
            "previous_filters",
            "string",
            "Optional JSON string of session_filters from the previous successful turn",
        ),
    ),
)
def mcp_compare_sim_packages(context) -> str:
    args = _mcp_arguments(context)
    result = handle_compare(
        str(args.get("request") or ""),
        previous_filters=args.get("previous_filters"),
    )
    return json.dumps(result)


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="list_active_sim_packages",
    description=(
        "List currently advertised KSA tourist/visitor SIM packages from official "
        "operator websites. Defaults: data+voice, 7 days, any budget."
    ),
    toolProperties=_tool_properties(
        ("service_type", "string", "data, voice, or both"),
        ("trip_days", "string", "Trip length in days"),
        ("budget_sar", "string", "Budget in SAR, or any"),
    ),
)
def mcp_list_active_sim_packages(context) -> str:
    args = _mcp_arguments(context)
    return json.dumps(
        handle_list_packages(
            str(args.get("service_type") or "both"),
            args.get("trip_days") or 7,
            str(args.get("budget_sar") or "any"),
        )
    )


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="get_package_details",
    description="Look up one current KSA SIM package by name, provider, or source wording.",
    toolProperties=_tool_properties(
        ("package_query", "string", "Package or provider name, for example: Mobily Visitor 100"),
    ),
)
def mcp_get_package_details(context) -> str:
    args = _mcp_arguments(context)
    return json.dumps(handle_package_details(str(args.get("package_query") or "")))


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="refuse_off_topic",
    description="Return the fixed refusal when the question is not about KSA SIM packages.",
    toolProperties=_tool_properties(
        ("request", "string", "The off-topic user question"),
    ),
)
def mcp_refuse_off_topic(context) -> str:
    args = _mcp_arguments(context)
    return json.dumps(handle_refuse(str(args.get("request") or "")))
