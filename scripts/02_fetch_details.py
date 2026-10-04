"""Step 2: fetch store-page details and review totals for every collected app.

Resumable: already fetched appids in data/raw/app_details.jsonl are skipped.
"""
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import RAW

OUT = RAW / "app_details.jsonl"
COOKIES = {"birthtime": "0", "lastagecheckage": "1-0-1990", "wants_mature_content": "1"}
HEADERS = {"User-Agent": "Mozilla/5.0 (market research script)"}
WORKERS = 4

lock = threading.Lock()
session = requests.Session()
session.headers.update(HEADERS)
session.cookies.update(COOKIES)


def get(url, **params):
    for attempt in range(8):
        try:
            r = session.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 403, 502, 503):
                time.sleep(10 * (attempt + 1))
                continue
            return r
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    return None


def parse_store(appid, html):
    s = BeautifulSoup(html, "html.parser")
    d = {}
    m = re.search(r"InitAppTagModal\(\s*\d+,\s*(\[.*?\])\s*,", html, re.S)
    d["tags"] = [{"name": t["name"], "count": t["count"]} for t in json.loads(m.group(1))] if m else []
    for row in s.select(".dev_row"):
        label = row.select_one(".subtitle")
        if not label:
            continue
        key = label.get_text(strip=True).rstrip(":").lower()
        names = [a.get_text(strip=True) for a in row.select(".summary a")]
        if key in ("developer", "publisher"):
            d[key + "s"] = names
    date = s.select_one(".release_date .date")
    d["release_text"] = date.get_text(strip=True) if date else ""
    d["coming_soon"] = bool(s.select_one(".game_area_comingsoon"))
    desc = s.select_one(".game_description_snippet")
    d["short_description"] = desc.get_text(strip=True) if desc else ""
    # first purchase block is the base game; prefer the undiscounted price
    block = s.select_one(".game_area_purchase_game_wrapper .game_purchase_action, .game_purchase_action")
    orig = block.select_one(".discount_original_price") if block else None
    price = block.select_one("[data-price-final]") if block else None
    if orig:
        d["price_usd"] = float(re.sub(r"[^\d.]", "", orig.get_text()) or 0) or None
    else:
        d["price_usd"] = int(price["data-price-final"]) / 100 if price else None
    first_btn = s.select_one(".game_purchase_action .game_purchase_price")
    d["is_free"] = bool(first_btn and "free" in first_btn.get_text(strip=True).lower()) and d["price_usd"] is None
    d["early_access"] = bool(s.select_one(".early_access_header"))
    name = s.select_one("#appHubAppName")
    d["name"] = name.get_text(strip=True) if name else ""
    return d


def fetch(appid):
    rec = {"appid": appid}
    r = get(f"https://store.steampowered.com/app/{appid}/", l="english", cc="us")
    if r is None or f"/app/{appid}" not in r.url:
        rec["error"] = "store_unavailable"
    else:
        rec.update(parse_store(appid, r.text))
    rv = get(f"https://store.steampowered.com/appreviews/{appid}",
             json=1, num_per_page=0, language="all", purchase_type="all", filter="all")
    if rv is not None and rv.status_code == 200:
        q = rv.json().get("query_summary", {})
        rec["reviews_total"] = q.get("total_reviews")
        rec["reviews_positive"] = q.get("total_positive")
        rec["review_score_desc"] = q.get("review_score_desc")
    with lock:
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main():
    ids = sorted(pd.read_csv(RAW / "search_hits.csv").appid.unique().tolist())
    done = set()
    if OUT.exists():
        done = {json.loads(l)["appid"] for l in OUT.open(encoding="utf-8")}
    todo = [i for i in ids if i not in done]
    print(f"total={len(ids)} done={len(done)} todo={len(todo)}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        for n, _ in enumerate(ex.map(fetch, todo), 1):
            if n % 200 == 0:
                rate = n / (time.time() - t0)
                print(f"{n}/{len(todo)}  {rate:.1f}/s  eta {(len(todo) - n) / rate / 60:.0f} min", flush=True)
    print("finished", flush=True)


if __name__ == "__main__":
    sys.exit(main())
