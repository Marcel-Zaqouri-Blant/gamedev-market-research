"""Step 10: what else people at each intersection review (public Steam profiles).

  python 10_profiles.py collect [--per-group 120] [--max-pages 5]
  python 10_profiles.py tags       # Steam store tags for games outside our dataset
  python 10_profiles.py analyze

Groups: for every pair containing dog or hunting, a random sample of crossover
people (reviewed games of both elements, hybrids excluded); plus a control group
per element (random reviewers of that element's games). Comparing a crossover
group with the two controls shows which side "outweighs" in those people.

Each person's public review list (steamcommunity.com/profiles/<id>/recommended)
is read, up to --max-pages × 10 latest reviews. Reviews of the games a person
was sampled through are dropped, otherwise they would create the lean by themselves.

Personal data (Steam IDs, review lists) stays in data/raw/profiles/ (gitignored);
only aggregates are written to data/.
"""
import argparse
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import product

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

import importlib
from config import DATA, ELEMENT_TAGS, RAW

ov = importlib.import_module("07_audience_overlap")

PROF = RAW / "profiles"
USERS = PROF / "users.jsonl"
GROUPS = PROF / "groups.json"
TAGS_EXTRA = RAW / "profile_game_tags.csv"
ANCHORS = ["dog", "hunting"]
OTHERS = ["hunting", "friendslop", "horror", "roguelite", "extraction"]
ELEMENTS = ["dog", "hunting", "friendslop", "horror", "roguelite", "extraction"]
EL_RU = {"dog": "собака", "hunting": "охота", "friendslop": "френдслоп",
         "horror": "хоррор", "roguelite": "рогалик", "extraction": "экстракшн"}

_lock = threading.Lock()
_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 (market research script)"


def pairs():
    return [(a, b) for a, b in product(ANCHORS, OTHERS) if a != b and not (a == "hunting" and b == "dog")]


# ---------------------------------------------------------------- groups
def build_groups(per_group, seed=0):
    g = ov.load_games()
    sets = ov.drop_heavy({a: s for a, s in ov.load_cache(False).items() if a in set(g.appid)})
    g = g[g.appid.isin(sets)]
    members = {e: set(g.appid[g[f"el_{e}"]]) for e in ELEMENTS}
    rng = np.random.default_rng(seed)
    groups = {}
    for a, b in pairs():
        hybrid = members[a] & members[b]
        A = ov.union([sets[i] for i in members[a] - hybrid])
        B = ov.union([sets[i] for i in members[b] - hybrid])
        cross = np.intersect1d(A, B, assume_unique=True)
        pick = rng.choice(cross, size=min(per_group, len(cross)), replace=False)
        groups[f"{a}+{b}"] = sorted(int(x) for x in pick)
    for e in ELEMENTS:
        pool = ov.union([sets[i] for i in members[e]])
        pick = rng.choice(pool, size=min(per_group, len(pool)), replace=False)
        groups[f"control:{e}"] = sorted(int(x) for x in pick)
    return groups


# ---------------------------------------------------------------- collect
def get(url, **params):
    for attempt in range(8):
        try:
            r = _s.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(min(60, 2 ** attempt))
    return None


def parse_page(html):
    s = BeautifulSoup(html, "html.parser")
    if s.select_one(".profile_private_info"):
        return "private", 0, []
    info = s.select_one(".workshopBrowsePagingInfo")
    m = re.search(r"of\s+([\d,]+)", info.get_text()) if info else None
    total = int(m.group(1).replace(",", "")) if m else 0
    out = []
    for box in s.select(".review_box"):
        a = box.select_one(".leftcol a[href*='/app/']")
        if not a:
            continue
        appid = int(re.search(r"/app/(\d+)", a["href"]).group(1))
        title = box.select_one(".title")
        hours = box.select_one(".hours")
        h = re.search(r"([\d,.]+)\s*hrs", hours.get_text()) if hours else None
        out.append([appid, bool(title and "Not" not in title.get_text()),
                    float(h.group(1).replace(",", "")) if h else None])
    return "public", total, out


def fetch_user(acc, max_pages):
    sid = acc + ov.STEAMID64_BASE
    url = f"https://steamcommunity.com/profiles/{sid}/recommended/"
    r = get(url, p=1)
    if r is None:
        rec = {"acc": acc, "status": "error"}
    else:
        status, total, reviews = parse_page(r.text)
        for p in range(2, min(max_pages, math.ceil(total / 10)) + 1):
            rp = get(url, p=p)
            if rp is None:
                break
            reviews += parse_page(rp.text)[2]
        rec = {"acc": acc, "status": status, "total": total, "reviews": reviews}
    with _lock, USERS.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def load_users():
    users = {}
    if USERS.exists():
        for line in USERS.open():
            try:
                u = json.loads(line)
            except json.JSONDecodeError:
                continue
            if u.get("status") != "error":
                users[u["acc"]] = u
    return users


def cmd_collect(args):
    PROF.mkdir(parents=True, exist_ok=True)
    if not GROUPS.exists() or args.rebuild:
        GROUPS.write_text(json.dumps(build_groups(args.per_group)))
    groups = json.loads(GROUPS.read_text())
    everyone = sorted({a for v in groups.values() for a in v})
    done = set(load_users())
    todo = [a for a in everyone if a not in done]
    print(f"groups: {len(groups)}  people: {len(everyone)}  to fetch: {len(todo)}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(args.workers) as ex:
        for n, _ in enumerate(ex.map(lambda a: fetch_user(a, args.max_pages), todo), 1):
            if n % 100 == 0 or n == len(todo):
                print(f"{n}/{len(todo)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    print("finished", flush=True)


# ---------------------------------------------------------------- tags
def game_tags():
    """appid -> set of tag names, from our dataset plus SteamSpy extras."""
    tags = {}
    g = pd.read_csv(DATA / "games.csv", usecols=["appid", "tags"])
    for a, t in zip(g.appid, g.tags.fillna("")):
        tags[a] = {x.strip() for x in t.split(",") if x.strip()}
    if TAGS_EXTRA.exists():
        e = pd.read_csv(TAGS_EXTRA)
        for a, t in zip(e.appid, e.tags.fillna("")):
            tags.setdefault(a, {x.strip() for x in t.split("|") if x.strip()})
    return tags


def cmd_tags(args):
    """Tags for every game in the profiles that our dataset doesn't cover (Steam store API, 100 per call)."""
    users = load_users()
    counts = pd.Series([r[0] for u in users.values() for r in u.get("reviews", [])]).value_counts()
    known = set(game_tags())
    todo = [int(a) for a, c in counts.items() if c >= args.min_people and a not in known]
    print(f"games in profiles missing tags: {len(todo)}")
    names = {t["tagid"]: t["name"] for t in
             get("https://store.steampowered.com/tagdata/populartags/english").json()}
    rows = pd.read_csv(TAGS_EXTRA).to_dict("records") if TAGS_EXTRA.exists() else []
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        req = {"ids": [{"appid": a} for a in chunk],
               "context": {"language": "english", "country_code": "US"},
               "data_request": {"include_tag_count": 20}}
        r = get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/",
                input_json=json.dumps(req))
        items = (r.json().get("response", {}).get("store_items", []) if r is not None else [])
        for it in items:
            tagids = [t["tagid"] for t in sorted(it.get("tags", []), key=lambda t: -t.get("weight", 0))]
            rows.append({"appid": it.get("appid", it.get("id")), "name": it.get("name", ""),
                         "tags": "|".join(names[t] for t in tagids if t in names)})
        if (i // 100) % 20 == 0:
            print(f"{i + len(chunk)}/{len(todo)}", flush=True)
        time.sleep(0.5)
    pd.DataFrame(rows).drop_duplicates("appid").to_csv(TAGS_EXTRA, index=False)
    print("done")


# ---------------------------------------------------------------- analyze
def element_of(tagset):
    out = {e: bool(tagset & ELEMENT_TAGS[e]) for e in ("dog", "hunting", "horror", "roguelite", "extraction")}
    out["friendslop"] = ("Online Co-Op" in tagset
                         and bool(tagset & (ELEMENT_TAGS["comedy"] | ELEMENT_TAGS["physics"] | ELEMENT_TAGS["party"]))
                         and "Massively Multiplayer" not in tagset)
    return out


def cmd_analyze(args):
    groups = json.loads(GROUPS.read_text())
    users = load_users()
    sets = ov.load_cache(False)
    tags = game_tags()
    names = pd.read_csv(DATA / "games.csv", usecols=["appid", "name"]).set_index("appid").name.to_dict()
    if TAGS_EXTRA.exists():
        extra = pd.read_csv(TAGS_EXTRA)
        names.update({a: n for a, n in zip(extra.appid, extra.name) if a not in names})
    el_cache = {}

    def els(appid):
        if appid not in el_cache:
            el_cache[appid] = element_of(tags[appid]) if appid in tags else None
        return el_cache[appid]

    def other_reviews(acc):
        """Reviews minus the games this person was sampled through."""
        u = users.get(acc)
        if not u or u["status"] != "public":
            return None
        return [r for r in u["reviews"] if not (r[0] in sets and ov.count_in(sets[r[0]], np.array([acc], np.uint32)))]

    share_rows, game_rows = [], []
    pooled = {}  # all sampled public people: appid -> people count, for the "what else" baseline
    per_group_games = {}
    for gname, accs in groups.items():
        revs = {a: other_reviews(a) for a in accs}
        public = {a: r for a, r in revs.items() if r}
        n_known = n_total = 0
        el_count = {e: 0 for e in ELEMENTS}
        el_people = {e: 0 for e in ELEMENTS}  # people with at least one other game of the element
        for a, rs in public.items():
            has = set()
            for appid, _, _ in rs:
                n_total += 1
                e = els(appid)
                if e is None:
                    continue
                n_known += 1
                for k, v in e.items():
                    el_count[k] += v
                    if v:
                        has.add(k)
            for k in has:
                el_people[k] += 1
        row = {"group": gname, "sampled": len(accs),
               "public_with_reviews": len(public),
               "avg_other_reviews": round(n_total / len(public), 1) if public else None,
               "reviews_with_tags_pct": round(100 * n_known / n_total, 1) if n_total else None}
        for e in ELEMENTS:
            row[f"share_{e}"] = round(100 * el_count[e] / n_known, 1) if n_known else None
        for e in ELEMENTS:
            row[f"people_{e}"] = round(100 * el_people[e] / len(public), 1) if public else None
        share_rows.append(row)
        people = pd.Series([appid for rs in public.values() for appid in {r[0] for r in rs}]).value_counts()
        per_group_games[gname] = (people, len(public))
        if not gname.startswith("control:"):
            for appid, c in people.items():
                pooled[appid] = pooled.get(appid, 0) + c
    shares = pd.DataFrame(share_rows)
    shares.to_csv(DATA / "profiles_element_shares.csv", index=False)

    # "what else": per crossover group, games reviewed by many of its people, vs all controls
    ctrl_people = pd.Series(dtype=float)
    ctrl_n = 0
    for gname, (people, n) in per_group_games.items():
        if gname.startswith("control:"):
            ctrl_people = ctrl_people.add(people, fill_value=0)
            ctrl_n += n
    for gname, (people, n) in per_group_games.items():
        if gname.startswith("control:") or not n:
            continue
        for appid, c in people.items():
            if c < args.min_people:
                continue
            base = ctrl_people.get(appid, 0) / ctrl_n if ctrl_n else 0
            e = els(appid) or {}
            game_rows.append({"group": gname, "appid": appid, "name": names.get(appid, ""),
                              "people": int(c), "pct_of_group": round(100 * c / n, 1),
                              "pct_of_controls": round(100 * base, 2),
                              "lift_vs_controls": round((c / n) / base, 2) if base else None,
                              "elements": ", ".join(EL_RU[k] for k, v in e.items() if v)})
    games = pd.DataFrame(game_rows).sort_values(["group", "people"], ascending=[True, False])
    games.to_csv(DATA / "profiles_top_games.csv", index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print(shares.to_string(index=False))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--per-group", type=int, default=120)
    c.add_argument("--max-pages", type=int, default=5)
    c.add_argument("--workers", type=int, default=2)
    c.add_argument("--rebuild", action="store_true", help="re-sample groups")
    t = sub.add_parser("tags")
    t.add_argument("--min-people", type=int, default=1)
    a = sub.add_parser("analyze")
    a.add_argument("--min-people", type=int, default=5)
    args = p.parse_args()
    {"collect": cmd_collect, "tags": cmd_tags, "analyze": cmd_analyze}[args.cmd](args)


if __name__ == "__main__":
    main()
