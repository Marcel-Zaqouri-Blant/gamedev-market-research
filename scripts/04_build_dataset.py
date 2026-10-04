"""Step 4: merge raw data into data/games.csv (+ .xlsx for manual review).

One row per game with element flags, AAA flag, sales estimate and tag ranks.
"""
import json
import re

import pandas as pd

from config import (AAA_PUBLISHERS, BIG_PUBLISHERS, DATA, DOG_NAME_WORDS,
                    ELEMENT_TAGS, RAW)

SALES_MULT_LOW, SALES_MULT_HIGH = 20, 60
DOG_NAME_RE = re.compile(r"\b(" + "|".join(w.strip() for w in DOG_NAME_WORDS) + r")s?\b", re.I)
HOT_DOG_RE = re.compile(r"hot\s*-?dog|dogfight|watch\s*dogs|underdog", re.I)


def word_match(names, patterns):
    text = " | ".join(names).lower()
    return next((p for p in patterns if re.search(rf"(?<![\w]){re.escape(p)}(?![\w])", text)), "")


def release_year(text):
    m = re.search(r"\b(19|20)\d{2}\b", text or "")
    return int(m.group(0)) if m else None


def main():
    recs = [json.loads(l) for l in (RAW / "app_details.jsonl").open(encoding="utf-8")]
    recs = [r for r in recs if "error" not in r]
    hits = pd.read_csv(RAW / "search_hits.csv")
    seeds = hits.groupby("appid").seed.apply(lambda s: ",".join(sorted(set(s))))
    search_names = hits.drop_duplicates("appid").set_index("appid").name
    prices = pd.read_csv(RAW / "prices.csv").set_index("appid").price_initial_usd

    rows = []
    for r in recs:
        appid = r["appid"]
        tags = [t["name"] for t in r.get("tags", [])]
        name = (r.get("name") or "").strip() or search_names.get(appid, "")
        pubs, devs = r.get("publishers", []), r.get("developers", [])
        row = {
            "appid": appid,
            "name": name,
            "url": f"https://store.steampowered.com/app/{appid}/",
            "developers": "; ".join(devs),
            "publishers": "; ".join(pubs),
            "release_text": r.get("release_text", ""),
            "release_year": release_year(r.get("release_text")),
            "coming_soon": r.get("coming_soon", False),
            "early_access": r.get("early_access", False),
            "price_usd": prices.get(appid),
            "reviews_total": r.get("reviews_total") or 0,
            "reviews_positive": r.get("reviews_positive") or 0,
            "review_score_desc": r.get("review_score_desc", ""),
            "tags": ", ".join(tags),
            "short_description": r.get("short_description", ""),
            "seeds": seeds.get(appid, ""),
        }
        row["positive_pct"] = (round(100 * row["reviews_positive"] / row["reviews_total"], 1)
                               if row["reviews_total"] else None)
        row["sales_est_low"] = row["reviews_total"] * SALES_MULT_LOW
        row["sales_est_high"] = row["reviews_total"] * SALES_MULT_HIGH
        row["aaa_match"] = word_match(pubs + devs, AAA_PUBLISHERS)
        row["big_publisher_match"] = word_match(pubs, BIG_PUBLISHERS)

        # element flags + best tag rank (1 = most voted tag)
        for el, el_tags in ELEMENT_TAGS.items():
            ranks = [i + 1 for i, t in enumerate(tags) if t in el_tags]
            row[f"{el}_rank"] = min(ranks) if ranks else None
            row[f"el_{el}"] = bool(ranks)
        dog_name = bool(DOG_NAME_RE.search(name)) and not HOT_DOG_RE.search(name)
        row["dog_by_name"] = dog_name
        row["el_dog"] = row["el_dog"] or dog_name
        row["el_friendslop"] = (row["el_coop_online"]
                                and (row["el_comedy"] or row["el_physics"] or row["el_party"])
                                and "Massively Multiplayer" not in tags)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["is_aaa"] = df.aaa_match != ""
    df["released"] = ~df.coming_soon & df.release_year.notna()
    df["serious_indie"] = (~df.is_aaa & df.released & df.price_usd.notna()
                           & (df.reviews_total >= 10))
    df = df.sort_values("reviews_total", ascending=False)
    df.to_csv(DATA / "games.csv", index=False)
    print(f"games: {len(df)}  aaa: {df.is_aaa.sum()}  released: {df.released.sum()}  "
          f"coming soon: {df.coming_soon.sum()}  serious indie: {df.serious_indie.sum()}")


if __name__ == "__main__":
    main()
