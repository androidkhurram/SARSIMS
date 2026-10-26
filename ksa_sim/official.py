"""Load current KSA tourist SIM packages from official operator websites only."""

from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

from ksa_sim.constants import DISCONTINUED_MARKERS, PROVIDERS
from ksa_sim.http import ssl_context
from ksa_sim.parse import ParsedRequest

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CACHE_TTL_SECONDS = 300

STC_URL = "https://www.stc.com.sa/en/personal/mobile/packages/sawa-ziyara.html"
ZAIN_JSON_URL = (
    "https://sa.zain.com/en/packagesdata/b2c-tabs/"
    "consumer-visitor,consumer-visitor-plus/en/consumer"
)
ZAIN_PAGE_URL = "https://sa.zain.com/en/mobile/visitor/visitor-40"
LEBARA_URL = "https://lebara.sa/en/package_category/prepaid"
VIRGIN_URL = "https://virginmobile.sa/en/"
MOBILY_PLAN_URLS = (
    "https://www.mobily.com.sa/web/en/personal/mobile/visitor/vistor-plans/visitors-30/visitors-30",
    "https://www.mobily.com.sa/web/en/personal/mobile/visitor/vistor-plans/visitors-50/visitors-50",
    "https://www.mobily.com.sa/web/en/personal/mobile/visitor/vistor-plans/visitors-65/visitors-65",
    "https://www.mobily.com.sa/web/en/personal/mobile/visitor/vistor-plans/visitors-90/visitors-90",
    "https://www.mobily.com.sa/web/en/personal/mobile/visitor/vistor-plans/visitors-100/visitors-100",
    "https://www.mobily.com.sa/web/en/personal/mobile/visitor/vistor-plans/visitors-150/visitors-150",
)

Fetcher = Callable[[str], str]

_cache_lock = threading.Lock()
_catalog_cache: dict = {"at": 0.0, "packages": []}


class FetchError(Exception):
    """Official operator pages could not be loaded."""


def fetch_url(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise FetchError(f"Official source returned HTTP {exc.code} for {url}.") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"Could not reach official source {url}.") from exc


def fetch_official_packages(
    parsed: ParsedRequest,
    *,
    fetcher: Fetcher | None = None,
    use_cache: bool = True,
) -> list[dict]:
    catalog = load_official_catalog(fetcher=fetcher, use_cache=use_cache)
    return filter_packages(catalog, parsed)


def load_official_catalog(
    *,
    fetcher: Fetcher | None = None,
    use_cache: bool = True,
) -> list[dict]:
    if use_cache:
        with _cache_lock:
            age = time.time() - _catalog_cache["at"]
            if _catalog_cache["packages"] and age < CACHE_TTL_SECONDS:
                return [dict(row) for row in _catalog_cache["packages"]]

    loader = fetcher or fetch_url
    checked_at = datetime.now(timezone.utc).isoformat()
    jobs: list[tuple[str, str, Callable[[str, str, str], list[dict]]]] = [
        ("STC", STC_URL, _parse_stc),
        ("Zain", ZAIN_JSON_URL, _parse_zain_json),
        ("Lebara", LEBARA_URL, _parse_lebara),
        ("Virgin Mobile", VIRGIN_URL, _parse_virgin),
    ]
    for url in MOBILY_PLAN_URLS:
        jobs.append(("Mobily", url, _parse_mobily))

    packages: list[dict] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_safe_fetch, loader, url): (provider, url, parser) for provider, url, parser in jobs}
        for future in as_completed(futures):
            provider, url, parser = futures[future]
            try:
                body = future.result()
                packages.extend(parser(body, url, checked_at))
            except Exception as exc:
                logger.info("Official source failed (%s): %s", provider, exc)
                errors.append(f"{provider}: {exc}")

    packages = _dedupe(packages)
    if not packages:
        detail = "; ".join(errors) if errors else "no packages parsed"
        raise FetchError(
            "No current visitor packages could be read from official operator websites. "
            f"({detail})"
        )

    if use_cache:
        with _cache_lock:
            _catalog_cache["at"] = time.time()
            _catalog_cache["packages"] = [dict(row) for row in packages]
    return packages


def filter_packages(packages: list[dict], parsed: ParsedRequest) -> list[dict]:
    filtered: list[dict] = []
    seen: set[str] = set()
    for package in packages:
        if _is_discontinued(package):
            continue
        provider = package.get("provider")
        if provider not in PROVIDERS:
            continue
        if parsed.providers and provider not in parsed.providers:
            continue
        if parsed.budget_sar is not None and package.get("price_sar") is not None:
            if package["price_sar"] > parsed.budget_sar:
                continue
        if parsed.sim_form in {"esim", "physical"}:
            form = package.get("sim_form")
            if form and form not in {parsed.sim_form, "either"}:
                continue
        key = (
            f"{provider}|{package.get('plan_name')}|{package.get('data_gb')}|"
            f"{package.get('price_sar')}|{package.get('validity_days')}"
        )
        if key in seen:
            continue
        seen.add(key)
        filtered.append(dict(package))
    if parsed.service_type == "data":
        data_only = [
            row
            for row in filtered
            if row.get("data_gb") is not None and not row.get("voice_minutes")
        ]
        if data_only:
            return data_only
        return [row for row in filtered if row.get("data_gb") is not None] or filtered
    if parsed.service_type == "voice":
        with_voice = [row for row in filtered if row.get("voice_minutes") is not None]
        if with_voice:
            return with_voice
    return filtered


def _safe_fetch(loader: Fetcher, url: str) -> str:
    return loader(url)


def _parse_stc(body: str, url: str, checked_at: str) -> list[dict]:
    packages = []
    blocks = re.split(r'data-product-name="', body)[1:]
    for block in blocks:
        name_match = re.match(r'([^"]+)', block)
        if not name_match:
            continue
        name = html.unescape(name_match.group(1)).strip()
        if not re.search(r"visitor", name, re.IGNORECASE):
            continue
        price = _first_float(
            re.search(r'data-product-price="([^"]+)"', block[:800])
            or re.search(r'productPriceCost[^>]*>\s*([^<]+)', block[:4000])
        )
        data_gb = _first_data_gb(
            re.search(
                r'product-card-featureTitle[^>]*>\s*([^<]+)',
                block[:4000],
            )
        )
        minutes = _hours_or_minutes(
            re.search(r'product-card-descTitle[^>]*>\s*([^<]+)', block[:5000])
        )
        validity_match = re.search(r"package validity:\s*([^<]+)", block[:6000], re.IGNORECASE)
        validity = _validity_days(validity_match.group(1) if validity_match else "")
        packages.append(
            _package_row(
                provider="STC",
                plan_name=name,
                sim_form="physical",
                data_gb=data_gb,
                voice_minutes=minutes,
                validity_days=validity,
                price=price,
                source_url=url,
                checked_at=checked_at,
                summary=f"stc {name} from the official sawa visitor page.",
            )
        )
    return packages


def _parse_mobily(body: str, url: str, checked_at: str) -> list[dict]:
    text = _visible_text(body)
    match = re.search(
        r"Visitors?\s+(\d+)\s*[Φφ]?\s*([\d.]+)\s*/\s*(\d+)\s*Days",
        text,
        re.IGNORECASE,
    )
    if not match:
        return []
    plan_name = f"Visitor {match.group(1)}"
    price = float(match.group(2))
    validity = int(match.group(3))
    data_match = re.search(r"Data\s+(\d+(?:\.\d+)?)\s*GB", text, re.IGNORECASE)
    minutes_match = re.search(r"Minutes\s+(\d+)", text, re.IGNORECASE)
    data_gb = float(data_match.group(1)) if data_match else None
    minutes = int(minutes_match.group(1)) if minutes_match else None
    sim_form = "esim" if re.search(r"\besim\b", text, re.IGNORECASE) else "physical"
    return [
        _package_row(
            provider="Mobily",
            plan_name=plan_name,
            sim_form=sim_form,
            data_gb=data_gb,
            voice_minutes=minutes,
            validity_days=validity,
            price=price,
            source_url=url,
            checked_at=checked_at,
            summary=f"Mobily {plan_name} from the official visitor plan page. Prices include VAT.",
        )
    ]


def _parse_zain_json(body: str, url: str, checked_at: str) -> list[dict]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FetchError("Zain official package feed was not valid JSON.") from exc
    packages = []
    for category in payload.get("dataPackages") or []:
        if not isinstance(category, dict):
            continue
        for item in category.get("items") or []:
            if not isinstance(item, dict):
                continue
            if not _truthy_flag(item.get("active", 1)):
                continue
            title = _strip_tags(item.get("title") or item.get("cms_title") or "")
            if not title:
                continue
            benefits = item.get("property_benefits") or []
            data_gb = _benefit_data_gb(benefits)
            minutes = _benefit_minutes(benefits)
            validity = _benefit_validity(benefits)
            if _truthy_flag(item.get("unlimited_data")):
                data_gb = 999.0
            price = _to_float(item.get("price_tax_included") or item.get("price"))
            source = item.get("redirect_url") or ZAIN_PAGE_URL
            packages.append(
                _package_row(
                    provider="Zain",
                    plan_name=title,
                    sim_form="physical",
                    data_gb=data_gb,
                    voice_minutes=minutes,
                    validity_days=validity,
                    price=price,
                    source_url=source,
                    checked_at=checked_at,
                    summary=_strip_tags(item.get("description_short") or item.get("description") or title)[:280],
                )
            )
    return packages


def _parse_lebara(body: str, url: str, checked_at: str) -> list[dict]:
    text = _visible_text(body)
    if not re.search(r"\b(?:prepaid|visitor|esim|tourist)\b", text, re.IGNORECASE):
        return []
    return _generic_official_packages("Lebara", text, url, checked_at)


def _parse_virgin(body: str, url: str, checked_at: str) -> list[dict]:
    text = _visible_text(body)
    if not re.search(r"\b(?:visitor|tourist|prepaid|esim)\b", text, re.IGNORECASE):
        return []
    return _generic_official_packages("Virgin Mobile", text, url, checked_at)


def _generic_official_packages(provider: str, text: str, url: str, checked_at: str) -> list[dict]:
    packages = []
    for match in re.finditer(
        r"(?:prepaid|visitor|tourist|esim)[^.|]{0,80}?"
        r"(?:(\d+(?:\.\d+)?)\s*GB)?[^.|]{0,40}?"
        r"(?:(\d+)\s*(?:day|days))?[^.|]{0,40}?"
        r"(?:(\d+(?:\.\d+)?)\s*(?:SAR|SR))",
        text,
        re.IGNORECASE,
    ):
        packages.append(
            _package_row(
                provider=provider,
                plan_name=f"{provider} visitor plan",
                sim_form="esim" if re.search(r"esim", match.group(0), re.IGNORECASE) else "physical",
                data_gb=float(match.group(1)) if match.group(1) else None,
                voice_minutes=None,
                validity_days=int(match.group(2)) if match.group(2) else None,
                price=float(match.group(3)) if match.group(3) else None,
                source_url=url,
                checked_at=checked_at,
                summary=match.group(0)[:280],
            )
        )
    return packages


def _package_row(
    *,
    provider: str,
    plan_name: str,
    sim_form: str,
    data_gb: float | None,
    voice_minutes: int | None,
    validity_days: int | None,
    price: float | None,
    source_url: str,
    checked_at: str,
    summary: str,
) -> dict:
    return {
        "provider": provider,
        "plan_name": plan_name,
        "title": _display_title(
            provider, sim_form, data_gb, voice_minutes, validity_days, price, plan_name
        ),
        "source_title": plan_name[:160],
        "summary": summary[:280],
        "price_sar": price,
        "price_label": f"{price:g} SAR" if price is not None else "Price not listed in source",
        "data_gb": data_gb,
        "data_label": _data_label(data_gb),
        "voice_minutes": voice_minutes,
        "validity_days": validity_days,
        "sim_form": sim_form,
        "source_url": source_url,
        "source_checked_at": checked_at,
        "status": "active_candidate",
    }


def _display_title(
    provider: str,
    sim_form: str,
    data_gb: float | None,
    voice_minutes: int | None,
    validity_days: int | None,
    price: float | None,
    plan_name: str,
) -> str:
    kind = "eSIM" if sim_form == "esim" else "tourist SIM"
    facts = [_data_label(data_gb) if data_gb is not None else "data not listed"]
    if voice_minutes is not None:
        facts.append("Unlimited calls" if voice_minutes >= 9999 else f"{voice_minutes} min")
    if validity_days is not None:
        facts.append(f"{validity_days} days")
    facts.append(f"{price:g} SAR" if price is not None else "price not listed")
    label = plan_name.strip() if plan_name and plan_name.lower() not in {provider.lower(), ""} else kind
    if label.lower().startswith(provider.lower()):
        return f"{label} — {' / '.join(facts)}"
    return f"{provider} {label} — {' / '.join(facts)}"


def _data_label(data_gb: float | None) -> str:
    if data_gb is None:
        return "Data not listed in source"
    if data_gb >= 999:
        return "Unlimited data"
    return f"{data_gb:g} GB"


def _is_discontinued(package: dict) -> bool:
    text = f"{package.get('title', '')} {package.get('summary', '')}".lower()
    return any(marker in text for marker in DISCONTINUED_MARKERS)


def _dedupe(packages: list[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for row in packages:
        key = (
            f"{row.get('provider')}|{row.get('plan_name')}|{row.get('data_gb')}|"
            f"{row.get('price_sar')}|{row.get('validity_days')}"
        )
        previous = unique.get(key)
        if previous is None or (previous.get("price_sar") is None and row.get("price_sar") is not None):
            unique[key] = row
    return list(unique.values())


def _visible_text(raw: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text)


def _strip_tags(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _truthy_flag(value) -> bool:
    if value in {None, "", 0, 0.0, "0", False, "false", "False", "no", "No"}:
        return False
    return True


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d+(?:\.\d+)?)", str(value).replace(",", ""))
    return float(match.group(1)) if match else None


def _first_float(match: re.Match | None) -> float | None:
    if not match:
        return None
    return _to_float(match.group(1))


def _first_data_gb(match: re.Match | None) -> float | None:
    if not match:
        return None
    return _parse_data_gb(match.group(1))


def _parse_data_gb(text: str) -> float | None:
    if re.search(r"\bunlimited\b", text or "", re.IGNORECASE):
        return 999.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|gigabytes?)\b", text or "", re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mb|megabytes?)\b", text or "", re.IGNORECASE)
    if match:
        return round(float(match.group(1)) / 1024, 3)
    return None


def _hours_or_minutes(match: re.Match | None) -> int | None:
    if not match:
        return None
    text = match.group(1)
    hours = re.search(r"(\d+(?:\.\d+)?)\s*hours?", text, re.IGNORECASE)
    if hours:
        return int(float(hours.group(1)) * 60)
    minutes = re.search(r"(\d+)\s*(?:minutes?|mins?)\b", text, re.IGNORECASE)
    if minutes:
        return int(minutes.group(1))
    return None


def _validity_days(text: str) -> int | None:
    blob = text or ""
    days = re.search(r"(\d+)\s*(?:day|days)\b", blob, re.IGNORECASE)
    if days:
        return int(days.group(1))
    weeks = re.search(r"(\d+)\s*(?:week|weeks)\b", blob, re.IGNORECASE)
    if weeks:
        return int(weeks.group(1)) * 7
    if re.search(r"\b(?:1|one)\s+month\b", blob, re.IGNORECASE):
        return 30
    return None


def _benefit_data_gb(benefits: list) -> float | None:
    for benefit in benefits:
        title = str(benefit.get("title") or "").lower()
        if "internet" not in title and "data" not in title:
            continue
        if _truthy_flag(benefit.get("unlimited")):
            return 999.0
        value = benefit.get("service_property_subtitle") or benefit.get("description") or ""
        parsed = _parse_data_gb(str(value))
        if parsed is not None:
            return parsed
        number = _to_float(value)
        if number is not None and number >= 1:
            return number
    return None


def _benefit_minutes(benefits: list) -> int | None:
    for benefit in benefits:
        title = str(benefit.get("title") or "").lower()
        if "minute" not in title and "call" not in title and "voice" not in title:
            continue
        if "social" in title:
            continue
        if _truthy_flag(benefit.get("unlimited")) or str(benefit.get("service_property_subtitle") or "").lower() == "unlimited":
            return 9999
        value = benefit.get("service_property_subtitle") or benefit.get("description") or ""
        match = re.search(r"(\d+)", str(value))
        if match:
            return int(match.group(1))
    return None


def _benefit_validity(benefits: list) -> int | None:
    for benefit in benefits:
        title = str(benefit.get("title") or "").lower()
        if "valid" not in title and "duration" not in title:
            continue
        days = _validity_days(str(benefit.get("service_property_subtitle") or ""))
        if days is not None:
            return days
    return None

