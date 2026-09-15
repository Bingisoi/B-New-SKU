import json
import csv
import requests

INPUT = "discovered_urls.json"
OUTPUT = "clean_urls.csv"

with open(INPUT, "r", encoding="utf-8") as f:
    data = json.load(f)

results = []

for i, item in enumerate(data, 1):

    # Your JSON contains {"url": "..."}
    if isinstance(item, dict):
        url = item.get("url", "").strip()
    else:
        url = str(item).strip()

    final_url = ""

    try:
        response = requests.get(
            url,
            allow_redirects=True,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        final_url = response.url

    except Exception as e:
        print(f"[ERROR] {i}: {e}")
        final_url = url

    results.append({
        "original_url": url,
        "clean_url": final_url
    })

    print(f"[{i}/{len(data)}] {final_url}")

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["original_url", "clean_url"]
    )
    writer.writeheader()
    writer.writerows(results)

print()
print(f"DONE: {len(results)} URLs saved to {OUTPUT}")