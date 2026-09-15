import csv
import requests
import time
import os

API_KEY = os.environ["ZENROWS_API_KEY"]

INPUT = "clean_urls.csv"
OUTPUT = "zenrows_results.csv"

with open(INPUT, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

results = []

for i, row in enumerate(rows, 1):
    url = row["clean_url"].strip()

    print(f"[{i}/{len(rows)}] {url}")

    try:
        response = requests.get(
            "https://api.zenrows.com/v1/",
            params={
                "url": url,
                "apikey": API_KEY,
                "mode": "auto",
                "response_type": "markdown"
            },
            timeout=60
        )

        results.append({
            "url": url,
            "status": response.status_code,
            "content": response.text
        })

    except Exception as e:
        results.append({
            "url": url,
            "status": "ERROR",
            "content": str(e)
        })

    time.sleep(1)

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["url", "status", "content"]
    )
    writer.writeheader()
    writer.writerows(results)

print(f"\nDONE: {len(results)} URLs saved to {OUTPUT}")