"""Step 1: collect app IDs for every search seed from Steam store search.

Output: data/raw/search_hits.csv (one row per appid x seed).
"""
import csv
import json
import time

import requests
from bs4 import BeautifulSoup

from config import RAW, SEEDS, TAG

URL = "https://store.steampowered.com/search/results/"
PAGE = 100


def fetch_page(tag_ids, start):
    params = {
        "tags": ",".join(map(str, tag_ids)),
        "category1": 998,  # games only
        "infinite": 1,
        "start": start,
        "count": PAGE,
        "cc": "us",
        "l": "english",
    }
    for attempt in range(6):
        r = requests.get(URL, params=params, timeout=60)
        if r.status_code == 200:
            return r.json()
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()


def parse_rows(html):
    for a in BeautifulSoup(html, "html.parser").select("a.search_result_row"):
        appid = a.get("data-ds-appid")
        if not appid or "," in appid:  # bundles carry several ids
            continue
        title = a.select_one(".title")
        released = a.select_one(".search_released")
        yield {
            "appid": int(appid),
            "name": title.get_text(strip=True) if title else "",
            "release_text": released.get_text(strip=True) if released else "",
        }


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / "search_hits.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["seed", "appid", "name", "release_text"])
        w.writeheader()
        for seed, tags in SEEDS.items():
            tag_ids = [TAG[t] for t in tags]
            first = fetch_page(tag_ids, 0)
            total = first["total_count"]
            seen = set()
            start, data = 0, first
            while True:
                rows = list(parse_rows(data["results_html"]))
                for row in rows:
                    if row["appid"] not in seen:
                        seen.add(row["appid"])
                        w.writerow({"seed": seed, **row})
                start += PAGE
                if start >= total or not rows:
                    break
                time.sleep(1)
                data = fetch_page(tag_ids, start)
            print(f"{seed}: total_count={total}, collected={len(seen)}", flush=True)


if __name__ == "__main__":
    main()
