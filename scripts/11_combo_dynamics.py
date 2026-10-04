"""Step 11: dynamics of every element combination that contains dog or hunting.

Main measure: share of released paid non-AAA games that reached 100+ reviews
(≈ 2–6k copies sold). It counts every game once, so a single hit can't inflate it.
Computed per release year and per half-year; periods too young to have collected
their reviews are flagged as incomplete.

Outputs: data/combo_dynamics.csv (combination × period), data/combo_summary.csv
"""
from itertools import combinations

import pandas as pd

from config import DATA

# "coop" = any co-op (online or local): broader than friendslop, gives combos more data
ELEMENTS = ["dog", "hunting", "coop", "friendslop", "horror", "roguelite", "extraction"]
ANCHORS = {"dog", "hunting"}
EL_RU = {"dog": "собака", "hunting": "охота", "coop": "кооп", "friendslop": "френдслоп",
         "horror": "хоррор", "roguelite": "рогалик", "extraction": "экстракшн"}
FIRST_YEAR = 2019
DATA_DATE = pd.Timestamp("2026-10-04")   # when the Steam data was collected
MATURE_MONTHS = 12                       # periods ending later than this before DATA_DATE are incomplete
SUCCESS, HIT = 100, 1000
MIN_GAMES = 15                           # fewer games in 2022+ -> "too little data"


def load():
    df = pd.read_csv(DATA / "games.csv")
    for c in [c for c in df.columns if c.startswith("el_")] + ["is_aaa", "released"]:
        df[c] = df[c].astype(bool)
    df["el_coop"] = df.tags.fillna("").str.contains(r"(?:^|, )(?:Co-op|Online Co-Op)(?:,|$)")
    df = df[df.released & ~df.is_aaa & df.price_usd.notna()].copy()
    df["date"] = pd.to_datetime(df.release_text, format="%b %d, %Y", errors="coerce")
    df["date"] = df.date.fillna(pd.to_datetime(df.release_year.astype("Int64").astype(str) + "-07-01",
                                               errors="coerce"))
    df = df[df.date.dt.year >= FIRST_YEAR]
    df["year"] = df.date.dt.year
    df["half"] = df.year.astype(str) + "-H" + ((df.date.dt.month > 6) + 1).astype(str)
    return df


def period_end(label):
    if "-H" in label:
        y, h = label.split("-H")
        return pd.Timestamp(f"{y}-{'06-30' if h == '1' else '12-31'}")
    return pd.Timestamp(f"{label}-12-31")


def stats(g):
    rev = g.reviews_total
    return {"games": len(g),
            "pct_100plus": round(100 * (rev >= SUCCESS).mean(), 1) if len(g) else None,
            "pct_1000plus": round(100 * (rev >= HIT).mean(), 1) if len(g) else None,
            "median_reviews": float(rev.median()) if len(g) else None}


def combos():
    for k in (1, 2, 3):
        for c in combinations(ELEMENTS, k):
            if ANCHORS & set(c):
                yield c


def main():
    df = load()
    up = pd.read_csv(DATA / "games.csv")
    up = up[up.coming_soon.astype(bool) & ~up.is_aaa.astype(bool) & up.release_year.isin([2026, 2027])].copy()
    up["el_coop"] = up.tags.fillna("").str.contains(r"(?:^|, )(?:Co-op|Online Co-Op)(?:,|$)")
    dyn, summ = [], []
    for c in combos():
        label = " + ".join(EL_RU[e] for e in c)
        mask = pd.Series(True, index=df.index)
        for e in c:
            mask &= df[f"el_{e}"]
        g = df[mask]
        if len(g) == 0:
            continue
        for kind, col in (("year", "year"), ("half", "half")):
            for per, gp in g.groupby(col):
                per = str(per)
                dyn.append({"combo": label, "n_elements": len(c), "period_type": kind, "period": per,
                            "incomplete": period_end(per) > DATA_DATE - pd.DateOffset(months=MATURE_MONTHS),
                            **stats(gp)})
        recent = g[g.year >= 2022]
        mature = recent[recent.date <= DATA_DATE - pd.DateOffset(months=MATURE_MONTHS)]
        early, late = mature[mature.year <= 2023], mature[mature.year >= 2024]
        rev = recent.reviews_total.sort_values(ascending=False)
        top3 = recent.sort_values("reviews_total", ascending=False).head(3)
        s_early, s_late = stats(early)["pct_100plus"], stats(late)["pct_100plus"]
        if len(recent) < MIN_GAMES:
            trend = "мало данных"
        elif len(early) < 8 or len(late) < 8:
            trend = "мало данных для тренда"
        elif s_late >= s_early * 1.25 and s_late - s_early >= 5:
            trend = "растёт"
        elif s_late <= s_early * 0.75 and s_early - s_late >= 5:
            trend = "падает"
        else:
            trend = "стабильно"
        up_mask = pd.Series(True, index=up.index)
        for e in c:
            up_mask &= up[f"el_{e}"].astype(bool)
        summ.append({
            "combo": label, "n_elements": len(c),
            "games_2022plus": len(recent),
            "pct_100plus_2022plus": stats(recent)["pct_100plus"],
            "pct_1000plus_2022plus": stats(recent)["pct_1000plus"],
            "median_reviews_2022plus": stats(recent)["median_reviews"],
            "pct_100plus_2022_23": s_early, "games_2022_23": len(early),
            "pct_100plus_2024_25": s_late, "games_2024_25": len(late),
            "trend": trend,
            "top3_share_of_reviews": round(100 * rev.head(3).sum() / rev.sum(), 1) if rev.sum() else None,
            "reviews_without_top3": int(rev.iloc[3:].sum()),
            "top3": "; ".join(f"{n} ({r})" for n, r in zip(top3.name, top3.reviews_total)),
            "announced_2026_27": int(up_mask.sum()),
            "games_all_since_2019": len(g),
        })
    pd.DataFrame(dyn).to_csv(DATA / "combo_dynamics.csv", index=False)
    s = pd.DataFrame(summ)
    s.to_csv(DATA / "combo_summary.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 70):
        print(s.drop(columns=["top3"]).to_string(index=False))


if __name__ == "__main__":
    main()
