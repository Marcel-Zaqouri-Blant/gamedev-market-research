"""Step 5: metrics for every combination (1-3) of the main elements.

Only combinations that contain at least one fully collected element
(dog, hunting, friendslop, extraction) are reported — horror and roguelite were
collected only via those seeds, so their standalone numbers are not market-wide.

Output: data/segments.csv
"""
from itertools import combinations

import pandas as pd

from config import DATA

ELEMENTS = ["dog", "hunting", "friendslop", "horror", "roguelite", "extraction"]
FULLY_COLLECTED = {"dog", "hunting", "friendslop", "extraction"}
RECENT_FROM = 2022  # "recent" = released this year or later


def metrics(g, g_all):
    rev = g.reviews_total.sort_values(ascending=False)
    top3 = g.sort_values("reviews_total", ascending=False).head(3)
    by_year = g.groupby("release_year").size()
    return {
        "games_all_paid": len(g_all),
        "share_100plus_of_all": round((g_all.reviews_total >= 100).mean() * 100, 1) if len(g_all) else None,
        "games": len(g),
        "games_recent": int((g.release_year >= RECENT_FROM).sum()),
        "games_2024": int(by_year.get(2024, 0)),
        "games_2025": int(by_year.get(2025, 0)),
        "median_reviews": rev.median() if len(rev) else None,
        "p75_reviews": rev.quantile(0.75) if len(rev) else None,
        "p90_reviews": rev.quantile(0.90) if len(rev) else None,
        "share_100plus": round((rev >= 100).mean() * 100, 1) if len(rev) else None,
        "share_500plus": round((rev >= 500).mean() * 100, 1) if len(rev) else None,
        "share_1000plus": round((rev >= 1000).mean() * 100, 1) if len(rev) else None,
        "reviews_sum": int(rev.sum()),
        "reviews_sum_wo_top3": int(rev.iloc[3:].sum()),
        "top3_share_pct": round(100 * rev.head(3).sum() / rev.sum(), 1) if rev.sum() else None,
        "median_positive_pct": g.positive_pct.median(),
        "median_price": g.price_usd.median(),
        "top3": "; ".join(f"{n} ({r})" for n, r in zip(top3.name, top3.reviews_total)),
    }


def main():
    df = pd.read_csv(DATA / "games.csv")
    base = df[df.serious_indie]
    # every released paid non-AAA game, including ones with <10 reviews
    base_all = df[df.released & ~df.is_aaa & df.price_usd.notna()]
    upcoming = df[df.coming_soon & ~df.is_aaa]
    rows = []
    for k in (1, 2, 3):
        for combo in combinations(ELEMENTS, k):
            if not FULLY_COLLECTED & set(combo):
                continue
            mask = pd.Series(True, index=base.index)
            all_mask = pd.Series(True, index=base_all.index)
            up_mask = pd.Series(True, index=upcoming.index)
            for el in combo:
                mask &= base[f"el_{el}"]
                all_mask &= base_all[f"el_{el}"]
                up_mask &= upcoming[f"el_{el}"]
            g = base[mask]
            if g.empty and not up_mask.any():
                continue
            rows.append({"segment": " + ".join(combo), "n_elements": k,
                         **metrics(g, base_all[all_mask]), "upcoming": int(up_mask.sum())})
    out = pd.DataFrame(rows)
    out.to_csv(DATA / "segments.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 60):
        print(out.drop(columns=["top3"]).to_string(index=False))


if __name__ == "__main__":
    main()
