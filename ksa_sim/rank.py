"""Rank extracted SIM packages for travellers and pick a recommended plan."""

from __future__ import annotations

from ksa_sim.constants import OFFICIAL_OPERATOR_HOSTS, RECOMMENDATION_CRITERIA
from ksa_sim.parse import ParsedRequest


def rank_packages(packages: list[dict], parsed: ParsedRequest) -> list[dict]:
    sort_by = parsed.sort_by
    scored = []
    for item in packages:
        row = dict(item)
        row["rank_score"] = _score(row, parsed, sort_by)
        row["rank_reason"] = _reason(row, parsed, sort_by)
        scored.append(row)

    if sort_by == "price":
        scored.sort(
            key=lambda row: (
                row.get("price_sar") is None,
                row.get("price_sar") if row.get("price_sar") is not None else 10**9,
                -row["rank_score"],
            )
        )
    elif sort_by == "data":
        scored.sort(
            key=lambda row: (
                row.get("price_sar") is None or row.get("data_gb") is None,
                row.get("data_gb") is None,
                row.get("price_sar") is None,
                -(row.get("data_gb") or 0),
                -row["rank_score"],
            )
        )
    elif parsed.service_type == "voice":
        scored.sort(
            key=lambda row: (
                row.get("voice_minutes") is None,
                row.get("price_sar") is None,
                -row["rank_score"],
            )
        )
    elif parsed.service_type == "data":
        scored.sort(
            key=lambda row: (
                row.get("data_gb") is None,
                row.get("price_sar") is None,
                row.get("voice_minutes") is not None,
                -row["rank_score"],
            )
        )
    else:
        scored.sort(
            key=lambda row: (
                row.get("price_sar") is None,
                -row["rank_score"],
            )
        )

    both = [
        row
        for row in scored
        if row.get("price_sar") is not None and row.get("data_gb") is not None
    ]
    priced = [row for row in scored if row.get("price_sar") is not None]
    with_data = [row for row in scored if row.get("data_gb") is not None]
    voice_priced = [
        row
        for row in scored
        if row.get("voice_minutes") is not None and row.get("price_sar") is not None
    ]
    with_voice = [row for row in scored if row.get("voice_minutes") is not None]
    if sort_by == "data":
        pool = both or with_data or scored
        pick = max(
            pool,
            key=lambda row: (
                row.get("price_sar") is not None and row.get("data_gb") is not None,
                row.get("data_gb") or 0,
                row.get("rank_score") or 0,
            ),
        )
    elif parsed.service_type == "voice":
        pool = voice_priced or with_voice or priced or scored
        pick = pool[0] if pool else None
    elif parsed.service_type == "data":
        data_only_priced = [
            row
            for row in scored
            if row.get("data_gb") is not None
            and row.get("price_sar") is not None
            and not row.get("voice_minutes")
        ]
        data_priced = [
            row
            for row in scored
            if row.get("data_gb") is not None and row.get("price_sar") is not None
        ]
        pool = data_only_priced or data_priced or with_data or scored
        pick = pool[0] if pool else None
    else:
        pool = both or priced or scored
        pick = pool[0] if pool else None
    for index, row in enumerate(scored, start=1):
        row["rank"] = index
        row["recommended"] = pick is not None and row is pick
    return scored


def build_recommendation(ranked: list[dict], parsed: ParsedRequest) -> dict | None:
    if not ranked:
        return None
    best = next((row for row in ranked if row.get("recommended")), ranked[0])
    criteria = []
    for item in RECOMMENDATION_CRITERIA:
        criteria.append(
            {
                **item,
                "assessment": _assess_criterion(item["id"], best, parsed),
            }
        )
    return {
        "provider": best.get("provider"),
        "title": best.get("title"),
        "rank": best.get("rank"),
        "summary": _recommendation_summary(best, parsed),
        "criteria": criteria,
        "source_url": best.get("source_url"),
        "price_sar": best.get("price_sar"),
        "data_gb": best.get("data_gb"),
        "voice_minutes": best.get("voice_minutes"),
        "validity_days": best.get("validity_days"),
    }


def build_comparison(ranked: list[dict], parsed: ParsedRequest) -> list[dict]:
    rows = []
    for row in ranked:
        price = row.get("price_sar")
        data_gb = row.get("data_gb")
        minutes = row.get("voice_minutes")
        if parsed.service_type == "voice":
            ratio = _sar_per_min(row)
            value = f"{ratio} SAR/min" if ratio is not None else "—"
        else:
            ratio = _sar_per_gb(row)
            value = f"{ratio} SAR/GB" if ratio is not None else "—"
            if parsed.service_type == "both":
                min_ratio = _sar_per_min(row)
                if min_ratio is not None:
                    value = f"{value}; {min_ratio} SAR/min"
        plan = row.get("plan_name") or row.get("title") or "Package"
        rows.append(
            {
                "rank": row.get("rank"),
                "provider": row.get("provider") or "Unknown",
                "plan": plan,
                "price_sar": price,
                "data_gb": data_gb,
                "voice_minutes": minutes,
                "validity_days": row.get("validity_days"),
                "value": value,
                "international": "Listed" if _has_international_calls(row) else "Not listed",
                "recommended": bool(row.get("recommended")),
            }
        )
    return rows


def _score(row: dict, parsed: ParsedRequest, sort_by: str | None) -> float:
    score = (
        _service_fit_score(row, parsed)
        + _trip_fit_score(row, parsed)
        + _value_score(row, parsed)
        + _traveller_preference_score(row, parsed)
        + _provider_score(row)
        + _source_score(row)
    )

    price = row.get("price_sar")
    data_gb = row.get("data_gb")
    minutes = row.get("voice_minutes")
    if sort_by == "price" and price is not None:
        score += 5
    if sort_by == "data" and data_gb is not None:
        score += 5

    if price is None and data_gb is None and minutes is None:
        score -= 20
    title = (row.get("title") or "").lower()
    summary = (row.get("summary") or "").lower()
    raw = (parsed.raw or "").lower()
    if any(token in title for token in ("home", "login", "app -", "group")):
        score -= 12
    if any(token in f"{title} {summary}" for token in ("hajj", "umrah")) and not any(
        token in raw for token in ("hajj", "umrah")
    ):
        score -= 18
    return round(score, 3)


def _service_fit_score(row: dict, parsed: ParsedRequest) -> float:
    data_gb = row.get("data_gb")
    minutes = row.get("voice_minutes")
    service = parsed.service_type
    if service == "voice":
        if not minutes:
            return -20
        if minutes >= 9999:
            return 40
        return 20 + 20 * min(minutes, 600) / 600
    if service == "data":
        if not data_gb:
            return -20
        amount = 12 + 18 * min(data_gb, 100) / 100
        if not minutes:
            amount += 10
        else:
            amount -= 8
        return amount
    score = 0.0
    if data_gb:
        score += 12 + 8 * min(data_gb, 100) / 100
    if minutes:
        score += 12 + 8 * min(minutes, 600) / 600
    if data_gb and minutes:
        score += 8
    if not data_gb and not minutes:
        score -= 20
    return score


def _trip_fit_score(row: dict, parsed: ParsedRequest) -> float:
    validity = row.get("validity_days")
    trip = parsed.trip_days
    if not trip or not validity:
        return 8
    if validity >= trip:
        unused = validity - trip
        return 30 - 20 * min(unused, trip) / trip
    return 30 * (validity / trip) ** 2


def _value_score(row: dict, parsed: ParsedRequest) -> float:
    price = row.get("price_sar")
    if price is None:
        return 0
    if parsed.budget_sar is not None:
        budget_bit = 3.0 if price <= parsed.budget_sar else -5.0
    else:
        budget_bit = 0.0

    service = parsed.service_type
    if service == "voice":
        minutes = row.get("voice_minutes")
        if not minutes:
            return budget_bit
        if minutes >= 9999:
            return budget_bit + 20
        sar_per_min = price / minutes
        return budget_bit + max(0.0, 20.0 * (1.0 - sar_per_min / 0.80))
    if service == "data":
        data_gb = row.get("data_gb")
        if not data_gb:
            return budget_bit
        sar_per_gb = price / data_gb
        return budget_bit + max(0.0, 20.0 * (1.0 - sar_per_gb / 6.0))

    data_part = 0.0
    min_part = 0.0
    data_gb = row.get("data_gb")
    minutes = row.get("voice_minutes")
    if data_gb:
        data_part = 10 * max(0.0, 1.0 - (price / data_gb) / 6.0)
    if minutes:
        min_part = 10 * max(0.0, 1.0 - (price / minutes) / 0.80)
    return budget_bit + data_part + min_part


def _traveller_preference_score(row: dict, parsed: ParsedRequest) -> float:
    score = 0.0
    if _is_visitor_pack(row):
        score += 2
    if _has_international_calls(row):
        score += 6
    data_gb = row.get("data_gb") or 0
    if parsed.service_type in {None, "voice", "both"}:
        if data_gb >= 999:
            score += 5
        elif data_gb:
            score += 5 * min(data_gb, 40) / 40
        minutes = row.get("voice_minutes") or 0
        if minutes >= 200:
            score += 2
    elif data_gb >= 10:
        score += 2
    if parsed.sim_form == "esim" and row.get("sim_form") == "esim":
        score += 2
    text = _package_text(row)
    if any(token in text for token in ("postpaid", "monthly bill")):
        score -= 4
    return min(score, 15)


def _package_text(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("title", "plan_name", "summary", "source_title")
    ).lower()


def _is_visitor_pack(row: dict) -> bool:
    text = _package_text(row)
    return any(token in text for token in ("visitor", "tourist", "prepaid", "sawa ziyara", "sawa-ziyara"))


def _has_international_calls(row: dict) -> bool:
    text = _package_text(row)
    return any(
        token in text
        for token in (
            "international",
            "flex minutes",
            "idd",
            "call abroad",
            "calls abroad",
            "local and international",
        )
    )


def _provider_score(row: dict) -> float:
    if row.get("provider") and row["provider"] != "Unknown":
        return 5
    return 0


def _source_score(row: dict) -> float:
    url = (row.get("source_url") or "").lower()
    if not url:
        return 0
    if any(host in url for host in OFFICIAL_OPERATOR_HOSTS):
        return 5
    if any(
        host in url
        for host in ("facebook.com", "reddit.com", "pinterest.", "quora.com", "tiktok.com", "youtube.com")
    ):
        return -8
    return 1


def _reason(row: dict, parsed: ParsedRequest, sort_by: str | None) -> str:
    bits = []
    if row.get("price_sar") is not None:
        bits.append(f"{row['price_sar']} SAR")
    if parsed.service_type == "voice":
        if row.get("voice_minutes") is not None:
            bits.append(f"{row['voice_minutes']} min")
        ratio = _sar_per_min(row)
        if ratio is not None:
            bits.append(f"{ratio} SAR/min")
    else:
        if row.get("data_gb") is not None:
            bits.append(f"{row['data_gb']} GB")
        if row.get("voice_minutes") is not None:
            bits.append(f"{row['voice_minutes']} min")
        ratio = _sar_per_gb(row)
        if ratio is not None and parsed.service_type != "voice":
            bits.append(f"{ratio} SAR/GB")
    if row.get("validity_days") is not None:
        bits.append(f"{row['validity_days']} days")
    if sort_by == "price":
        bits.append("sorted by price")
    elif sort_by == "data":
        bits.append("sorted by data")
    else:
        bits.append("ranked by service fit, trip fit, value, traveller preference")
    if parsed.trip_days:
        bits.append(f"trip ~{parsed.trip_days}d")
    return " · ".join(bits) if bits else "matched from official operator websites"


def _sar_per_gb(row: dict) -> float | None:
    price = row.get("price_sar")
    data_gb = row.get("data_gb")
    if price is None or not data_gb or data_gb <= 0:
        return None
    return round(price / data_gb, 2)


def _sar_per_min(row: dict) -> float | None:
    price = row.get("price_sar")
    minutes = row.get("voice_minutes")
    if price is None or not minutes or minutes <= 0:
        return None
    return round(price / minutes, 2)


def _assess_criterion(criterion_id: str, row: dict, parsed: ParsedRequest) -> str:
    service = parsed.service_type
    if criterion_id == "service_fit":
        has_data = row.get("data_gb") is not None
        has_voice = row.get("voice_minutes") is not None
        if service == "data" and has_data:
            amount = "unlimited data" if row.get("data_gb", 0) >= 999 else f"{row['data_gb']:g} GB"
            return f"Includes a data allowance of {amount}."
        if service == "voice" and has_voice:
            minutes = row["voice_minutes"]
            if minutes >= 9999:
                return "Includes unlimited voice minutes."
            return f"Includes {minutes:g} voice minutes."
        if service == "both" and has_data and has_voice:
            return "Includes both data and voice."
        if service == "both" and has_data:
            return "Has data; voice minutes were not listed in the source snippet."
        if has_data or has_voice:
            return "Partial match from the source snippet."
        return "Plan details were incomplete in the source snippet."
    if criterion_id == "trip_fit":
        validity = row.get("validity_days")
        if parsed.trip_days and validity:
            gap = abs(validity - parsed.trip_days)
            if gap == 0:
                return f"Validity matches the {parsed.trip_days}-day stay."
            return f"Validity is {validity} days vs a {parsed.trip_days}-day stay."
        if validity:
            return f"Listed validity is {validity} days."
        return "Validity was not listed in the source snippet."
    if criterion_id == "value":
        bits = []
        if row.get("price_sar") is not None:
            bits.append(f"{row['price_sar']} SAR")
        if service == "voice":
            if row.get("voice_minutes") is not None:
                bits.append(f"{row['voice_minutes']:g} min")
            ratio = _sar_per_min(row)
            if ratio is not None:
                bits.append(f"{ratio} SAR/min")
        else:
            ratio = _sar_per_gb(row)
            if ratio is not None:
                bits.append(f"{ratio} SAR/GB")
            if service == "both":
                min_ratio = _sar_per_min(row)
                if min_ratio is not None:
                    bits.append(f"{min_ratio} SAR/min")
        if parsed.budget_sar is not None and row.get("price_sar") is not None:
            if row["price_sar"] <= parsed.budget_sar:
                bits.append("within budget")
            else:
                bits.append("above budget")
        return ", ".join(bits) if bits else "Price was not listed in the source snippet."
    if criterion_id == "traveller_preference":
        bits = []
        if _is_visitor_pack(row):
            bits.append("visitor/tourist pack")
        if _has_international_calls(row):
            bits.append("operator lists international / flex minutes")
        else:
            bits.append("international calling is not listed on the operator page")
        data_gb = row.get("data_gb")
        if data_gb:
            data_text = "unlimited data" if data_gb >= 999 else f"{data_gb:g} GB"
            bits.append(f"{data_text} for maps and messaging")
        minutes = row.get("voice_minutes")
        if minutes and parsed.service_type != "data":
            if minutes >= 9999:
                bits.append("unlimited minutes to call home")
            elif minutes >= 200:
                bits.append(f"{minutes:g} min is enough for typical calls home")
            else:
                bits.append(f"only {minutes:g} min listed for calls")
        return "; ".join(bits) + "."
    if criterion_id == "known_provider":
        provider = row.get("provider") or "Unknown"
        return f"Identified as {provider}."
    url = (row.get("source_url") or "").lower()
    if any(host in url for host in OFFICIAL_OPERATOR_HOSTS):
        return "Source is the operator's official website."
    if url:
        return "Source URL was not an official KSA operator domain."
    return "No source URL was extracted."


def _recommendation_summary(row: dict, parsed: ParsedRequest) -> str:
    title = row.get("title") or f"{row.get('provider', 'This package')} tourist SIM"
    bits = [f"Recommended: {title}."]
    if parsed.service_type == "voice":
        if row.get("voice_minutes") is not None:
            minutes = row["voice_minutes"]
            voice_text = "unlimited minutes" if minutes >= 9999 else f"{minutes:g} min"
            bits.append(f"Listed voice: {voice_text}.")
    elif row.get("data_gb") is not None:
        data_text = "unlimited data" if row["data_gb"] >= 999 else f"{row['data_gb']:g} GB"
        bits.append(f"Listed data: {data_text}.")
    elif parsed.sort_by == "data":
        bits.append("The source snippet did not list a GB amount — open the source to confirm data.")
    service = parsed.service_type or "your"
    bits.append(f"It ranked first for a {service} plan")
    if parsed.trip_days:
        bits[-1] += f" on a {parsed.trip_days}-day trip"
    if parsed.sort_by == "data":
        bits[-1] += ", sorted for maximum listed data"
    elif parsed.sort_by == "price":
        bits[-1] += ", sorted for lowest listed price"
    bits[-1] += (
        " using service fit, trip-length fit, value for money, typical international "
        "traveller preference, known provider, and source quality."
    )
    if parsed.budget_sar is not None and row.get("price_sar") is not None:
        if row["price_sar"] <= parsed.budget_sar:
            bits.append(f"Listed price {row['price_sar']} SAR is within the {parsed.budget_sar:g} SAR budget.")
    bits.append("Confirm the live price on the operator site before buying.")
    return " ".join(bits)
