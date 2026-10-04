"""Step 8: YouTube creators who covered games from both sides of an intersection.

  python 08_creators.py search --targets data/creator_targets.csv [--budget 9000]
  python 08_creators.py rank   --targets data/creator_targets.csv

targets CSV columns: intersection, side (a | b | hybrid), appid, name
  side a / b = games of each element of the intersection, hybrid = has both.

search: for every target game, top videos by views (search.list, 100 quota units
        per call), then video and channel statistics (1 unit per 50 ids).
        Raw API responses are cached in data/raw/youtube/, so reruns cost nothing.
rank:   a creator is "at the intersection" if they covered a hybrid game, or games
        from both side a and side b. Sorted by subscribers.

Needs YOUTUBE_API_KEY. Outputs: data/creator_videos.csv, data/creators.csv
"""
import argparse
import hashlib
import html
import json
import os
import re
import unicodedata

import pandas as pd
import requests

from config import DATA, RAW

API = "https://www.googleapis.com/youtube/v3/"
CACHE = RAW / "youtube"
COST = {"search": 100, "videos": 1, "channels": 1}
# platform / press channels: they post trailers, they are not creators to reach out to
MEDIA_CHANNELS = re.compile(
    r"^(playstation|xbox|nintendo|ign|gamespot|gametrailers|steam|epic games|pc gamer|"
    r"polygon|game informer|gamesradar|rock paper shotgun|aci gamespot|gameranx|"
    r"gamingbolt|gamespot trailers|ign india|maximilian dood)$", re.I)
TRAILER = re.compile(r"\b(official|trailer|teaser|launch|announce(ment)?)\b", re.I)


class Quota:
    def __init__(self, budget):
        self.budget, self.used = budget, 0


def call(endpoint, params, quota):
    """GET with on-disk cache; cached calls cost no quota."""
    key = hashlib.sha1(json.dumps([endpoint, sorted(params.items())]).encode()).hexdigest()
    path = CACHE / f"{endpoint}_{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    if quota.used + COST[endpoint] > quota.budget:
        raise RuntimeError(f"quota budget reached ({quota.used} units)")
    r = requests.get(API + endpoint, params={**params, "key": os.environ["YOUTUBE_API_KEY"]}, timeout=60)
    quota.used += COST[endpoint]
    if r.status_code != 200:
        raise RuntimeError(f"{endpoint} {r.status_code}: {r.text[:300]}")
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(r.text)
    return r.json()


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[™®©]", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def mentions(game, title, desc):
    """Video is about the game if its title (or, for long names, description) has the name."""
    g = norm(game)
    t, d = f" {norm(title)} ", f" {norm(desc)} "
    if f" {g} " in t:
        return True
    return len(g) >= 12 and f" {g} " in d


def chunks(xs, n=50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def cmd_search(args):
    quota = Quota(args.budget)
    targets = pd.read_csv(args.targets).drop_duplicates("appid")
    rows = []
    try:
        for t in targets.itertuples():
            query = f'"{t.name}" game'  # quotes: exact name, "game": drops films/books
            res = call("search", {"part": "snippet", "q": query, "type": "video",
                                  "order": "viewCount", "maxResults": 50,
                                  "videoCategoryId": 20}, quota)  # 20 = Gaming
            kept = 0
            for it in res.get("items", []):
                sn = it["snippet"]
                if not mentions(t.name, sn["title"], sn.get("description", "")):
                    continue
                kept += 1
                title, channel = html.unescape(sn["title"]), html.unescape(sn["channelTitle"])
                rows.append({"appid": t.appid, "game": t.name, "video_id": it["id"]["videoId"],
                             "title": title, "published": sn["publishedAt"][:10],
                             "channel_id": sn["channelId"], "channel": channel,
                             "is_media": bool(MEDIA_CHANNELS.match(channel) or TRAILER.search(title))})
            print(f"{t.name}: {kept}/{len(res.get('items', []))} videos kept  (quota used {quota.used})",
                  flush=True)
    except RuntimeError as e:
        print("stopped:", e)
    vids = pd.DataFrame(rows)
    if vids.empty:
        return
    stats = {}
    for ch in chunks(vids.video_id.unique().tolist()):
        for it in call("videos", {"part": "statistics", "id": ",".join(ch)}, quota).get("items", []):
            stats[it["id"]] = int(it["statistics"].get("viewCount", 0))
    vids["views"] = vids.video_id.map(stats)
    vids["video_url"] = "https://www.youtube.com/watch?v=" + vids.video_id
    vids.to_csv(DATA / "creator_videos.csv", index=False)

    chans = []
    for ch in chunks(vids.channel_id.unique().tolist()):
        res = call("channels", {"part": "snippet,statistics", "id": ",".join(ch)}, quota)
        for it in res.get("items", []):
            st, sn = it["statistics"], it["snippet"]
            chans.append({"channel_id": it["id"], "channel": html.unescape(sn["title"]),
                          "subscribers": int(st.get("subscriberCount", 0)) if not st.get("hiddenSubscriberCount") else None,
                          "channel_views": int(st.get("viewCount", 0)), "videos_total": int(st.get("videoCount", 0)),
                          "country": sn.get("country", ""), "handle": sn.get("customUrl", ""),
                          "url": f"https://www.youtube.com/channel/{it['id']}"})
    pd.DataFrame(chans).to_csv(RAW / "youtube_channels.csv", index=False)
    print(f"videos: {len(vids)}  channels: {len(chans)}  quota used this run: {quota.used}")


def cmd_rank(args):
    targets = pd.read_csv(args.targets)
    vids = pd.read_csv(DATA / "creator_videos.csv")
    vids = vids[~vids.is_media.astype(bool)]
    chans = pd.read_csv(RAW / "youtube_channels.csv").set_index("channel_id")
    out = []
    for inter, tg in targets.groupby("intersection"):
        side = tg.set_index("appid").side
        v = vids[vids.appid.isin(side.index)].assign(side=lambda d: d.appid.map(side))
        for cid, cv in v.groupby("channel_id"):
            sides = set(cv.side)
            if not ("hybrid" in sides or {"a", "b"} <= sides):
                continue
            games = cv.groupby(["game", "side"]).views.sum().sort_values(ascending=False)
            c = chans.loc[cid] if cid in chans.index else {}
            out.append({"intersection": inter, "channel": c.get("channel", cv.channel.iloc[0]),
                        "subscribers": c.get("subscribers"), "url": c.get("url"),
                        "country": c.get("country", ""),
                        "games_covered": "; ".join(f"{g} [{s}]" for (g, s) in games.index),
                        "n_games": len(games), "views_on_these_games": int(cv.views.sum()),
                        "top_video": cv.sort_values("views", ascending=False).video_url.iloc[0]})
    if not out:
        print("no creators cover both sides of any intersection")
        return
    res = pd.DataFrame(out).sort_values(["intersection", "subscribers"], ascending=[True, False])
    res.to_csv(DATA / "creators.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_colwidth", 70):
        print(res.groupby("intersection").head(args.top).to_string(index=False))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("--targets", default=str(DATA / "creator_targets.csv"))
    s.add_argument("--budget", type=int, default=9000, help="max quota units this run")
    r = sub.add_parser("rank")
    r.add_argument("--targets", default=str(DATA / "creator_targets.csv"))
    r.add_argument("--top", type=int, default=20)
    args = p.parse_args()
    {"search": cmd_search, "rank": cmd_rank}[args.cmd](args)


if __name__ == "__main__":
    main()
