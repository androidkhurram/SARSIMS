"""Parse a natural-language SIM request into structured filters."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedRequest:
    service_type: str | None = None  # data | voice | both
    trip_days: int | None = None
    budget_sar: float | None = None
    allow_any_budget: bool = False
    providers: list[str] = field(default_factory=list)
    allow_any_provider: bool = False
    sim_form: str | None = None  # esim | physical | either
    sort_by: str | None = None  # price | data | value
    raw: str = ""
    error: str | None = None

    def interpreted_as(self) -> dict:
        data: dict = {}
        if self.service_type:
            data["service_type"] = self.service_type
        if self.trip_days is not None:
            data["trip_days"] = self.trip_days
        if self.budget_sar is not None:
            data["budget_sar"] = self.budget_sar
        if self.allow_any_budget:
            data["allow_any_budget"] = True
        if self.providers:
            data["providers"] = list(self.providers)
        if self.allow_any_provider:
            data["allow_any_provider"] = True
        if self.sim_form:
            data["sim_form"] = self.sim_form
        if self.sort_by:
            data["sort_by"] = self.sort_by
        return data


_PROVIDER_MAP = {
    "stc": "STC",
    "mobily": "Mobily",
    "zain": "Zain",
    "lebara": "Lebara",
    "virgin": "Virgin Mobile",
    "virgin mobile": "Virgin Mobile",
}


def parse_request(request: str) -> ParsedRequest:
    text = (request or "").strip()
    parsed = ParsedRequest(raw=text)
    if not text:
        parsed.error = "Empty request."
        return parsed

    lower = text.lower()

    if re.search(r"\b(?:data\s*\+?\s*voice|voice\s*\+?\s*data|both|combo|combined)\b", lower):
        parsed.service_type = "both"
    elif re.search(r"\b(?:data[- ]?only|only data|internet|gb|mb)\b", lower) and not re.search(
        r"\b(?:call|voice|minute)\b", lower
    ):
        parsed.service_type = "data"
    elif re.search(r"\b(?:voice[- ]?only|only voice|calls?|minutes?)\b", lower) and not re.search(
        r"\b(?:data|internet|gb)\b", lower
    ):
        parsed.service_type = "voice"
    elif re.search(r"\bdata\b", lower) and re.search(r"\b(?:voice|call|minute)\b", lower):
        parsed.service_type = "both"
    elif re.search(r"\bdata\b", lower):
        parsed.service_type = "data"
    elif re.search(r"\b(?:voice|call|minute)\b", lower):
        parsed.service_type = "voice"

    days = _trip_days(lower)
    if days is not None:
        parsed.trip_days = days

    if re.search(r"\bany\s+budget\b", lower) or re.search(r"\bno\s+budget\b", lower):
        parsed.allow_any_budget = True
    else:
        budget = _budget_sar(lower)
        if budget is not None:
            parsed.budget_sar = budget

    providers = []
    for key, name in _PROVIDER_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            if name not in providers:
                providers.append(name)
    if providers:
        parsed.providers = providers
    if re.search(r"\bany\s+provider\b", lower) or re.search(r"\bany\s+operator\b", lower):
        parsed.allow_any_provider = True
        parsed.providers = []

    if re.search(r"\besim\b|\be-sim\b", lower):
        parsed.sim_form = "esim"
    elif re.search(r"\bphysical\b|\bplastic\s+sim\b|\bsim\s+card\b", lower):
        parsed.sim_form = "physical"
    elif re.search(r"\beither\b|\bno preference\b", lower) and re.search(r"\bsim\b", lower):
        parsed.sim_form = "either"

    if re.search(r"\bcheapest\b|\blowest\s+price\b|\bsort\s+by\s+price\b", lower):
        parsed.sort_by = "price"
    elif re.search(
        r"\b(?:most|max(?:imum)?|highest|largest|more)\s+data\b|"
        r"\bmaximum\s+data\b|\bsort\s+by\s+data\b|\bmost\s+gb\b|"
        r"\b(?:unlimited\s+data|biggest\s+(?:data\s+)?pack)",
        lower,
    ):
        parsed.sort_by = "data"
    elif re.search(r"\bbest\s+value\b|\bvalue\s+for\s+money\b", lower):
        parsed.sort_by = "value"

    return parsed


def _trip_days(lower: str) -> int | None:
    override = re.search(
        r"(?:change(?:\s+it)?|update|switch|make\s+it|set(?:\s+it)?|instead)\s+"
        r"(?:(?:it|that|this)\s+)?(?:to\s+)?(\d+)\s*(?:day|days)?",
        lower,
    )
    if override:
        return int(override.group(1))
    numbered = list(re.finditer(r"\b(\d+)\s*(?:day|days|night|nights)\b", lower))
    if numbered:
        return int(numbered[-1].group(1))
    match = re.search(r"\b(?:for|about|around)\s+(\d+)\s*(?:d)\b", lower)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)\s*-\s*day\b", lower)
    if match:
        return int(match.group(1))
    if re.search(r"\b(?:one|a)\s+week\b", lower) or re.search(r"\b7\s*days?\b", lower):
        return 7
    if re.search(r"\b(?:two)\s+weeks?\b", lower):
        return 14
    if re.search(r"\b(?:a\s+)?month\b", lower) or re.search(r"\b30\s*days?\b", lower):
        return 30
    if re.search(r"\bweekend\b", lower):
        return 3
    return None


def _budget_sar(lower: str) -> float | None:
    match = re.search(
        r"(?:under|below|max|up to|budget(?:\s+of)?|less than)\s*"
        r"(?:sar|sr|riyal[s]?)?\s*([\d,]+(?:\.\d+)?)",
        lower,
    )
    if match:
        return float(match.group(1).replace(",", ""))
    match = re.search(
        r"\b([\d,]+(?:\.\d+)?)\s*(?:sar|sr|riyal[s]?)\b",
        lower,
    )
    if match:
        return float(match.group(1).replace(",", ""))
    return None
