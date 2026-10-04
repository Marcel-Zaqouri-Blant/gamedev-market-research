"""Step 7: audience overlap between segments via Steam review authors.

  python 07_audience_overlap.py estimate              # how many requests `collect` needs
  python 07_audience_overlap.py collect [--cap 1000] [--limit N] [--appids 1,2]
  python 07_audience_overlap.py analyze [--positive-only]

collect: downloads review authors per game into data/raw/reviewers/ (local cache,
         NOT committed: Steam IDs are personal data). Resumable; at most --cap
         most recent reviews per game (default 500), so a single hit can't dominate a segment.
analyze: for every pair of segments A, B counts reviewers who reviewed games of
         both. Games that belong to both A and B are dropped from the pair,
         otherwise one hunting-friendslop game would create the overlap by itself.
         lift compares that with how often reviewers of other games in the sample
         reach the segment (see pair_overlaps); then profiles what else people at
         chosen intersections review (see affinity).

Outputs (aggregates only): data/audience_overlap.csv, data/audience_affinity.csv
"""
import argparse
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations

import numpy as np
import pandas as pd
import requests

from config import DATA, RAW

CACHE = RAW / "reviewers"
META = CACHE / "_meta.jsonl"
STEAMID64_BASE = 76561197960265728  # steamid64 - base = 32-bit account id
PAGE = 100
SEGMENTS = ["dog", "hunting", "friendslop", "horror", "roguelite", "extraction"]
MIN_REVIEWS = 10      # games with fewer reviews add noise, not signal
MIN_OBSERVED = 20     # below this the lift is flagged as unreliable
MIN_PROFILE = 50      # fewer people at an intersection -> no "what else they play" profile

_lock = threading.Lock()
_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0 (market research script)"


# ---------------------------------------------------------------- selection
def load_games():
    df = pd.read_csv(DATA / "games.csv")
    for c in [c for c in df.columns if c.startswith("el_")] + ["is_aaa", "released"]:
        df[c] = df[c].astype(bool)
    sel = df[df.released & ~df.is_aaa & (df.reviews_total >= MIN_REVIEWS)
             & df[[f"el_{s}" for s in SEGMENTS]].any(axis=1)]
    return sel


def pages_needed(reviews, cap):
    return math.ceil(min(reviews, cap) / PAGE)


# ---------------------------------------------------------------- collect
def fetch_page(appid, cursor):
    params = {"json": 1, "num_per_page": PAGE, "language": "all", "purchase_type": "all",
              "filter": "recent", "cursor": cursor}
    for attempt in range(10):
        try:
            r = _session.get(f"https://store.steampowered.com/appreviews/{appid}",
                             params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        # Steam answers 429 to ~1 request in 40: short exponential backoff, capped at 1 min
        time.sleep(min(60, 2 ** attempt))
    return None


def collect_app(appid, cap):
    ids, pos, cursor, seen_cursors, ok, exhausted = [], [], "*", set(), True, False
    while len(ids) < cap:
        d = fetch_page(appid, cursor)
        if d is None or not d.get("success"):
            ok = False
            break
        revs = d.get("reviews", [])
        for r in revs:
            acc = int(r["author"]["steamid"]) - STEAMID64_BASE
            if 0 <= acc < 2 ** 32:  # individual accounts only; guards the uint32 cast
                ids.append(acc)
                pos.append(bool(r.get("voted_up")))
        cursor = d.get("cursor")
        if not revs or not cursor or cursor in seen_cursors:
            exhausted = True  # no more reviews: the game is fully covered
            break
        seen_cursors.add(cursor)
    if not ok and not ids:
        return {"appid": appid, "error": "fetch_failed"}
    ids = np.asarray(ids[:cap], dtype=np.uint32)
    pos = np.asarray(pos[:cap], dtype=bool)
    # one author can't review a game twice, but the cursor can repeat items
    ids, first = np.unique(ids, return_index=True)
    np.savez(CACHE / f"{appid}.npz", ids=ids, pos=pos[first])
    meta = {"appid": appid, "n": int(len(ids)), "complete": ok, "exhausted": exhausted,
            "ts": int(time.time())}
    with _lock, META.open("a") as f:
        f.write(json.dumps(meta) + "\n")
    return meta


def cached_counts():
    """appid -> reviewers in cache (last meta record wins); inf if all reviews were fetched."""
    counts = {}
    if META.exists():
        for line in META.open():
            m = json.loads(line)
            if "n" in m and (CACHE / f"{m['appid']}.npz").exists():
                counts[m["appid"]] = float("inf") if m.get("exhausted") else m["n"]
    return counts


def is_cached(g, cap):
    """A game is done if the cache holds what `cap` asks for (5% slack: reviews get deleted)."""
    have = g.appid.map(cached_counts()).fillna(-1)
    return have >= 0.95 * g.reviews_total.clip(upper=cap)


def cmd_estimate(args):
    g = load_games()
    pages = g.reviews_total.apply(lambda r: pages_needed(r, args.cap))
    todo = ~is_cached(g, args.cap)
    print(f"games: {len(g)}  (already cached: {(~todo).sum()})")
    print(f"requests for remaining games at cap={args.cap}: {pages[todo].sum()}")
    for cap in (300, 500, 1000, 2000, 5000):
        p = g.reviews_total.apply(lambda r: pages_needed(r, cap))[todo].sum()
        print(f"  cap={cap:>5}: {p:>6} requests  ≈ {p / args.rate / 60:5.0f} min at {args.rate}/s")


def cmd_collect(args):
    CACHE.mkdir(parents=True, exist_ok=True)
    g = load_games()
    if args.appids:
        g = g[g.appid.isin([int(x) for x in args.appids.split(",")])]
    g = g[~is_cached(g, args.cap)]
    # small games first: segments fill up evenly instead of waiting for big ones
    g = g.sort_values("reviews_total")
    if args.limit:
        g = g.head(args.limit)
    todo = g.appid.tolist()
    total_pages = g.reviews_total.apply(lambda r: pages_needed(r, args.cap)).sum()
    print(f"collecting {len(todo)} games, ~{total_pages} requests, workers={args.workers}", flush=True)
    t0, done, failed = time.time(), 0, 0
    with ThreadPoolExecutor(args.workers) as ex:
        for meta in ex.map(lambda a: collect_app(a, args.cap), todo):
            done += 1
            failed += "error" in meta
            if done % 100 == 0 or done == len(todo):
                el = time.time() - t0
                print(f"{done}/{len(todo)} games  failed={failed}  {el / 60:.1f} min", flush=True)
    print("finished", flush=True)


# ---------------------------------------------------------------- analyze
def load_cache(positive_only):
    sets = {}
    for p in CACHE.glob("*.npz"):
        z = np.load(p)
        ids = z["ids"][z["pos"]] if positive_only else z["ids"]
        sets[int(p.stem)] = ids  # already sorted & unique
    return sets


def union(arrays):
    return np.unique(np.concatenate(arrays)) if arrays else np.empty(0, np.uint32)


def cmd_analyze(args):
    g = load_games()
    sets = load_cache(args.positive_only)
    g = g[g.appid.isin(sets)]
    sets = {a: s for a, s in sets.items() if a in set(g.appid)}
    universe = union(list(sets.values()))
    _, per_person = np.unique(np.concatenate(list(sets.values())), return_counts=True)
    print(f"games with reviewers: {len(sets)}  unique reviewers: {len(universe)}  "
          f"reviewed 2+ games: {(per_person >= 2).sum()} ({100 * (per_person >= 2).mean():.1f}%)")
    members = {s: set(g.appid[g[f"el_{s}"]]) & set(sets) for s in SEGMENTS}
    suffix = "_positive" if args.positive_only else ""

    pairs = pair_overlaps(sets, members)
    pairs.to_csv(DATA / f"audience_overlap{suffix}.csv", index=False)
    print(pairs.to_string(index=False))

    names = g.set_index("appid").name
    reviews = g.set_index("appid").reviews_total
    aff = []
    for t in args.targets.split(","):
        aff += affinity(tuple(t.split("+")), sets, members, names, reviews)
    if aff:
        aff = (pd.DataFrame(aff).sort_values(["intersection", "lift"], ascending=[True, False])
               .groupby("intersection").head(args.top))
        aff.to_csv(DATA / f"audience_affinity{suffix}.csv", index=False)
        with pd.option_context("display.width", 220, "display.max_colwidth", 36):
            print(aff.to_string(index=False))


def count_in(sorted_set, ids):
    """How many of `ids` are in `sorted_set` (both sorted unique uint32)."""
    if not len(sorted_set) or not len(ids):
        return 0
    pos = np.searchsorted(sorted_set, ids)
    pos[pos == len(sorted_set)] = 0
    return int((sorted_set[pos] == ids).sum())


def pair_overlaps(sets, members):
    """Overlap of segment audiences, compared with a within-universe baseline.

    lift(A→B) = P(reviewed B | reviewed A) / P(reviewed B | reviewed some game outside A∪B).
    The baseline is how often reviewers of *other* games in our sample wander into B,
    so lift 1 = no special affinity, 2 = A's audience goes to B twice as often.
    """
    rows = []
    for a, b in combinations(SEGMENTS, 2):
        only_a, only_b = members[a] - members[b], members[b] - members[a]
        rest = set(sets) - members[a] - members[b]
        A = union([sets[i] for i in only_a])
        B = union([sets[i] for i in only_b])
        R = union([sets[i] for i in rest])
        if not len(A) or not len(B) or not len(R):
            continue
        obs = len(np.intersect1d(A, B, assume_unique=True))
        base_b = len(np.intersect1d(R, B, assume_unique=True)) / len(R)
        base_a = len(np.intersect1d(R, A, assume_unique=True)) / len(R)
        lift_ab = (obs / len(A)) / base_b if base_b else None
        lift_ba = (obs / len(B)) / base_a if base_a else None
        rows.append({
            "segment_a": a, "segment_b": b,
            "games_a": len(only_a), "games_b": len(only_b),
            "reviewers_a": len(A), "reviewers_b": len(B), "overlap": obs,
            "pct_of_a_also_b": round(100 * obs / len(A), 2),
            "pct_of_b_also_a": round(100 * obs / len(B), 2),
            "baseline_pct_b": round(100 * base_b, 2), "baseline_pct_a": round(100 * base_a, 2),
            "lift_a_to_b": round(lift_ab, 2) if lift_ab else None,
            "lift_b_to_a": round(lift_ba, 2) if lift_ba else None,
            "lift": round(math.sqrt(lift_ab * lift_ba), 2) if lift_ab and lift_ba else None,
            # ~95% interval from Poisson noise of the overlap count
            "lift_low": round(math.sqrt(lift_ab * lift_ba) * max(0, 1 - 1.96 / math.sqrt(obs)), 2)
            if obs and lift_ab and lift_ba else None,
            "lift_high": round(math.sqrt(lift_ab * lift_ba) * (1 + 1.96 / math.sqrt(obs)), 2)
            if obs and lift_ab and lift_ba else None,
            "reliable": obs >= MIN_OBSERVED,
        })
    return pd.DataFrame(rows).sort_values("lift", ascending=False)


def affinity(target, sets, members, names, reviews):
    """Which other games the audience at the intersection of `target` reviews.

    core = crossover players (reviewed games of every element, games being different)
         ∪ hybrid players (reviewed a game that already has all target elements).
    Only people who also reviewed something outside the target segments are profiled,
    and the baseline is everyone who reviewed something outside them.
    """
    label = "+".join(target)
    hybrid = set.intersection(*(members[s] for s in target))
    in_target = set.union(*(members[s] for s in target))
    crossover = union([sets[i] for i in members[target[0]] - hybrid])
    for s in target[1:]:
        crossover = np.intersect1d(crossover, union([sets[i] for i in members[s] - hybrid]),
                                   assume_unique=True)
    hybrid_players = union([sets[i] for i in hybrid])
    core = union([crossover, hybrid_players])
    other = union([sets[i] for i in set(sets) - in_target])
    core_obs = np.intersect1d(core, other, assume_unique=True)
    print(f"{label}: crossover={len(crossover)} hybrid_games={len(hybrid)} "
          f"hybrid_players={len(hybrid_players)} core_with_other_reviews={len(core_obs)}")
    if len(core_obs) < MIN_PROFILE:
        print(f"  {label}: too few people to profile — skipped")
        return []
    out = []
    for appid in set(sets) - in_target:
        ids = sets[appid]
        hit = count_in(core_obs, ids)
        if hit < 5:
            continue
        p_core, p_base = hit / len(core_obs), len(ids) / len(other)
        out.append({"intersection": label, "core_profiled": len(core_obs),
                    "appid": appid, "name": names[appid], "game_reviews_total": reviews[appid],
                    "core_who_reviewed": hit, "pct_of_core": round(100 * p_core, 2),
                    "lift": round(p_core / p_base, 2)})
    return out


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("--cap", type=int, default=500)
    e.add_argument("--rate", type=float, default=3.0, help="expected requests per second")
    c = sub.add_parser("collect")
    c.add_argument("--cap", type=int, default=500)
    c.add_argument("--workers", type=int, default=4)
    c.add_argument("--limit", type=int)
    c.add_argument("--appids")
    a = sub.add_parser("analyze")
    a.add_argument("--positive-only", action="store_true")
    a.add_argument("--targets", default="hunting+friendslop,dog+friendslop,hunting+horror,dog+hunting",
                   help="intersections to profile, comma-separated")
    a.add_argument("--top", type=int, default=25)
    args = p.parse_args()
    {"estimate": cmd_estimate, "collect": cmd_collect, "analyze": cmd_analyze}[args.cmd](args)


if __name__ == "__main__":
    main()
