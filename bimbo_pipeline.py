import csv
import sys
import re

csv.field_size_limit(sys.maxsize)

INPUT_FILE = "zenrows_results.csv"
OUTPUT_FILE = "clay_input_231.csv"

MAX_CONTEXT = 10000


def clean_content(text):
    if not text:
        return ""

    # Remove markdown images
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)

    # Convert markdown links to visible text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove URLs
    text = re.sub(r'https?://\S+', ' ', text)

    # Remove empty markdown links
    text = re.sub(r'\[\s*\]', ' ', text)

    # Remove common navigation noise
    noise = [
        "Local Sports Things To Do Politics Real Estate",
        "Advertise Obituaries eNewspaper Legals Search",
        "Privacy Policy Terms of Service",
        "Subscribe Today",
        "Sign In Login",
        "Cookie Policy",
        "Follow us on",
        "Contact Us",
        "Advertise Your Business"
    ]

    for item in noise:
        text = text.replace(item, " ")

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def extract_title(text):
    if not text:
        return ""

    # Find the first markdown H1
    match = re.search(r'#\s+(.+?)(?=\s{2,}|$)', text)

    if match:
        return match.group(1).strip()[:500]

    # Fallback
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for sentence in sentences:
        sentence = sentence.strip()

        if 20 <= len(sentence) <= 300:
            return sentence

    return text[:300]


def detect_page_type(url, text):

    u = url.lower()
    t = text.lower()

    if "linkedin.com/jobs" in u:
        return "Job Posting"

    if "/jobs/" in u or "jobs" in u or "career" in u:
        return "Job Posting"

    if any(x in t for x in [
        "new store",
        "new stores",
        "store opening",
        "store openings",
        "opening new location",
        "opening new locations"
    ]):
        return "Store / Retail News"

    if any(x in t for x in [
        "bakery",
        "bakeries",
        "bread",
        "baked goods"
    ]):
        return "Bakery / Food"

    if any(x in t for x in [
        "procurement",
        "purchasing",
        "sourcing",
        "supplier"
    ]):
        return "Procurement / Supply Chain"

    if any(x in t for x in [
        "distribution center",
        "distribution centre",
        "warehouse"
    ]):
        return "Distribution / Supply Chain"

    return "Article / Webpage"


def find_signal_keywords(text):

    text_lower = text.lower()

    keywords = {
        "store expansion": [
            "new store",
            "new stores",
            "store opening",
            "store openings",
            "opens new location",
            "opening new locations"
        ],

        "grocery expansion": [
            "grocery expansion",
            "retail expansion",
            "expand its footprint",
            "expanding its footprint"
        ],

        "bakery": [
            "bakery",
            "bakeries",
            "bread",
            "baked goods"
        ],

        "hiring": [
            "hiring",
            "now hiring",
            "job opening",
            "job openings",
            "career opportunity"
        ],

        "category management": [
            "category manager",
            "category management",
            "category leadership"
        ],

        "procurement": [
            "procurement",
            "purchasing",
            "sourcing",
            "supplier"
        ],

        "distribution": [
            "distribution center",
            "distribution centre",
            "warehouse",
            "distribution facility"
        ],

        "acquisition": [
            "acquisition",
            "acquired",
            "merger",
            "merging"
        ],

        "investment": [
            "investment",
            "million investment",
            "capital investment",
            "capital expenditure"
        ]
    }

    found = []

    for category, terms in keywords.items():

        for term in terms:

            if term in text_lower:
                found.append(category)
                break

    return list(dict.fromkeys(found))


def extract_relevant_context(text):

    if not text:
        return ""

    keywords = [
        "new store",
        "new stores",
        "store opening",
        "store openings",
        "opening",
        "opens",
        "expansion",
        "expanding",
        "grocery",
        "supermarket",
        "bakery",
        "bakery department",
        "bread",
        "baked goods",
        "category manager",
        "category management",
        "merchandising",
        "procurement",
        "purchasing",
        "supplier",
        "sourcing",
        "distribution",
        "distribution center",
        "warehouse",
        "foodservice",
        "acquisition",
        "acquired",
        "merger",
        "investment",
        "facility",
        "manufacturing",
        "hiring",
        "job opening",
        "leadership"
    ]

    sentences = re.split(r'(?<=[.!?])\s+', text)

    relevant = []

    for sentence in sentences:

        sentence = sentence.strip()

        if len(sentence) < 40:
            continue

        lower = sentence.lower()

        if any(keyword in lower for keyword in keywords):
            relevant.append(sentence)

        if len(relevant) >= 15:
            break

    if not relevant:
        return text[:MAX_CONTEXT]

    return " ".join(relevant)[:MAX_CONTEXT]


# ==========================================
# LOAD ALL 231 SCRAPED RECORDS
# ==========================================

with open(INPUT_FILE, "r", encoding="utf-8") as f:

    rows = list(csv.DictReader(f))


print(f"Loaded {len(rows)} scraped records")


results = []


for i, row in enumerate(rows, 1):

    url = row.get("url", "")
    status = row.get("status", "")
    raw_content = row.get("content", "")

    cleaned = clean_content(raw_content)

    title = extract_title(cleaned)

    page_type = detect_page_type(
        url,
        cleaned
    )

    keywords = find_signal_keywords(
        cleaned
    )

    context = extract_relevant_context(
        cleaned
    )

    results.append({

        "source_url": url,

        "scrape_status": status,

        "page_title": title,

        "page_type": page_type,

        "signal_keywords": "; ".join(keywords),

        "signal_context": context
    })

    print(
        f"[{i}/{len(rows)}] processed"
    )


# ==========================================
# CREATE CLAY INPUT
# ==========================================

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "source_url",
            "scrape_status",
            "page_title",
            "page_type",
            "signal_keywords",
            "signal_context"
        ]
    )

    writer.writeheader()

    writer.writerows(results)


print()
print("====================================")
print("DONE")
print(f"Created: {OUTPUT_FILE}")
print(f"Rows: {len(results)}")
print("====================================")