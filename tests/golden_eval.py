#!/usr/bin/env python3
"""Run golden questions against the live official catalog (one fetch)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ksa_sim.advisor import compare_sim_packages
from ksa_sim.constants import ACCURACY_NOTICE, OFF_TOPIC_REPLY, OFFICIAL_OPERATOR_HOSTS
from ksa_sim.official import load_official_catalog

OFFICIAL = OFFICIAL_OPERATOR_HOSTS


def official_url(url: str) -> bool:
    text = (url or "").lower()
    return any(host in text for host in OFFICIAL)


def packages_ok(result: dict) -> list[str]:
    fails = []
    rows = result.get("packages") or []
    if result.get("error"):
        fails.append(f"error: {result['error']}")
        return fails
    for i, row in enumerate(rows, start=1):
        if row.get("provider") in {None, "", "Unknown"}:
            fails.append(f"#{i} unknown provider")
        url = row.get("source_url") or ""
        if not official_url(url):
            fails.append(f"#{i} non-official URL {url}")
        if row.get("price_sar") is None and "not listed" not in (row.get("price_label") or "").lower():
            fails.append(f"#{i} missing price label")
        if row.get("data_gb") is None and "not listed" not in (row.get("data_label") or "").lower():
            fails.append(f"#{i} missing data label")
    return fails


def run_case(name: str, request: str, checks, previous=None, catalog=None) -> dict:
    result = compare_sim_packages(request, previous_filters=previous, catalog=catalog)
    failures = []
    try:
        extra = checks(result) or []
        failures.extend(extra)
    except Exception as exc:
        failures.append(f"check crashed: {exc}")
    status = "PASS" if not failures else "FAIL"
    rec = result.get("recommendation") or {}
    return {
        "id": name,
        "request": request,
        "status": status,
        "failures": failures,
        "needs_clarification": bool(result.get("needs_clarification")),
        "field": result.get("field"),
        "off_topic": bool(result.get("off_topic")),
        "total": result.get("total_results"),
        "trip_days": (result.get("interpreted_as") or {}).get("trip_days"),
        "service_type": (result.get("interpreted_as") or {}).get("service_type"),
        "sort_by": (result.get("interpreted_as") or {}).get("sort_by"),
        "best": rec.get("title") or rec.get("provider"),
        "best_price": rec.get("price_sar"),
        "best_gb": rec.get("data_gb"),
        "notice": result.get("accuracy_notice") == ACCURACY_NOTICE if result.get("packages") else None,
    }


def main() -> int:
    catalog = load_official_catalog(use_cache=False)
    print(f"catalog_size={len(catalog)}", file=sys.stderr)

    cases = []

    def g1(result):
        fails = packages_ok(result)
        if result.get("needs_clarification"):
            fails.append("should not clarify a complete request")
        if not result.get("packages"):
            fails.append("expected packages")
        if not result.get("recommendation"):
            fails.append("expected a recommended package")
        if result.get("accuracy_notice") != ACCURACY_NOTICE:
            fails.append("missing accuracy notice")
        if result.get("source") != "official_operator_websites":
            fails.append(f"source={result.get('source')}")
        return fails

    cases.append(
        run_case(
            "G01 happy path data+voice 14d any budget",
            "data and voice tourist SIM for 14 days any budget",
            g1,
            catalog=catalog,
        )
    )

    def g2(result):
        if not result.get("needs_clarification"):
            return ["expected clarification"]
        if result.get("field") != "service_type":
            return [f"field={result.get('field')}"]
        return []

    cases.append(
        run_case(
            "G02 clarify missing service type",
            "tourist SIM in Riyadh for a week",
            g2,
        )
    )

    def g3(result):
        if not result.get("needs_clarification"):
            return ["expected clarification"]
        if result.get("field") != "trip_days":
            return [f"field={result.get('field')}"]
        return []

    cases.append(
        run_case(
            "G03 clarify missing trip length",
            "data and voice tourist SIM any budget",
            g3,
        )
    )

    def g4(result):
        if not result.get("needs_clarification"):
            return ["expected clarification"]
        if result.get("field") != "budget":
            return [f"field={result.get('field')}"]
        return []

    cases.append(
        run_case(
            "G04 clarify missing budget",
            "data and voice tourist SIM for 7 days",
            g4,
        )
    )

    def off_topic(result):
        if not result.get("off_topic"):
            return ["expected off_topic"]
        if result.get("message") != OFF_TOPIC_REPLY:
            return [f"message={result.get('message')}"]
        if result.get("packages"):
            return ["off-topic should return no packages"]
        return []

    cases.append(run_case("G05 off-topic weather", "What is the weather in Riyadh?", off_topic))
    cases.append(
        run_case(
            "G06 off-topic Haram walkie talkie",
            "where can I buy a walkie talkie in Haram Makkah?",
            off_topic,
        )
    )

    def g7(result):
        fails = packages_ok(result)
        interpreted = result.get("interpreted_as") or {}
        if interpreted.get("sort_by") != "data":
            fails.append(f"sort_by={interpreted.get('sort_by')}")
        if interpreted.get("trip_days") != 30:
            fails.append(f"trip_days={interpreted.get('trip_days')}")
        rec = result.get("recommendation") or {}
        if rec.get("data_gb") is None:
            fails.append("recommended plan has no GB")
        priced = [
            row
            for row in (result.get("packages") or [])
            if row.get("price_sar") is not None and row.get("data_gb") is not None
        ]
        if priced:
            top = max(priced, key=lambda row: row.get("data_gb") or 0)
            if rec.get("data_gb") != top.get("data_gb"):
                fails.append(
                    f"recommended {rec.get('data_gb')} GB, largest priced is {top.get('data_gb')} GB ({top.get('provider')})"
                )
        return fails

    cases.append(
        run_case(
            "G07 maximum data keeps 30-day session",
            "provide me the sim with maximum data",
            g7,
            previous={"service_type": "data", "trip_days": 30, "allow_any_budget": True},
            catalog=catalog,
        )
    )

    def g8(result):
        fails = packages_ok(result)
        interpreted = result.get("interpreted_as") or {}
        if interpreted.get("trip_days") != 120:
            fails.append(f"trip_days={interpreted.get('trip_days')} expected 120")
        if interpreted.get("service_type") != "data":
            fails.append(f"service_type={interpreted.get('service_type')}")
        if not interpreted.get("allow_any_budget"):
            fails.append("expected any budget")
        if result.get("off_topic"):
            fails.append("follow-up treated as off-topic")
        return fails

    cases.append(
        run_case(
            "G08 follow-up changes 14 days to 120",
            "change it to 120 days and any budget is fine",
            g8,
            previous={"service_type": "data", "trip_days": 14},
            catalog=catalog,
        )
    )

    def g9(result):
        fails = packages_ok(result)
        for row in result.get("packages") or []:
            price = row.get("price_sar")
            if price is not None and price > 50:
                fails.append(f"{row.get('title')} price {price} > 50")
        return fails

    cases.append(
        run_case(
            "G09 budget under 50 SAR",
            "data and voice tourist SIM for 14 days under 50 SAR",
            g9,
            catalog=catalog,
        )
    )

    def g10(result):
        fails = packages_ok(result)
        providers = {row.get("provider") for row in (result.get("packages") or [])}
        if providers - {"STC"}:
            fails.append(f"providers={sorted(providers)}")
        if "STC" not in providers:
            fails.append("no STC packages")
        return fails

    cases.append(
        run_case(
            "G10 STC only",
            "STC tourist SIM data and voice for 14 days any budget",
            g10,
            catalog=catalog,
        )
    )

    def g11(result):
        fails = packages_ok(result)
        interpreted = result.get("interpreted_as") or {}
        if interpreted.get("sort_by") != "price":
            fails.append(f"sort_by={interpreted.get('sort_by')}")
        priced = [row for row in (result.get("packages") or []) if row.get("price_sar") is not None]
        rec = result.get("recommendation") or {}
        if priced:
            cheapest = min(priced, key=lambda row: row["price_sar"])
            if rec.get("price_sar") != cheapest["price_sar"]:
                fails.append(
                    f"recommended {rec.get('price_sar')} SAR, cheapest listed is {cheapest['price_sar']} SAR"
                )
            if priced[0].get("price_sar") != cheapest["price_sar"]:
                fails.append(f"rank 1 price {priced[0].get('price_sar')} is not cheapest")
        return fails

    cases.append(
        run_case(
            "G11 cheapest data+voice 7 days",
            "cheapest data and voice SIM for 7 days any budget",
            g11,
            catalog=catalog,
        )
    )

    def g12(result):
        fails = packages_ok(result)
        if (result.get("interpreted_as") or {}).get("service_type") != "data":
            fails.append(f"service_type={result.get('interpreted_as')}")
        rec = result.get("recommendation") or {}
        if rec.get("data_gb") is None:
            fails.append("data-only recommendation has no GB")
        return fails

    cases.append(
        run_case(
            "G12 data only 14 days",
            "data only tourist SIM for 14 days any budget",
            g12,
            catalog=catalog,
        )
    )

    def g13(result):
        fails = packages_ok(result)
        if (result.get("interpreted_as") or {}).get("service_type") != "voice":
            fails.append(f"service_type={result.get('interpreted_as')}")
        rec = result.get("recommendation") or {}
        if rec.get("voice_minutes") is None:
            fails.append("voice-only recommendation has no minutes")
        return fails

    cases.append(
        run_case(
            "G13 voice only 14 days",
            "voice only tourist SIM for 14 days any budget",
            g13,
            catalog=catalog,
        )
    )

    def g14(result):
        fails = packages_ok(result)
        interpreted = result.get("interpreted_as") or {}
        if interpreted.get("budget_sar") != 80:
            fails.append(f"budget={interpreted.get('budget_sar')}")
        if interpreted.get("service_type") != "data":
            fails.append(f"service_type={interpreted.get('service_type')}")
        if interpreted.get("trip_days") != 7:
            fails.append(f"trip_days={interpreted.get('trip_days')}")
        for row in result.get("packages") or []:
            if row.get("price_sar") is not None and row["price_sar"] > 80:
                fails.append(f"over budget {row.get('title')} {row['price_sar']}")
        return fails

    cases.append(
        run_case(
            "G14 merge follow-up under 80 SAR",
            "under 80 SAR",
            g14,
            previous={"service_type": "data", "trip_days": 7},
            catalog=catalog,
        )
    )

    def g15(result):
        fails = packages_ok(result)
        if result.get("needs_clarification"):
            fails.append("eSIM complete request should not clarify")
        forms = {row.get("sim_form") for row in (result.get("packages") or [])}
        if result.get("packages") and forms - {"esim", "either"}:
            fails.append(f"physical plans returned for eSIM ask: {forms}")
        return fails

    cases.append(
        run_case(
            "G15 eSIM only 14 days any budget",
            "data and voice eSIM for 14 days any budget",
            g15,
            catalog=catalog,
        )
    )

    passed = sum(1 for case in cases if case["status"] == "PASS")
    report = {
        "catalog_size": len(catalog),
        "passed": passed,
        "failed": len(cases) - passed,
        "total": len(cases),
        "cases": cases,
    }
    print(json.dumps(report, indent=2))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
