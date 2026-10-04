"""Step 3: base USD prices via the batch appdetails endpoint (100 apps per call).

Output: data/raw/prices.csv  (appid, price_initial_usd; empty = free / not for sale)
"""
import csv
import time

import pandas as pd
import requests

from config import RAW

BATCH = 100


def main():
    ids = sorted(pd.read_csv(RAW / "search_hits.csv").appid.unique().tolist())
    with (RAW / "prices.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["appid", "price_initial_usd"])
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            for attempt in range(6):
                r = requests.get("https://store.steampowered.com/api/appdetails",
                                 params={"appids": ",".join(map(str, chunk)),
                                         "filters": "price_overview", "cc": "us"}, timeout=60)
                if r.status_code == 200 and r.text.startswith("{"):
                    break
                time.sleep(15 * (attempt + 1))
            for appid, v in r.json().items():
                po = (v.get("data") or {}).get("price_overview") if isinstance(v.get("data"), dict) else None
                w.writerow([appid, po["initial"] / 100 if po else ""])
            time.sleep(1.5)
    print("done")


if __name__ == "__main__":
    main()
