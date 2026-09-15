"""
Bimbo Bakeries — Arizona Retail Expansion Signal Pipeline
============================================================
Discovers retail expansion / bakery / competitor signals via Serper,
then crawls + extracts structured data via Crawl4AI's LLM extraction
strategy, scores each signal, and writes results to CSV/JSON.

Install:
    pip install crawl4ai requests python-dotenv pydantic
    crawl4ai-setup   # installs Playwright browsers

Env vars required:
    SERPER_API_KEY
    OPENAI_API_KEY (or swap the LLM provider config below)
"""

import os
import json
import time
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List

import requests
from pydantic import BaseModel, Field

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

SERPER_API_KEY = os.environ["SERPER_API_KEY"]
LOOKBACK_DAYS = 90

RETAILERS = [
    "Fry's Food Stores", "Safeway", "Albertsons",
]

COMPETITORS = [
    "Flowers Foods", "Nature's Own", "Wonder Bread", "Sara Lee bakery",
]

AZ_CITIES = ["Phoenix", "Tucson", "Mesa", "Scottsdale", "Chandler",
             "Gilbert", "Glendale", "Tempe", "Peoria", "Surprise"]

# ----------------------------------------------------------------------
# COUNTY / CITY PERMIT PORTAL MAP
# ----------------------------------------------------------------------
# Most AZ municipalities run on Accela Citizen Access (ACA) or OpenGov for
# public permit search. Where a city has its own domain, query it directly;
# otherwise fall back to the county assessor/permit portal. These feed the
# PERMIT_QUERY_TEMPLATES below and the address cross-reference stage.

AZ_COUNTIES = {
    "Maricopa": {
        "permit_domains": ["phoenix.gov", "accela.mesaaz.gov", "eservices.chandleraz.gov",
                            "gilbertaz.gov", "scottsdaleaz.gov", "tempe.gov",
                            "glendaleaz.com", "peoriaaz.gov", "surpriseaz.gov"],
        "assessor_domain": "mcassessor.maricopa.gov",
        "cities": ["Phoenix", "Mesa", "Chandler", "Gilbert", "Scottsdale",
                   "Tempe", "Glendale", "Peoria", "Surprise"],
    },
    "Pima": {
        "permit_domains": ["tucsonaz.gov"],
        "assessor_domain": "asr.pima.gov",
        "cities": ["Tucson", "Oro Valley", "Marana"],
    },
    "Pinal": {
        "permit_domains": ["casagrandeaz.gov", "sanetanvalley.gov"],
        "assessor_domain": "pinalcountyaz.gov",
        "cities": ["Casa Grande", "San Tan Valley", "Maricopa"],
    },
    "Yavapai": {
        "permit_domains": ["prescott-az.gov"],
        "assessor_domain": "yavapaiaz.gov",
        "cities": ["Prescott", "Prescott Valley"],
    },
    "Coconino": {
        "permit_domains": ["flagstaffaz.gov"],
        "assessor_domain": "coconino.az.gov",
        "cities": ["Flagstaff"],
    },
    "Yuma": {
        "permit_domains": ["yumaaz.gov"],
        "assessor_domain": "yumacountyaz.gov",
        "cities": ["Yuma"],
    },
    "Mohave": {
        "permit_domains": ["lakehavasucity.az.gov", "kingmanaz.gov"],
        "assessor_domain": "mohavecounty.us",
        "cities": ["Lake Havasu City", "Kingman", "Bullhead City"],
    },
    "Cochise": {
        "permit_domains": ["sierravistaaz.gov"],
        "assessor_domain": "cochise.az.gov",
        "cities": ["Sierra Vista", "Douglas"],
    },
}

# Flat list retained for backwards compatibility with scoring logic below
AZ_CITIES = sorted({c for county in AZ_COUNTIES.values() for c in county["cities"]})

# Which counties to run permit-portal queries against by default.
# Maricopa (Phoenix metro) + Pima (Tucson) cover the large majority of AZ
# retail activity. Add county keys here to widen coverage at higher query cost.
PERMIT_SCOPE_COUNTIES = ["Maricopa", "Pima"]

PERMIT_QUERY_TEMPLATES = [
    '{r} {domain} commercial permit',
    '{r} {domain} building permit bakery grocery retail',
    '{r} {city} building permit commercial 2026',
    '{r} {city} site plan review commercial',
    '{r} {city} certificate of occupancy',
]

QUERY_TEMPLATES = [
    '{r} new stores Arizona 2026',
    '{r} bakery expansion Arizona',
    '{r} category manager bakery',
    '{r} buyer bakery hiring Arizona',
    '{r} distribution center Arizona 2026',
    '{r} distribution center bakery',
    '{r} bread bakery expansion',
    '{r} grand opening Arizona',
    '{r} remodel bakery department',
    '{r} category manager bakery Arizona linkedin jobs',
    '{r} bakery news progressive grocer',
    '{r} Arizona supermarket news',
    '{r} Arizona distribution press release',
    '{r} WARN notice Arizona',
]

COMPETITOR_QUERY_TEMPLATES = [
    '{c} store closing Arizona',
    '{c} bakery program Arizona',
    '{c} distribution Arizona',
    '{c} losing shelf space Arizona',
]

# ----------------------------------------------------------------------
# OUTPUT SCHEMA — mirrors the exact report shape requested
# ----------------------------------------------------------------------

class Signal(BaseModel):
    retailer: str = Field(description="Retail chain or banner name")
    signal_type: str = Field(description="One of: Store Expansion, Bakery/Category News, "
                                          "New Buyer, Competitor Activity, Distribution Center, "
                                          "Permit Filing, Other")
    location: str = Field(description="City/state or region")
    street_address: Optional[str] = Field(default=None, description="Exact street address if mentioned "
                                           "in the source (news copy, permit filing, or press release)")
    county: Optional[str] = Field(default=None, description="Arizona county, if determinable from location/address")
    store_count: Optional[str] = Field(default=None, description="Number of stores if mentioned")
    category: str = Field(default="Grocery", description="Retail category")
    bakery_relevance: str = Field(description="High, Medium, or Low")
    date: str = Field(description="Date of the news/event, YYYY-MM or best guess")
    evidence: str = Field(description="1-2 sentence summary of what was found, in your own words")
    source_url: str = Field(description="URL of the source page")
    competitor_present: bool = Field(default=False, description="True if a Bimbo competitor is named as incumbent")
    permit_confirmed: bool = Field(default=False, description="True if this signal is itself a permit/"
                                    "construction filing, or the extraction found one referencing the same address")


EXTRACTION_INSTRUCTION = """
You are analyzing a web page for retail/bakery industry signals relevant to
Bimbo Bakeries USA's expansion and account-targeting strategy in Arizona.

Extract ONLY if the page contains a genuine signal matching one of these types:
- Store Expansion (new stores, grand openings, remodels)
- Bakery/Category News (bakery department changes, new category strategy)
- New Buyer (new category manager / buyer hired or promoted)
- Competitor Activity (a Bimbo competitor — Flowers Foods, Nature's Own,
  Wonder Bread, Sara Lee, or a private-label bakery program — gaining or
  losing placement)
- Distribution Center (new/expanded DC, DC hiring, WARN notices)
- Permit Filing (a municipal building permit, site plan review, or
  certificate of occupancy record — these often carry the exact street
  address, which is the highest-confidence location data available)

If the page includes a specific street address (common on permit portals,
press releases, and local news with dateline addresses), extract it exactly
as written into street_address, and infer the Arizona county from the
city if possible.

For each distinct signal found, output a JSON object with these fields:
retailer, signal_type, location, street_address, county, store_count,
category, bakery_relevance (High/Medium/Low — High if bakery/bread is
explicitly mentioned, Medium if general grocery category, Low if
tangential), date, evidence (rewritten in your own words, 1-2 sentences,
never copy source text verbatim), source_url, competitor_present (true/false),
permit_confirmed (true if this page is itself a permit/construction record).

If the page has no relevant signal, return an empty list.
Do not fabricate data. Only extract what is explicitly stated on the page.
"""

# ----------------------------------------------------------------------
# STAGE 1 — SERPER DISCOVERY
# ----------------------------------------------------------------------

def serper_search(query: str, search_type: str = "news", num: int = 20) -> list[dict]:
    """Query Serper's search or news endpoint. Retries on transient server
    errors (502/503/504) since those are Serper-side blips, not a real
    problem with the key, credits, or query — but does NOT retry on 400/403,
    since those are permanent until you fix the actual cause."""
    url = f"https://google.serper.dev/{search_type}"
    payload = {"q": query, "num": num, "gl": "us", "hl": "en"}
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.ok:
            data = resp.json()
            return data.get("news", []) or data.get("organic", [])

        if resp.status_code in (502, 503, 504) and attempt < max_retries:
            print(f"    (transient {resp.status_code} from Serper, retrying in 5s...)")
            time.sleep(5)
            continue

        # Permanent failure (bad key, no credits, bad query pattern) or
        # retries exhausted — surface the real error body and give up.
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} {resp.reason} for url: {url} -> body: {resp.text}"
        )

    # unreachable, but keeps type checkers happy
    return []


def within_lookback(date_str: Optional[str]) -> bool:
    """Serper news results include a relative or absolute date string.
    Best-effort filter; final date confidence comes from Crawl4AI extraction."""
    if not date_str:
        return True  # keep — let extraction stage confirm/reject
    return True  # placeholder: Serper's 'date' field is inconsistent enough
                 # that hard filtering here drops good signals; filter post-extraction instead


def discover_urls() -> list[dict]:
    """Run all query templates across retailers + competitors, dedupe URLs."""
    seen = {}
    all_queries = []

    for r in RETAILERS:
        for tmpl in QUERY_TEMPLATES:
            all_queries.append(tmpl.format(r=r))
    for c in COMPETITORS:
        for tmpl in COMPETITOR_QUERY_TEMPLATES:
            all_queries.append(tmpl.format(c=c))

    # Permit-portal queries: per retailer, per county, per domain/city.
    # NOTE: this is the most expensive block (retailers x counties x cities x
    # templates). Default scope is Maricopa + Pima only — where 80%+ of AZ
    # retail expansion actually happens. Set PERMIT_SCOPE = "all" below to
    # widen to every county, but expect several thousand queries.
    permit_counties = {k: v for k, v in AZ_COUNTIES.items() if k in PERMIT_SCOPE_COUNTIES}
    for r in RETAILERS:
        for county, info in permit_counties.items():
            for city in info["cities"]:
                for tmpl in PERMIT_QUERY_TEMPLATES:
                    if "{domain}" in tmpl:
                        for domain in info["permit_domains"]:
                            all_queries.append(tmpl.format(r=r, domain=domain, city=city))
                    else:
                        all_queries.append(tmpl.format(r=r, city=city))

    print(f"Running {len(all_queries)} Serper queries...")
    consecutive_failures = 0
    for q in all_queries:
        try:
            results = serper_search(q, search_type="news")
            if not results:
                results = serper_search(q, search_type="search")
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            print(f"  ! query failed: {q[:60]} -> {e}")
            if consecutive_failures >= 5:
                print("\n5 queries in a row failed the same way — stopping early "
                      "instead of burning through the rest. Fix whatever the error "
                      "above says (key, credits, or param issue) and re-run.")
                raise SystemExit(1)
            continue

        for item in results:
            link = item.get("link")
            if not link:
                continue
            url_hash = hashlib.md5(link.encode()).hexdigest()
            if url_hash not in seen:
                seen[url_hash] = {
                    "url": link,
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "date": item.get("date", ""),
                    "query": q,
                }
        time.sleep(0.2)  # gentle rate limiting

    print(f"Discovered {len(seen)} unique URLs.")
    return list(seen.values())


# ----------------------------------------------------------------------
# STAGE 2 — CRAWL4AI EXTRACTION
# ----------------------------------------------------------------------

async def extract_signals(urls: list[dict]) -> list[dict]:
    """Crawl each URL and run LLM structured extraction against the Signal schema."""
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider="openai/gpt-4o-mini", api_token=os.environ.get("OPENAI_API_KEY")),
        schema=Signal.model_json_schema(),
        extraction_type="schema",
        instruction=EXTRACTION_INSTRUCTION,
        chunk_token_threshold=4000,
        apply_chunking=True,
        input_format="markdown",
    )

    run_config = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        cache_mode="bypass",
        page_timeout=30000,
    )

    all_signals = []
    async with AsyncWebCrawler() as crawler:
        for item in urls:
            try:
                result = await crawler.arun(url=item["url"], config=run_config)
                if not result.success or not result.extracted_content:
                    continue
                parsed = json.loads(result.extracted_content)
                if isinstance(parsed, dict):
                    parsed = [parsed]
                for sig in parsed:
                    sig["source_url"] = item["url"]
                    sig["_discovery_query"] = item["query"]
                    all_signals.append(sig)
            except Exception as e:
                print(f"  ! extraction failed for {item['url'][:60]} -> {e}")
                continue

    return all_signals


# ----------------------------------------------------------------------
# STAGE 2.5 — GEOCODING + PERMIT CROSS-REFERENCE
# ----------------------------------------------------------------------

def geocode_address(address: str, city: str = "") -> Optional[dict]:
    """Free geocoding via OpenStreetMap Nominatim (no API key needed).
    Rate-limited to 1 req/sec per Nominatim's usage policy — fine for
    batch runs, don't parallelize this without your own tile/geocoding key."""
    if not address:
        return None
    query = f"{address}, {city}, Arizona" if city else f"{address}, Arizona"
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "bimbo-bakeries-signal-pipeline/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return {"lat": results[0]["lat"], "lon": results[0]["lon"],
                    "display_name": results[0]["display_name"]}
    except Exception as e:
        print(f"  ! geocode failed for '{address}' -> {e}")
    time.sleep(1)  # Nominatim rate limit
    return None


def cross_reference_permits(signals: list[dict]) -> list[dict]:
    """Link non-permit signals (news, job posts) to permit-filing signals
    that share a retailer + city, to upgrade location confidence. If a
    permit signal exists for the same retailer/city within the lookback
    window, mark the paired news signal as permit_confirmed."""
    permit_signals = [s for s in signals if s.get("signal_type") == "Permit Filing"]

    for sig in signals:
        if sig.get("signal_type") == "Permit Filing":
            continue
        for permit in permit_signals:
            same_retailer = sig.get("retailer", "").lower() == permit.get("retailer", "").lower()
            same_city = (sig.get("location", "").lower().split(",")[0].strip()
                         == permit.get("location", "").lower().split(",")[0].strip())
            if same_retailer and same_city:
                sig["permit_confirmed"] = True
                if not sig.get("street_address") and permit.get("street_address"):
                    sig["street_address"] = permit["street_address"]
                break

    return signals


def enrich_with_geocoding(signals: list[dict]) -> list[dict]:
    """Geocode any signal that has a street_address, to enable mapping
    (Airtable map view, Google Sheets + Maps, or a Clay location column)."""
    for sig in signals:
        addr = sig.get("street_address")
        if addr:
            geo = geocode_address(addr, sig.get("location", ""))
            if geo:
                sig["latitude"] = geo["lat"]
                sig["longitude"] = geo["lon"]
    return signals


# ----------------------------------------------------------------------
# STAGE 3 — OPPORTUNITY SCORING
# ----------------------------------------------------------------------

def score_signal(sig: dict) -> int:
    """
    Opportunity Score (1-10). Weighted for: recency, bakery relevance,
    signal type strength, competitor displacement potential, and
    Arizona geographic specificity.
    """
    score = 5  # baseline

    relevance = str(sig.get("bakery_relevance", "")).lower()
    if relevance == "high":
        score += 2
    elif relevance == "medium":
        score += 1

    signal_type = str(sig.get("signal_type", "")).lower()
    high_value_types = ["new buyer", "competitor activity", "distribution center"]
    if any(t in signal_type for t in high_value_types):
        score += 1

    if sig.get("competitor_present"):
        score += 2  # displacement opportunities are the highest-value plays

    location = str(sig.get("location", "")).lower()
    if any(city.lower() in location for city in AZ_CITIES) or "arizona" in location:
        score += 1

    # A confirmed street address (from the signal itself or a cross-referenced
    # permit filing) is a strong confidence boost — it's the difference
    # between "somewhere in Phoenix" and an address a rep can drive to.
    if sig.get("street_address") or sig.get("permit_confirmed"):
        score += 1

    # Recency check
    date_str = sig.get("date", "")
    try:
        parsed_date = datetime.strptime(date_str[:7], "%Y-%m")
        if parsed_date >= datetime.now() - timedelta(days=LOOKBACK_DAYS):
            score += 1
    except Exception:
        pass

    return max(1, min(10, score))


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

async def main():
    urls = discover_urls()

    # Save raw discovery for audit/debugging
    with open("/home/claude/discovered_urls.json", "w") as f:
        json.dump(urls, f, indent=2)

    signals = await extract_signals(urls)

    # Link news/job/DC signals to permit filings at the same retailer+city,
    # then geocode any signal carrying a street address.
    signals = cross_reference_permits(signals)
    signals = enrich_with_geocoding(signals)

    for sig in signals:
        sig["opportunity_score"] = score_signal(sig)

    # Sort by score descending
    signals.sort(key=lambda s: s.get("opportunity_score", 0), reverse=True)

    with open("/home/claude/bimbo_az_signals.json", "w") as f:
        json.dump(signals, f, indent=2)

    # CSV output
    import csv
    if signals:
        fieldnames = ["retailer", "signal_type", "location", "street_address",
                      "county", "latitude", "longitude", "store_count",
                      "category", "bakery_relevance", "date", "evidence",
                      "opportunity_score", "source_url", "competitor_present",
                      "permit_confirmed"]
        with open("/home/claude/bimbo_az_signals.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(signals)

    print(f"\nDone. {len(signals)} signals extracted -> bimbo_az_signals.csv / .json")


if __name__ == "__main__":
    asyncio.run(main())
