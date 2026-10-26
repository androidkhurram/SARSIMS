"""Shared product strings and provider vocabulary."""

from __future__ import annotations

OFF_TOPIC_REPLY = (
    "This specific information is not provided by any service provider."
)

MAX_LISTED_PACKAGES = 10

ACCURACY_NOTICE = (
    "Prices and promos may change. These results reflect the latest check of "
    "official KSA operator websites (STC, Mobily, Zain, Lebara, Virgin Mobile) "
    "and are not a guarantee of real-time promo accuracy without a fresh "
    "refresh/source check at purchase time."
)

PROVIDERS = (
    "STC",
    "Mobily",
    "Zain",
    "Lebara",
    "Virgin Mobile",
)

PROVIDER_DOMAINS = (
    ("stc.com.sa", "STC"),
    ("mobily.com.sa", "Mobily"),
    ("sa.zain.com", "Zain"),
    ("zain.com", "Zain"),
    ("virginmobile.sa", "Virgin Mobile"),
    ("lebara.sa", "Lebara"),
)

OFFICIAL_OPERATOR_HOSTS = (
    "stc.com.sa",
    "mobily.com.sa",
    "sa.zain.com",
    "zain.com",
    "virginmobile.sa",
    "lebara.sa",
)

JUNK_MARKERS = (
    "ai agent",
    "ai workspace",
    "build, distribute",
    "metrologia",
    "sim members",
    "sim structure",
    "sim international",
    "sim usa",
    "you're in the usa",
    "under armour",
    "homework",
)

RECOMMENDATION_CRITERIA = (
    {
        "id": "service_fit",
        "name": "Service fit",
        "definition": "Has the requested data, voice, or both.",
    },
    {
        "id": "trip_fit",
        "name": "Trip length fit",
        "definition": "Validity is closest to the stay, with little unused time.",
    },
    {
        "id": "value",
        "name": "Value for money",
        "definition": "Lower SAR per GB, or lower SAR per minute for voice, within budget.",
    },
    {
        "id": "traveller_preference",
        "name": "Typical international traveller preference",
        "definition": (
            "Visitor packs with enough data for maps and messaging, minutes to call "
            "home, and international calling when the operator lists it."
        ),
    },
    {
        "id": "known_provider",
        "name": "Known provider",
        "definition": "Official KSA operator: STC, Mobily, Zain, Lebara, or Virgin Mobile.",
    },
    {
        "id": "source_quality",
        "name": "Source quality",
        "definition": "Facts taken from the operator's official website, not aggregators or search snippets.",
    },
)

DISCONTINUED_MARKERS = (
    "discontinued",
    "no longer available",
    "no longer offered",
    "expired",
    "legacy plan",
    "was available",
    "previously offered",
    "old promo",
)
