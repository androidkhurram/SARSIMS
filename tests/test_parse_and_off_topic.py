"""Unit tests that do not call live operator websites."""

from __future__ import annotations

import json
import unittest

from ksa_sim.advisor import compare_sim_packages
from ksa_sim.clarify import next_clarification
from ksa_sim.constants import (
    ACCURACY_NOTICE,
    MAX_LISTED_PACKAGES,
    OFF_TOPIC_REPLY,
    PROVIDERS,
    RECOMMENDATION_CRITERIA,
)
from ksa_sim.off_topic import is_off_topic, off_topic_payload
from ksa_sim.official import filter_packages, _parse_mobily, _parse_stc, _parse_zain_json
from ksa_sim.parse import parse_request
from ksa_sim.rank import build_recommendation, rank_packages
from ksa_sim.session import merge_parsed, should_merge_with_previous


def _pkg(**overrides):
    row = {
        "provider": "STC",
        "plan_name": "visitor 26",
        "summary": "official visitor plan",
        "price_sar": 31,
        "data_gb": 6,
        "voice_minutes": 60,
        "validity_days": 14,
        "sim_form": "physical",
        "source_url": "https://www.stc.com.sa/en/personal/mobile/packages/sawa-ziyara.html",
        "status": "active_candidate",
    }
    row.update(overrides)
    data = row.get("data_gb")
    data_text = f"{data:g} GB" if data is not None else "data not listed"
    price = row.get("price_sar")
    price_text = f"{price:g} SAR" if price is not None else "price not listed"
    row.setdefault(
        "title",
        f"{row['provider']} {row.get('plan_name') or 'tourist SIM'} — {data_text} / {price_text}",
    )
    return row


class ParseTests(unittest.TestCase):
    def test_parses_data_trip_and_budget(self):
        parsed = parse_request("data SIM for 7 days under 100 SAR on STC")
        self.assertEqual(parsed.service_type, "data")
        self.assertEqual(parsed.trip_days, 7)
        self.assertEqual(parsed.budget_sar, 100.0)
        self.assertEqual(parsed.providers, ["STC"])

    def test_clarifies_missing_service(self):
        parsed = parse_request("tourist SIM in Riyadh for a week")
        ask = next_clarification(parsed, parsed.interpreted_as())
        self.assertTrue(ask["needs_clarification"])
        self.assertEqual(ask["field"], "service_type")

    def test_parses_maximum_data_sort(self):
        parsed = parse_request("provide me the sim with maximum data")
        self.assertEqual(parsed.service_type, "data")
        self.assertEqual(parsed.sort_by, "data")

    def test_follow_up_days_override_wins(self):
        parsed = parse_request(
            "get me best data package for 14 days change it to 120 days and any budget is fine"
        )
        self.assertEqual(parsed.service_type, "data")
        self.assertEqual(parsed.trip_days, 120)
        self.assertTrue(parsed.allow_any_budget)

    def test_aggregator_brands_are_not_official_providers(self):
        parsed = parse_request("Airalo eSIM for Saudi Arabia")
        self.assertEqual(parsed.providers, [])
        self.assertNotIn("Airalo", PROVIDERS)
        self.assertNotIn("Holafly", PROVIDERS)


class OffTopicTests(unittest.TestCase):
    def test_visa_is_off_topic(self):
        self.assertTrue(is_off_topic("How do I get a tourist visa for KSA?"))
        payload = off_topic_payload()
        self.assertEqual(payload["message"], OFF_TOPIC_REPLY)

    def test_sim_is_on_topic(self):
        self.assertFalse(is_off_topic("Compare Mobily tourist SIM data plans"))


class RankTests(unittest.TestCase):
    def test_cheaper_ranks_first_when_sorting_by_price(self):
        parsed = parse_request("data for 7 days any budget cheapest")
        packages = [
            {"provider": "A", "title": "A", "price_sar": 120, "data_gb": 10},
            {"provider": "B", "title": "B", "price_sar": 40, "data_gb": 5},
        ]
        ranked = rank_packages(packages, parsed)
        self.assertEqual(ranked[0]["provider"], "B")
        self.assertIn("promo", ACCURACY_NOTICE.lower())
        self.assertIn("official", ACCURACY_NOTICE.lower())

    def test_maximum_data_prefers_listed_gb(self):
        parsed = parse_request("provide me the sim with maximum data")
        packages = [
            {"provider": "STC", "title": "STC 100 SAR", "price_sar": 100, "data_gb": None},
            {"provider": "Mobily", "title": "Mobily 50GB", "price_sar": 150, "data_gb": 50},
            {"provider": "Zain", "title": "Zain 10GB", "price_sar": 40, "data_gb": 10},
        ]
        ranked = rank_packages(packages, parsed)
        self.assertEqual(ranked[0]["provider"], "Mobily")
        rec = build_recommendation(ranked, parsed)
        self.assertEqual(rec["data_gb"], 50)
        self.assertIn("50 GB", rec["summary"])

    def test_max_data_prefers_priced_plan_over_unpriced_unlimited(self):
        parsed = parse_request("provide me the sim with maximum data")
        packages = [
            {"provider": "Mobily", "title": "Unlimited", "price_sar": None, "data_gb": 999, "rank_score": 40},
            {"provider": "Zain", "title": "80GB", "price_sar": 200, "data_gb": 80, "rank_score": 20},
        ]
        ranked = rank_packages(packages, parsed)
        rec = build_recommendation(ranked, parsed)
        self.assertEqual(rec["provider"], "Zain")
        self.assertEqual(rec["price_sar"], 200)

    def test_voice_only_does_not_recommend_data_addon(self):
        parsed = parse_request("voice only tourist SIM for 14 days any budget")
        packages = [
            {
                "provider": "Zain",
                "title": "Data Plus Unlimited",
                "price_sar": 100,
                "data_gb": 999,
                "voice_minutes": None,
                "validity_days": 7,
            },
            {
                "provider": "STC",
                "title": "visitor 26",
                "price_sar": 31,
                "data_gb": 6,
                "voice_minutes": 60,
                "validity_days": 14,
            },
            {
                "provider": "Mobily",
                "title": "Visitor 150",
                "price_sar": 172.5,
                "data_gb": 40,
                "voice_minutes": 600,
                "validity_days": 30,
            },
        ]
        ranked = rank_packages(packages, parsed)
        rec = build_recommendation(ranked, parsed)
        self.assertIsNotNone(rec.get("voice_minutes"))
        self.assertNotEqual(rec["title"], "Data Plus Unlimited")
        self.assertEqual(ranked[0].get("voice_minutes"), rec.get("voice_minutes"))

    def test_voice_only_ranks_minutes_trip_and_price_not_data(self):
        parsed = parse_request("voice only tourist SIM for 30 days any budget")
        packages = [
            _pkg(
                provider="Mobily",
                plan_name="Visitor 90",
                price_sar=103.5,
                data_gb=55,
                voice_minutes=300,
                validity_days=30,
            ),
            _pkg(
                provider="STC",
                plan_name="visitor 86",
                price_sar=100,
                data_gb=51,
                voice_minutes=300,
                validity_days=28,
            ),
            _pkg(
                provider="Zain",
                plan_name="Visitor 110",
                price_sar=126.5,
                data_gb=45,
                voice_minutes=500,
                validity_days=28,
            ),
            _pkg(
                provider="Mobily",
                plan_name="Visitor 150",
                price_sar=172.5,
                data_gb=40,
                voice_minutes=600,
                validity_days=30,
            ),
            _pkg(
                provider="Zain",
                plan_name="Zain Visitor 150",
                price_sar=172.5,
                data_gb=70,
                voice_minutes=700,
                validity_days=28,
            ),
            _pkg(
                provider="STC",
                plan_name="visitor 26",
                price_sar=31,
                data_gb=6,
                voice_minutes=60,
                validity_days=14,
            ),
            _pkg(
                provider="Mobily",
                plan_name="Visitor 100",
                price_sar=115,
                data_gb=25,
                voice_minutes=400,
                validity_days=14,
            ),
        ]
        ranked = rank_packages(packages, parsed)
        rec = build_recommendation(ranked, parsed)
        self.assertGreaterEqual(rec["voice_minutes"], 500)
        self.assertGreaterEqual(rec["validity_days"], 28)
        self.assertNotIn("Visitor 90", rec["title"])
        mobily_150 = next(row["rank"] for row in ranked if row["plan_name"] == "Visitor 150")
        mobily_90 = next(row["rank"] for row in ranked if row["plan_name"] == "Visitor 90")
        visitor_26 = next(row["rank"] for row in ranked if row["plan_name"] == "visitor 26")
        self.assertLess(mobily_150, mobily_90)
        self.assertGreater(visitor_26, 4)
        rec_value = next(item["assessment"] for item in rec["criteria"] if item["id"] == "value")
        self.assertIn("SAR/min", rec_value)
        self.assertNotIn("SAR/GB", rec_value)
        self.assertTrue(any(item["id"] == "traveller_preference" for item in rec["criteria"]))

    def test_international_minutes_outrank_otherwise_equal_voice_pack(self):
        parsed = parse_request("voice only tourist SIM for 30 days any budget")
        local_only = _pkg(
            provider="Mobily",
            plan_name="Visitor 150",
            price_sar=172.5,
            data_gb=40,
            voice_minutes=600,
            validity_days=30,
            summary="Mobily Visitor 150 from the official visitor plan page. Prices include VAT.",
        )
        with_intl = _pkg(
            provider="Zain",
            plan_name="Visitor 150",
            price_sar=172.5,
            data_gb=40,
            voice_minutes=600,
            validity_days=30,
            summary="Flex minutes can be used for local and international calls.",
        )
        ranked = rank_packages([local_only, with_intl], parsed)
        rec = build_recommendation(ranked, parsed)
        self.assertEqual(rec["provider"], "Zain")
        assessment = next(
            item["assessment"] for item in rec["criteria"] if item["id"] == "traveller_preference"
        )
        self.assertIn("international", assessment.lower())

    def test_data_only_prefers_plan_without_minutes(self):
        parsed = parse_request("data only tourist SIM for 14 days any budget")
        packages = [
            {
                "provider": "STC",
                "title": "visitor 26",
                "price_sar": 31,
                "data_gb": 6,
                "voice_minutes": 60,
                "validity_days": 14,
            },
            {
                "provider": "Zain",
                "title": "Data Plus Unlimited",
                "price_sar": 100,
                "data_gb": 999,
                "voice_minutes": None,
                "validity_days": 7,
            },
        ]
        ranked = rank_packages(packages, parsed)
        rec = build_recommendation(ranked, parsed)
        self.assertEqual(rec["title"], "Data Plus Unlimited")
        self.assertIsNone(rec.get("voice_minutes"))


class SessionTests(unittest.TestCase):
    def test_merges_follow_up_budget(self):
        prior = {"service_type": "data", "trip_days": 7}
        current = parse_request("under 80 SAR")
        self.assertTrue(should_merge_with_previous("under 80 SAR", current, prior))
        merged = merge_parsed(current, prior)
        self.assertEqual(merged.service_type, "data")
        self.assertEqual(merged.trip_days, 7)
        self.assertEqual(merged.budget_sar, 80.0)

    def test_follow_up_replaces_previous_days(self):
        prior = {"service_type": "data", "trip_days": 14}
        current = parse_request("change it to 120 days and any budget is fine")
        self.assertEqual(current.trip_days, 120)
        self.assertTrue(should_merge_with_previous(current.raw, current, prior))
        merged = merge_parsed(current, prior)
        self.assertEqual(merged.service_type, "data")
        self.assertEqual(merged.trip_days, 120)
        self.assertTrue(merged.allow_any_budget)

    def test_new_data_only_sim_does_not_inherit_previous_trip(self):
        prior = {"service_type": "voice", "trip_days": 14, "allow_any_budget": True}
        current = parse_request("data only sim")
        self.assertEqual(current.service_type, "data")
        self.assertIsNone(current.trip_days)
        self.assertFalse(should_merge_with_previous(current.raw, current, prior))


class OfficialParseTests(unittest.TestCase):
    def test_parses_stc_visitor_cards(self):
        html = """
        <div data-product-name="visitor 26" data-product-price="31 §">
          <p class="productCardData product-card-featureTitle prepaid-card">6 GB</p>
          <p class="productCardData product-card-descTitle">1 hour</p>
          <p>package validity: 2 Weeks</p>
        </div>
        <div data-product-name="visitor 165" data-product-price="190 §">
          <p class="productCardData product-card-featureTitle prepaid-card">100 GB</p>
          <p class="productCardData product-card-descTitle">10 hours flex</p>
          <p>package validity: 4 weeks</p>
        </div>
        """
        packages = _parse_stc(html, "https://www.stc.com.sa/en/personal/mobile/packages/sawa-ziyara.html", "now")
        self.assertEqual(len(packages), 2)
        by_name = {item["plan_name"]: item for item in packages}
        self.assertEqual(by_name["visitor 26"]["price_sar"], 31.0)
        self.assertEqual(by_name["visitor 26"]["data_gb"], 6.0)
        self.assertEqual(by_name["visitor 26"]["voice_minutes"], 60)
        self.assertEqual(by_name["visitor 26"]["validity_days"], 14)
        self.assertEqual(by_name["visitor 165"]["data_gb"], 100.0)
        self.assertEqual(by_name["visitor 165"]["price_sar"], 190.0)
        self.assertEqual(by_name["visitor 165"]["validity_days"], 28)
        self.assertIn("stc.com.sa", packages[0]["source_url"])

    def test_parses_mobily_visitor_plan_page(self):
        html = """
        <div>Back Visitor 30 Φ 34.5 /14 Days VAT Incl. Subscribe
        Minutes 60 More Details Data 5GB More Details</div>
        """
        packages = _parse_mobily(
            html,
            "https://www.mobily.com.sa/web/en/personal/mobile/visitor/vistor-plans/visitors-30/visitors-30",
            "now",
        )
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]["provider"], "Mobily")
        self.assertEqual(packages[0]["price_sar"], 34.5)
        self.assertEqual(packages[0]["data_gb"], 5.0)
        self.assertEqual(packages[0]["voice_minutes"], 60)
        self.assertEqual(packages[0]["validity_days"], 14)

    def test_parses_zain_official_json(self):
        payload = {
            "dataPackages": [
                {
                    "key": "visitor",
                    "items": [
                        {
                            "active": "1",
                            "unlimited_data": "0",
                            "title": "<h4>Visitor 35</h4>",
                            "price": 40.25,
                            "redirect_url": "https://sim.sa.zain.com/visitor",
                            "description": "Visitor package",
                            "property_benefits": [
                                {"title": "Flex MINUTES", "service_property_subtitle": "70"},
                                {"title": "Internet", "service_property_subtitle": "5 GB"},
                                {"title": "Validity", "service_property_subtitle": "14 Days"},
                            ],
                        }
                    ],
                }
            ]
        }
        packages = _parse_zain_json(json.dumps(payload), "https://sa.zain.com/en/packagesdata/b2c-tabs/x", "now")
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]["provider"], "Zain")
        self.assertEqual(packages[0]["plan_name"], "Visitor 35")
        self.assertEqual(packages[0]["price_sar"], 40.25)
        self.assertEqual(packages[0]["data_gb"], 5.0)
        self.assertEqual(packages[0]["voice_minutes"], 70)
        self.assertEqual(packages[0]["validity_days"], 14)

    def test_budget_filter_keeps_official_providers_only(self):
        parsed = parse_request("data and voice SIM for 7 days under 50 SAR")
        packages = filter_packages(
            [
                _pkg(provider="STC", price_sar=31, data_gb=6),
                _pkg(provider="Mobily", plan_name="Visitor 90", price_sar=103.5, data_gb=55),
                _pkg(provider="Airalo", plan_name="eSIM", price_sar=20, data_gb=5, source_url="https://www.airalo.com"),
            ],
            parsed,
        )
        self.assertEqual([item["provider"] for item in packages], ["STC"])

    def test_data_only_hides_combo_plans_when_a_data_pack_exists(self):
        parsed = parse_request("data only tourist SIM for 14 days any budget")
        packages = filter_packages(
            [
                _pkg(provider="STC", plan_name="visitor 26", voice_minutes=60, data_gb=6),
                _pkg(
                    provider="Zain",
                    plan_name="Data Plus Unlimited",
                    data_gb=999,
                    voice_minutes=None,
                    price_sar=100,
                    validity_days=7,
                ),
            ],
            parsed,
        )
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]["plan_name"], "Data Plus Unlimited")
        self.assertIsNone(packages[0].get("voice_minutes"))


class AdvisorTests(unittest.TestCase):
    def test_incomplete_data_only_sim_asks_trip_length(self):
        result = compare_sim_packages(
            "data only sim",
            previous_filters={
                "service_type": "voice",
                "trip_days": 14,
                "allow_any_budget": True,
            },
        )
        self.assertTrue(result.get("needs_clarification"))
        self.assertEqual(result.get("field"), "trip_days")
        self.assertFalse(result.get("packages"))

    def test_off_topic_uses_fixed_message(self):
        result = compare_sim_packages("What is the weather in Riyadh?")
        self.assertTrue(result["off_topic"])
        self.assertEqual(result["message"], OFF_TOPIC_REPLY)

    def test_ranks_from_official_catalog_and_adds_accuracy_notice(self):
        catalog = [
            _pkg(),
            _pkg(
                provider="Mobily",
                plan_name="Old promo",
                title="Old Mobily promo discontinued",
                summary="This package is discontinued and no longer available",
                price_sar=20,
                data_gb=50,
            ),
        ]
        result = compare_sim_packages(
            "data and voice SIM for 7 days under 100 SAR",
            catalog=catalog,
        )
        self.assertGreaterEqual(result["total_results"], 1)
        self.assertEqual(result["packages"][0]["provider"], "STC")
        self.assertEqual(result["accuracy_notice"], ACCURACY_NOTICE)
        self.assertEqual(result["source"], "official_operator_websites")
        self.assertIsNotNone(result["recommendation"])
        self.assertEqual(result["recommendation"]["provider"], "STC")
        self.assertEqual(len(result["recommendation"]["criteria"]), len(RECOMMENDATION_CRITERIA))
        self.assertIn(
            "traveller_preference",
            {item["id"] for item in result["recommendation"]["criteria"]},
        )
        titles = " ".join(item["title"] for item in result["packages"])
        self.assertNotIn("discontinued", titles.lower())
        self.assertNotIn("Unknown", titles)
        self.assertIn("STC", result["packages"][0]["title"])

    def test_lists_at_most_ten_packages_with_comparison_table(self):
        catalog = [
            _pkg(
                plan_name=f"visitor {index}",
                title=f"STC visitor {index}",
                price_sar=30 + index,
                data_gb=5 + index,
                voice_minutes=60 + index,
            )
            for index in range(12)
        ]
        result = compare_sim_packages(
            "data and voice SIM for 14 days any budget",
            catalog=catalog,
        )
        self.assertEqual(result["total_matched"], 12)
        self.assertEqual(len(result["packages"]), MAX_LISTED_PACKAGES)
        self.assertEqual(len(result["comparison"]), MAX_LISTED_PACKAGES)
        self.assertEqual([row["rank"] for row in result["comparison"]], list(range(1, 11)))
        self.assertEqual(result["comparison"][0]["provider"], result["packages"][0]["provider"])
        self.assertIn("value", result["comparison"][0])

    def test_follow_up_days_replace_session_filters(self):
        catalog = [
            _pkg(
                provider="Mobily",
                plan_name="Visitor 150",
                title="Mobily Visitor 150",
                price_sar=172.5,
                data_gb=40,
                validity_days=30,
            )
        ]
        result = compare_sim_packages(
            "change it to 120 days and any budget is fine",
            previous_filters={"service_type": "data", "trip_days": 14},
            catalog=catalog,
        )
        self.assertFalse(result.get("off_topic"))
        self.assertEqual(result["interpreted_as"]["trip_days"], 120)
        self.assertEqual(result["interpreted_as"]["service_type"], "data")
        self.assertTrue(result["interpreted_as"].get("allow_any_budget"))

    def test_maximum_data_follow_up_keeps_session_and_sorts(self):
        catalog = [
            _pkg(provider="STC", plan_name="visitor 26", price_sar=31, data_gb=6),
            _pkg(provider="Zain", plan_name="Visitor 150", price_sar=172.5, data_gb=70, validity_days=28),
        ]
        result = compare_sim_packages(
            "provide me the sim with maximum data",
            previous_filters={"service_type": "data", "trip_days": 30, "allow_any_budget": True},
            catalog=catalog,
        )
        self.assertEqual(result["interpreted_as"]["sort_by"], "data")
        self.assertEqual(result["interpreted_as"]["trip_days"], 30)
        self.assertEqual(result["recommendation"]["provider"], "Zain")
        self.assertEqual(result["recommendation"]["data_gb"], 70.0)
        self.assertIn("70 GB", result["recommendation"]["title"])


if __name__ == "__main__":
    unittest.main()
