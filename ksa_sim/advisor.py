"""Orchestrate parse → clarify → official operator fetch → rank for KSA SIM plans."""

from __future__ import annotations

import logging

from ksa_sim.clarify import next_clarification
from ksa_sim.constants import ACCURACY_NOTICE, MAX_LISTED_PACKAGES
from ksa_sim.off_topic import is_filter_follow_up, is_off_topic, off_topic_payload
from ksa_sim.official import FetchError, fetch_official_packages, filter_packages
from ksa_sim.parse import parse_request
from ksa_sim.rank import build_comparison, build_recommendation, rank_packages
from ksa_sim.session import (
    merge_parsed,
    session_filters,
    should_merge_with_previous,
)

logger = logging.getLogger(__name__)


def compare_sim_packages(
    request: str,
    *,
    previous_filters: dict | None = None,
    catalog: list[dict] | None = None,
    fetch_catalog=fetch_official_packages,
    require_clarification: bool = True,
) -> dict:
    if is_off_topic(request) and not (
        previous_filters and is_filter_follow_up(request)
    ):
        return off_topic_payload()

    parsed = parse_request(request)
    prior = session_filters(previous_filters)
    merged = False
    if should_merge_with_previous(request, parsed, prior):
        parsed = merge_parsed(parsed, prior)
        merged = True

    if not require_clarification:
        if not parsed.service_type:
            parsed.service_type = "both"
        if parsed.trip_days is None:
            parsed.trip_days = 7
        if parsed.budget_sar is None:
            parsed.allow_any_budget = True

    interpreted = parsed.interpreted_as()
    if parsed.error:
        return {"error": parsed.error, "interpreted_as": interpreted}

    if require_clarification:
        clarification = next_clarification(parsed, interpreted)
        if clarification:
            if merged:
                clarification["merged_with_previous"] = True
            return clarification

    logger.info("KSA SIM official-operator lookup: %s", interpreted)
    try:
        packages = catalog if catalog is not None else fetch_catalog(parsed)
        packages = filter_packages(packages, parsed)
    except FetchError as exc:
        return {
            "error": str(exc),
            "interpreted_as": interpreted,
            "accuracy_notice": ACCURACY_NOTICE,
        }

    ranked = rank_packages(packages, parsed)
    recommendation = build_recommendation(ranked, parsed)
    listed = ranked[:MAX_LISTED_PACKAGES]
    result = {
        "interpreted_as": interpreted,
        "search_query": "official KSA operator websites",
        "total_matched": len(ranked),
        "total_results": len(listed),
        "recommendation": recommendation,
        "packages": listed,
        "comparison": build_comparison(listed, parsed),
        "accuracy_notice": ACCURACY_NOTICE,
        "session_filters": session_filters(interpreted),
        "source": "official_operator_websites",
    }
    if merged:
        result["merged_with_previous"] = True
    if not ranked:
        result["message"] = (
            "No current matching packages were extracted from official operator "
            "websites. Try broadening budget or service type, then purchase only "
            "after checking the operator site."
        )
    return result
