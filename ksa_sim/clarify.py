"""Ask one follow-up at a time before searching."""

from __future__ import annotations

from ksa_sim.parse import ParsedRequest

_SERVICE_OPTIONS = [
    {"id": "data", "label": "Data only"},
    {"id": "voice", "label": "Voice only"},
    {"id": "both", "label": "Data + voice"},
]
_DURATION_OPTIONS = [
    {"id": "3", "label": "3 days"},
    {"id": "7", "label": "7 days"},
    {"id": "14", "label": "14 days"},
    {"id": "30", "label": "30 days"},
]
_BUDGET_OPTIONS = [
    {"id": "any", "label": "Any budget"},
    {"id": "50", "label": "Under 50 SAR"},
    {"id": "100", "label": "Under 100 SAR"},
    {"id": "200", "label": "Under 200 SAR"},
]


def next_clarification(parsed: ParsedRequest, interpreted: dict) -> dict | None:
    if not parsed.service_type:
        return _ask(
            field="service_type",
            question="Do you need data only, voice only, or both data and voice?",
            placeholder="data, voice, or both",
            interpreted=interpreted,
            options=_SERVICE_OPTIONS,
            hint=(
                "Ask the user this question, then call compare_sim_packages again "
                "with their original request plus data, voice, or both."
            ),
        )

    if parsed.trip_days is None:
        return _ask(
            field="trip_days",
            question="How many days will you be in Saudi Arabia?",
            placeholder="e.g. 7 days",
            interpreted=interpreted,
            options=_DURATION_OPTIONS,
            hint=(
                "Ask the user this question, then call compare_sim_packages again "
                "with their original request plus the trip length."
            ),
        )

    if parsed.budget_sar is None and not parsed.allow_any_budget:
        return _ask(
            field="budget",
            question="What is your budget in SAR, or say any budget?",
            placeholder="e.g. under 100 SAR, or any budget",
            interpreted=interpreted,
            options=_BUDGET_OPTIONS,
            hint=(
                "Ask the user this question, then call compare_sim_packages again "
                "with their original request plus the budget."
            ),
        )

    return None


def _ask(
    *,
    field: str,
    question: str,
    placeholder: str,
    interpreted: dict,
    hint: str,
    options: list[dict] | None = None,
) -> dict:
    payload = {
        "needs_clarification": True,
        "field": field,
        "question": question,
        "input": {"type": "text", "placeholder": placeholder},
        "interpreted_as": interpreted,
        "hint": hint,
    }
    if options:
        payload["options"] = options
    return payload
