"""Step 15: quality of success, price and player count for small-scope co-op games.

  python 15_quality.py collect   # store pages, prices, review samples, review histograms
  python 15_quality.py youtube   # YouTube views for the top games of each direction (quota!)
  python 15_quality.py analyze   # data/quality_*.csv, data/quality.xlsx

Games: small-scope co-op base from 14_coop_market.py (no big-production tags).
For every game: base price (appdetails) and max player count parsed from the store
description. For games with 100+ reviews also:
  - longevity: share of first-year reviews that came after the first 3 months;
  - playtime: median hours played by 100 recent reviewers;
  - geography: review languages of the same 100 reviewers;
  - watchability: YouTube views of top videos per Steam review (subset, quota-limited).
"""
import argparse
import importlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import DATA, RAW

cm = importlib.import_module("14_coop_market")

OUT = RAW / "quality"
PAGES = OUT / "store.jsonl"
REVS = OUT / "reviews.jsonl"
PRICES = OUT / "prices.csv"
COOKIES = {"birthtime": "0", "lastagecheckage": "1-0-1990", "wants_mature_content": "1"}

_lock = threading.Lock()
_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 (market research script)"
_s.cookies.update(COOKIES)


def get(url, **params):
    for attempt in range(9):
        try:
            r = _s.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(min(60, 2 ** attempt))
    return None


def small_base():
    _, base = cm.load_base()
    return base[base.top_tags.apply(lambda s: not (s & cm.BIG_SCOPE))].copy()


# ---------------------------------------------------------------- players
WORD_NUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "ten": 10, "twelve": 12, "sixteen": 16}
NUM = r"(\d{1,3}|" + "|".join(WORD_NUM) + r")"
# (pattern, add): "with 3 friends" means 4 players, hence add=1 for friends / teammates
PLAYER_PATTERNS = [
    (rf"up\s+to\s+{NUM}\s+(?:\w+\s+){{0,2}}(?:players|people)", 0),
    (rf"up\s+to\s+{NUM}\s+(?:\w+\s+){{0,2}}(?:friends|crewmates|teammates)", 1),
    (rf"{NUM}\s*(?:-|–|—|to)\s*{NUM}\s+(?:\w+\s+)?players", 0),
    (rf"{NUM}[\s-]*player\b", 0),
    (rf"(?:squad|team|group|party|crew)\s+of\s+(?:up\s+to\s+)?{NUM}", 0),
    (rf"{NUM}\s+players", 0),
    (rf"(?:with|and)\s+{NUM}\s+(?:\w+\s+)?(?:friends|crewmates|teammates)", 1),
]


def to_int(x):
    x = x.lower()
    return WORD_NUM.get(x) or (int(x) if x.isdigit() else None)


def max_players(text):
    """Largest plausible player count mentioned in the description (2..64), or None."""
    found = []
    for pat, add in PLAYER_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            for g in m.groups():
                n = to_int(g) if g else None
                if n:
                    n += add
                if n and 2 <= n <= 64:
                    found.append(n)
    return max(found) if found else None


# ---------------------------------------------------------------- collect
def fetch_store(appid):
    r = get(f"https://store.steampowered.com/app/{appid}/", l="english", cc="us")
    rec = {"appid": appid}
    if r is None or f"/app/{appid}" not in r.url:
        rec["error"] = "unavailable"
    else:
        s = BeautifulSoup(r.text, "html.parser")
        desc = s.select_one("#game_area_description")
        snip = s.select_one(".game_description_snippet")
        text = " ".join(x.get_text(" ", strip=True) for x in (snip, desc) if x)
        rec["max_players"] = max_players(text)
        rec["desc_len"] = len(text)
        rec["has_demo"] = bool(s.select_one(".demo_above_purchase, #demoGameBtn"))
    with _lock, PAGES.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def fetch_reviews(appid):
    rec = {"appid": appid}
    r = get(f"https://store.steampowered.com/appreviews/{appid}", json=1, num_per_page=100,
            language="all", purchase_type="all", filter="recent", cursor="*")
    if r is not None:
        revs = r.json().get("reviews", [])
        rec["playtime_h"] = [round(x["author"].get("playtime_forever", 0) / 60, 1) for x in revs]
        rec["languages"] = [x.get("language", "") for x in revs]
    h = get(f"https://store.steampowered.com/appreviewhistogram/{appid}",
            l="english", review_score_preference=0)
    if h is not None:
        res = h.json().get("results", {})
        rec["hist"] = [[x["date"], x["recommendations_up"] + x["recommendations_down"]]
                       for x in res.get("rollups", [])]
    with _lock, REVS.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def done_ids(path):
    return {json.loads(l)["appid"] for l in path.open()} if path.exists() else set()


def cmd_collect(args):
    OUT.mkdir(parents=True, exist_ok=True)
    small = small_base()
    ids = small.appid.tolist()
    if not PRICES.exists():
        rows = []
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            r = get("https://store.steampowered.com/api/appdetails",
                    appids=",".join(map(str, chunk)), filters="price_overview", cc="us")
            for a, v in (r.json() if r is not None else {}).items():
                po = (v.get("data") or {}).get("price_overview") if isinstance(v.get("data"), dict) else None
                rows.append({"appid": int(a), "price_usd": po["initial"] / 100 if po else None})
            time.sleep(1.5)
        pd.DataFrame(rows).to_csv(PRICES, index=False)
        print(f"prices: {len(rows)}", flush=True)
    todo_pages = [a for a in ids if a not in done_ids(PAGES)]
    big = small[small.reviews >= 100].appid.tolist()
    todo_revs = [a for a in big if a not in done_ids(REVS)]
    print(f"store pages to fetch: {len(todo_pages)}  review samples to fetch: {len(todo_revs)}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(args.workers) as ex:
        for n, _ in enumerate(ex.map(fetch_reviews, todo_revs), 1):
            if n % 100 == 0:
                print(f"reviews {n}/{len(todo_revs)}  {(time.time() - t0) / 60:.1f} min", flush=True)
        for n, _ in enumerate(ex.map(fetch_store, todo_pages), 1):
            if n % 200 == 0:
                print(f"pages {n}/{len(todo_pages)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    print("finished", flush=True)


# ---------------------------------------------------------------- youtube
def cmd_youtube(args):
    """Search YouTube for the biggest 100+ review games of each direction (cached, quota-limited)."""
    yt = importlib.import_module("08_creators")
    small = small_base()
    hits = small[small.reviews >= 100]
    picks = {}
    for label, f in cm.SMALL_CHECKS:
        g = hits[hits.top_tags.apply(f)].sort_values("reviews", ascending=False)
        # mid-market: skip mega-hits, they would dominate the per-direction figure
        g = g[g.reviews < 50_000].head(args.per_direction)
        for a, n in zip(g.appid, g.name):
            picks[a] = n
    quota = yt.Quota(args.budget)
    rows = []
    for appid, name in picks.items():
        try:
            res = yt.call("search", {"part": "snippet", "q": f'"{name}" game', "type": "video",
                                     "order": "viewCount", "maxResults": 50, "videoCategoryId": 20}, quota)
        except RuntimeError as e:
            print("stopped:", e)
            break
        vids = [it["id"]["videoId"] for it in res.get("items", [])
                if yt.mentions(name, it["snippet"]["title"], it["snippet"].get("description", ""))]
        views = 0
        for ch in yt.chunks(vids):
            st = yt.call("videos", {"part": "statistics", "id": ",".join(ch)}, quota)
            views += sum(int(i["statistics"].get("viewCount", 0)) for i in st.get("items", []))
        rows.append({"appid": appid, "name": name, "videos_matched": len(vids), "views_top50": views})
    pd.DataFrame(rows).to_csv(OUT / "youtube.csv", index=False)
    print(f"games: {len(rows)}  quota used: {quota.used}")


# ---------------------------------------------------------------- analyze
LANG_RU = {"english": "английский", "russian": "русский", "schinese": "китайский (упр.)",
           "brazilian": "португальский (Бразилия)", "spanish": "испанский (Испания)",
           "latam": "испанский (Лат. Америка)", "german": "немецкий", "french": "французский",
           "polish": "польский", "turkish": "турецкий", "koreana": "корейский", "japanese": "японский",
           "tchinese": "китайский (трад.)", "ukrainian": "украинский", "thai": "тайский", "italian": "итальянский"}


def longevity(hist, release_ts):
    """Share of first-year reviews that arrived after the first 3 months."""
    if not hist or not release_ts:
        return None
    t3, t12 = release_ts + 91 * 86400, release_ts + 365 * 86400
    first_year = sum(n for d, n in hist if d < t12)
    if first_year < 20:
        return None
    later = sum(n for d, n in hist if t3 <= d < t12)
    return round(100 * later / first_year, 1)


def load_joined():
    small = small_base()
    pages = pd.DataFrame([json.loads(l) for l in PAGES.open()]).drop_duplicates("appid") if PAGES.exists() else pd.DataFrame(columns=["appid"])
    revs = {json.loads(l)["appid"]: json.loads(l) for l in REVS.open()} if REVS.exists() else {}
    prices = pd.read_csv(PRICES) if PRICES.exists() else pd.DataFrame(columns=["appid", "price_usd"])
    df = small.merge(pages, on="appid", how="left").merge(prices, on="appid", how="left")
    df["release_ts"] = (df.date - pd.Timestamp("1970-01-01")).dt.total_seconds().astype("int64")
    df["longevity_pct"] = [longevity(revs.get(a, {}).get("hist"), ts) for a, ts in zip(df.appid, df.release_ts)]
    df["playtime_median_h"] = [float(np.median(revs[a]["playtime_h"])) if revs.get(a, {}).get("playtime_h") else None
                               for a in df.appid]
    df["languages"] = [revs.get(a, {}).get("languages") for a in df.appid]
    yt = OUT / "youtube.csv"
    if yt.exists():
        y = pd.read_csv(yt)[["appid", "views_top50"]]
        df = df.merge(y, on="appid", how="left")
        df["views_per_review"] = (df.views_top50 / df.reviews).round(0)
    return df


def price_bucket(p):
    if pd.isna(p):
        return None
    return ("до $5" if p < 5 else "$5–9.99" if p < 10 else "$10–14.99" if p < 15
            else "$15–19.99" if p < 20 else "$20+")


def players_bucket(n):
    if pd.isna(n):
        return "не указано"
    return "2" if n <= 2 else "3–4" if n <= 4 else "5–8" if n <= 8 else "9+"


def cmd_analyze(args):
    df = load_joined()
    hits = df[df.reviews >= 100]
    avg = cm.rate(df)
    print(f"small-scope games: {len(df)}  with 100+: {len(hits)}  overall 100+ = {avg}%")

    # 1. quality of success per direction (among games that reached 100+)
    rows = []
    for label, f in cm.SMALL_CHECKS:
        g = hits[hits.top_tags.apply(f)]
        if not len(g):
            continue
        langs = pd.Series([l for ls in g.languages.dropna() for l in ls])
        top_langs = (langs.value_counts(normalize=True) * 100).round(0).head(4)
        rows.append({
            "direction": label, "games_100plus": len(g),
            "longevity_median_pct": g.longevity_pct.median(),
            "playtime_median_h": g.playtime_median_h.median(),
            "views_per_review_median": g.views_per_review.median() if "views_per_review" in g else None,
            "youtube_games": int(g.views_per_review.notna().sum()) if "views_per_review" in g else 0,
            "english_pct": round(100 * (langs == "english").mean(), 0) if len(langs) else None,
            "top_languages": ", ".join(f"{LANG_RU.get(k, k)} {int(v)}%" for k, v in top_langs.items()),
            "median_price": g.price_usd.median(),
        })
    q = pd.DataFrame(rows)
    order = [label for label, _ in cm.SMALL_CHECKS]
    q["o"] = q.direction.map(order.index)
    q = q.sort_values("o").drop(columns="o")
    q.to_csv(DATA / "quality_directions.csv", index=False)

    # 2. price
    df["price_bucket"] = df.price_usd.apply(price_bucket)
    pr = []
    for b in ["до $5", "$5–9.99", "$10–14.99", "$15–19.99", "$20+"]:
        g = df[df.price_bucket == b]
        lo, hi = cm.wilson(int((g.reviews >= 100).sum()), len(g))
        pr.append({"price": b, "games": len(g), "pct_100plus": cm.rate(g), "ci_low": lo, "ci_high": hi,
                   "pct_1000plus": cm.rate(g, thr=1000), "median_reviews": g.reviews.median()})
    pr = pd.DataFrame(pr)
    pr.to_csv(DATA / "quality_price.csv", index=False)

    # 3. players
    df["players_bucket"] = df.max_players.apply(players_bucket)
    pl = []
    for b in ["2", "3–4", "5–8", "9+", "не указано"]:
        g = df[df.players_bucket == b]
        lo, hi = cm.wilson(int((g.reviews >= 100).sum()), len(g))
        online = g.top_tags.apply(lambda s: "Online Co-Op" in s).mean() * 100 if len(g) else None
        pl.append({"players": b, "games": len(g), "pct_100plus": cm.rate(g), "ci_low": lo, "ci_high": hi,
                   "pct_1000plus": cm.rate(g, thr=1000), "online_coop_pct": round(online, 0) if online is not None else None,
                   "examples": "; ".join(g.sort_values("reviews", ascending=False).name.head(4))})
    pl = pd.DataFrame(pl)
    pl.to_csv(DATA / "quality_players.csv", index=False)
    df.drop(columns=["languages", "top_tags", "all_tags"]).to_csv(DATA / "quality_games.csv", index=False)
    comps = build_comps(df)
    export(q, pr, pl, comps, df)
    with pd.option_context("display.width", 250, "display.max_colwidth", 80):
        print(q.to_string(index=False)); print(); print(pr.to_string(index=False)); print(); print(pl.to_string(index=False))


TENSION = {"Stealth", "Survival", "Horror", "Psychological Horror", "Survival Horror"}


def build_comps(df):
    """Mid-market references for the recommended direction: online co-op + tension or nature theme."""
    f = df[df.top_tags.apply(lambda s: "Online Co-Op" in s)
           & (df.top_tags.apply(lambda s: bool(s & TENSION)) | df.all_tags.apply(lambda s: bool(s & cm.THEME)))
           & df.reviews.between(200, 20_000)].copy()
    f["themed"] = f.all_tags.apply(lambda s: bool(s & cm.THEME))
    f["sales_low"], f["sales_high"] = f.reviews * 20, f.reviews * 60
    f["url"] = "https://store.steampowered.com/app/" + f.appid.astype(str) + "/"
    f["tags10"] = f.tags.apply(lambda t: ", ".join(t[:10]))
    f["year"] = f.date.dt.year
    # all themed games plus the strongest tension games, 30 rows in total
    themed = f[f.themed].sort_values("reviews", ascending=False)
    rest = f[~f.themed].sort_values("reviews", ascending=False).head(max(0, 30 - len(themed)))
    out = pd.concat([themed, rest]).sort_values("reviews", ascending=False)
    cols = ["name", "year", "price_usd", "reviews", "positive_pct", "sales_low", "sales_high",
            "playtime_median_h", "longevity_pct", "max_players", "early_access", "themed", "tags10", "url"]
    if "views_per_review" in out:
        cols.insert(10, "views_per_review")
    out[cols].to_csv(DATA / "quality_comps.csv", index=False)
    return out[cols]


def export(q, pr, pl, comps, df):
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    legend = pd.DataFrame([
        ("Выборка", f"«Небольшие» кооп-игры Steam 2022 – 2025 (без тегов крафта, строительства, открытого мира, "
                    f"симуляторов, RPG, стратегий, MMO среди главных), платные, без AAA: {len(df)} игр, "
                    f"из них 100+ отзывов у {int((df.reviews >= 100).sum())}."),
        ("Долгоиграемость", "Какая доля отзывов первого года пришла после первых 3 месяцев. "
                            "Выше = игра продаётся дольше, а не сгорает на старте."),
        ("Игровое время", "Медиана часов в игре у 100 последних авторов отзывов (медиана по играм направления)."),
        ("Просмотры на отзыв", "Просмотры 50 самых популярных роликов YouTube об игре ÷ число отзывов в Steam. "
                               "Сколько бесплатного охвата приходится на одну продажу. Посчитано для 46 игр "
                               "(лимит YouTube), поэтому это ориентир."),
        ("Языки", "Языки отзывов у тех же 100 авторов — где живут игроки."),
        ("Цена", "Базовая цена в долларах без скидки."),
        ("Игроки", "Максимальное число игроков из описания игры в Steam («up to 4 players», «1–6 players»). "
                   "«не указано» — в описании нет числа."),
        ("Продажи ≈", "Отзывы × 20 … × 60."),
    ], columns=["Что", "Пояснение"])
    qn = q.rename(columns={"direction": "Направление", "games_100plus": "Игр со 100+",
                           "longevity_median_pct": "Долгоиграемость, %", "playtime_median_h": "Игровое время, ч",
                           "views_per_review_median": "Просмотры на отзыв", "youtube_games": "Игр с YouTube",
                           "english_pct": "Английский, %", "top_languages": "Главные языки",
                           "median_price": "Медианная цена, $"})
    prn = pr.rename(columns={"price": "Цена", "games": "Игр", "pct_100plus": "Набрали 100+, %",
                             "ci_low": "Интервал от", "ci_high": "Интервал до", "pct_1000plus": "Набрали 1000+, %",
                             "median_reviews": "Медиана отзывов"})
    pln = pl.rename(columns={"players": "Игроков", "games": "Игр", "pct_100plus": "Набрали 100+, %",
                             "ci_low": "Интервал от", "ci_high": "Интервал до", "pct_1000plus": "Набрали 1000+, %",
                             "online_coop_pct": "С онлайн-коопом, %", "examples": "Примеры"})
    cn = comps.rename(columns={"name": "Игра", "year": "Год", "price_usd": "Цена, $", "reviews": "Отзывы",
                               "positive_pct": "% положит.", "sales_low": "Продажи ≈ от", "sales_high": "Продажи ≈ до",
                               "playtime_median_h": "Игровое время, ч", "longevity_pct": "Долгоиграемость, %",
                               "max_players": "Игроков", "views_per_review": "Просмотры на отзыв",
                               "early_access": "Ранний доступ", "themed": "Природа / животные / охота",
                               "tags10": "Главные теги", "url": "Ссылка"})
    for c in ("Ранний доступ", "Природа / животные / охота"):
        cn[c] = cn[c].map({True: "да", False: ""})
    with pd.ExcelWriter(DATA / "quality.xlsx", engine="openpyxl") as w:
        for name, d, widths in (("Пояснения", legend, {"Что": 20, "Пояснение": 130}),
                                ("Качество успеха", qn, {"Направление": 30, "Главные языки": 70}),
                                ("Цена", prn, {}), ("Игроки", pln, {"Примеры": 80}),
                                ("Ориентиры", cn, {"Игра": 36, "Главные теги": 80, "Ссылка": 45})):
            d.to_excel(w, sheet_name=name, index=False)
            ws = w.sheets[name]
            ws.freeze_panes = "B2"
            ws.auto_filter.ref = ws.dimensions
            for i, c in enumerate(d.columns, 1):
                ws.column_dimensions[get_column_letter(i)].width = widths.get(c, 14)
                ws.cell(1, i).font = Font(bold=True)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--workers", type=int, default=3)
    y = sub.add_parser("youtube")
    y.add_argument("--per-direction", type=int, default=6)
    y.add_argument("--budget", type=int, default=5000)
    sub.add_parser("analyze")
    args = p.parse_args()
    {"collect": cmd_collect, "youtube": cmd_youtube, "analyze": cmd_analyze}[args.cmd](args)


if __name__ == "__main__":
    main()
