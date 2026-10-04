"""Step 12: interactive overview page of dog / hunting combinations.

Reads data/combo_summary.csv, data/combo_dynamics.csv and data/games.csv,
writes docs/combos_overview.html (data inlined, no external requests).
"""
import importlib
import json

import pandas as pd

from config import DATA, ROOT

cd = importlib.import_module("11_combo_dynamics")


def games_for(df, combo):
    mask = pd.Series(True, index=df.index)
    for e in combo:
        mask &= df[f"el_{e}"]
    return df[mask]


def game_row(r):
    return {"name": r["name"], "year": int(r.year), "reviews": int(r.reviews_total),
            "pos": None if pd.isna(r.positive_pct) else float(r.positive_pct),
            "price": None if pd.isna(r.price_usd) else float(r.price_usd), "url": r.url}


def main():
    summ = pd.read_csv(DATA / "combo_summary.csv")
    dyn = pd.read_csv(DATA / "combo_dynamics.csv")
    df = cd.load()
    label_to_combo = {" + ".join(cd.EL_RU[e] for e in c): c for c in cd.combos()}
    items = []
    for r in summ.itertuples():
        combo = label_to_combo[r.combo]
        g = games_for(df, combo)
        recent = g[g.year >= 2022].sort_values("reviews_total", ascending=False)
        mid = recent[(recent.reviews_total >= 100) & (recent.reviews_total < 2000)]
        d = dyn[dyn.combo == r.combo]

        def series(kind):
            x = d[d.period_type == kind]
            return [{"p": str(p), "games": int(n), "p100": v, "inc": bool(i)}
                    for p, n, v, i in zip(x.period, x.games, x.pct_100plus, x.incomplete)]

        nan = lambda v: None if pd.isna(v) else v
        items.append({
            "combo": r.combo, "k": int(r.n_elements), "els": list(combo),
            "games": int(r.games_2022plus), "p100": nan(r.pct_100plus_2022plus),
            "p1000": nan(r.pct_1000plus_2022plus), "median": nan(r.median_reviews_2022plus),
            "early": nan(r.pct_100plus_2022_23), "early_n": int(r.games_2022_23),
            "late": nan(r.pct_100plus_2024_25), "late_n": int(r.games_2024_25),
            "trend": r.trend, "top3share": nan(r.top3_share_of_reviews),
            "announced": int(r.announced_2026_27), "years": series("year"), "halves": series("half"),
            "top": [game_row(x) for _, x in recent.head(5).iterrows()],
            "mid": [game_row(x) for _, x in mid.head(8).iterrows()],
        })
    html = TEMPLATE.replace("/*DATA*/", json.dumps(items, ensure_ascii=False))
    out = ROOT / "docs" / "combos_overview.html"
    out.write_text(html, encoding="utf-8")
    print("written", out, f"{len(html) / 1024:.0f} KB")


TEMPLATE = r"""<title>Собаки и охота в Steam</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600&family=Unbounded:wght@500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* Layout: a scan-first table of combinations (summary), a detail panel below with two small charts and game lists. */
:root {
  --bg: #f6f7f4; --surface: #ffffff; --line: #dfe2da; --fg: #16190f; --fg2: #50554a; --muted: #80857a;
  --accent: #2f6b3a; --accent-soft: #e3eedf;
  --seq-0: #eef4fb; --seq-1: #cde2fb; --seq-2: #9ec5f4; --seq-3: #5598e7; --seq-4: #256abf; --seq-5: #184f95;
  --bar: #2a78d6; --bar-inc: #b7d3f6;
  --good: #0ca30c; --bad: #d03b3b; --warn: #b07700;
  --f-display: "Unbounded", "Golos Text", system-ui, sans-serif;
  --f-body: "Golos Text", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #141611; --surface: #1c1f18; --line: #33372d; --fg: #eef0e8; --fg2: #b9bdb0; --muted: #8c9183;
  --accent: #8cc995; --accent-soft: #233226;
  --seq-0: #1f2530; --seq-1: #1c3556; --seq-2: #1c5cab; --seq-3: #2a78d6; --seq-4: #5598e7; --seq-5: #9ec5f4;
  --bar: #3987e5; --bar-inc: #2b4a73; --good: #2bc02b; --bad: #e66767; --warn: #e0a531; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #141611; --surface: #1c1f18; --line: #33372d; --fg: #eef0e8; --fg2: #b9bdb0; --muted: #8c9183;
  --accent: #8cc995; --accent-soft: #233226;
  --seq-0: #1f2530; --seq-1: #1c3556; --seq-2: #1c5cab; --seq-3: #2a78d6; --seq-4: #5598e7; --seq-5: #9ec5f4;
  --bar: #3987e5; --bar-inc: #2b4a73; --good: #2bc02b; --bad: #e66767; --warn: #e0a531; color-scheme: dark }
body { background: var(--bg); color: var(--fg); font: 15px/1.5 var(--f-body); }
.wrap { max-width: 1120px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 56px; display: grid; gap: 22px; }
h1 { font: 600 clamp(22px, 3.2vw, 30px)/1.15 var(--f-display); margin: 0; text-wrap: balance; letter-spacing: -0.01em; }
h2 { font: 600 17px/1.3 var(--f-display); margin: 0; text-wrap: balance; }
.lede { color: var(--fg2); max-width: 68ch; margin: 6px 0 0; }
.lede b { color: var(--fg); font-weight: 600; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--surface); }
.seg button { font: 500 13px var(--f-body); color: var(--fg2); background: none; border: 0; padding: 7px 12px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--accent-soft); color: var(--fg); }
.seg button:focus-visible, tr:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.label { font: 500 11px var(--f-body); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.tablebox { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; min-width: 760px; font-variant-numeric: tabular-nums; }
th { text-align: left; font: 500 11px var(--f-body); letter-spacing: .05em; text-transform: uppercase; color: var(--muted);
  padding: 10px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; vertical-align: bottom; }
th.num, td.num { text-align: right; }
td { padding: 9px 8px; border-bottom: 1px solid var(--line); vertical-align: middle; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: color-mix(in srgb, var(--accent-soft) 55%, transparent); }
tbody tr[aria-selected="true"] { background: var(--accent-soft); }
tbody tr.thin td { color: var(--muted); }
td.combo { font-weight: 600; white-space: nowrap; }
td.combo small { display: block; font-weight: 400; color: var(--muted); font-size: 12px; }
.heat { display: inline-block; min-width: 54px; padding: 3px 8px; border-radius: 6px; font: 500 13px var(--f-mono); text-align: right; }
.chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; padding: 2px 9px; border-radius: 99px;
  border: 1px solid var(--line); white-space: nowrap; color: var(--fg2); }
.chip i { font-style: normal; font-weight: 700; }
.chip.up i { color: var(--good); } .chip.down i { color: var(--bad); } .chip.flat i { color: var(--fg2); } .chip.na i { color: var(--muted); }
.mono { font-family: var(--f-mono); font-size: 13px; }
.detail { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; }
@media (max-width: 760px) { .detail { grid-template-columns: minmax(0, 1fr); } }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; display: grid; gap: 10px; min-width: 0; align-content: start; }
.panel header { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.kpis { display: flex; flex-wrap: wrap; gap: 22px; }
.kpi .v { font: 600 22px/1.1 var(--f-display); }
.kpi .k { color: var(--muted); font-size: 12.5px; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
svg text { fill: var(--muted); font: 11px var(--f-body); }
svg .grid { stroke: var(--line); stroke-width: 1; }
svg .val { fill: var(--fg2); font: 500 11px var(--f-mono); }
.games { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.games li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 10px; padding: 6px 0; border-bottom: 1px dashed var(--line); align-items: baseline; }
.games li:last-child { border-bottom: 0; }
.games a { color: var(--fg); text-decoration: none; overflow-wrap: anywhere; }
.games a:hover { text-decoration: underline; color: var(--accent); }
.games .meta { color: var(--muted); font-size: 12.5px; }
.empty { color: var(--muted); font-size: 13.5px; }
.note { color: var(--muted); font-size: 13px; max-width: 80ch; }
.tip { position: fixed; pointer-events: none; background: var(--fg); color: var(--bg); font: 12.5px/1.4 var(--f-body);
  padding: 7px 9px; border-radius: 6px; max-width: 240px; z-index: 5; }
@media (prefers-reduced-motion: no-preference) { tbody tr { transition: background .12s; } }
</style>

<div class="wrap">
  <header>
    <div class="label">Steam · игры с 2022 года · без AAA · только платные</div>
    <h1>Собаки и охота в Steam</h1>
    <p class="lede">Главная мера — <b>доля игр, набравших 100+ отзывов</b> (примерно от 2–6 тыс. проданных копий).
      Каждая игра считается один раз, поэтому один хит её не раздувает. Нажмите на строку, чтобы увидеть динамику и примеры игр.</p>
  </header>

  <div class="controls" role="group" aria-label="Фильтры">
    <span class="label">Показать</span>
    <div class="seg" id="f-k">
      <button type="button" data-k="all" aria-pressed="true">Все</button>
      <button type="button" data-k="1" aria-pressed="false">Одиночные</button>
      <button type="button" data-k="2" aria-pressed="false">Пары</button>
      <button type="button" data-k="3" aria-pressed="false">Тройки</button>
    </div>
    <div class="seg" id="f-thin">
      <button type="button" data-v="show" aria-pressed="true">С малыми выборками</button>
      <button type="button" data-v="hide" aria-pressed="false">Только от 15 игр</button>
    </div>
  </div>

  <div class="tablebox">
    <table>
      <thead><tr>
        <th>Сочетание</th>
        <th class="num">Игр с 2022</th>
        <th class="num">Набрали 100+</th>
        <th class="num">Набрали 1000+</th>
        <th class="num">Медиана отзывов</th>
        <th>Тренд 100+<br><span style="text-transform:none;letter-spacing:0">2022–23 → 2024–25</span></th>
        <th class="num">Доля топ-3</th>
        <th class="num">Анонсы 26–27</th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>

  <section class="detail" id="detail" aria-live="polite"></section>

  <p class="note">«Доля топ-3» — какая часть всех отзывов сочетания приходится на три крупнейшие игры; выше 70% значит, что ниша держится на хитах.
    Периоды моложе 12 месяцев отмечены светлым: их игры ещё набирают отзывы, и доля занижена.
    «Кооп» — любой кооп (онлайн или локальный); «френдслоп» — онлайн-кооп с тегами юмора, физики или пати.
    Данные Steam на 4 октября 2026.</p>
</div>
<div class="tip" id="tip" hidden></div>

<script>
const DATA = /*DATA*/;
const $ = s => document.querySelector(s);
const fmt = v => v == null ? "—" : (Math.round(v * 10) / 10).toLocaleString("ru-RU");
const pct = v => v == null ? "—" : fmt(v) + "%";
const SEQ = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5"];
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const MIN = 15;
let state = { k: "all", thin: "show", sel: null, period: "year" };

function heat(v, max) {
  if (v == null) return `<span class="heat" style="color:var(--muted)">—</span>`;
  const step = Math.min(5, Math.floor((v / max) * 5.999));
  const dark = step >= 4;
  return `<span class="heat" style="background:var(${SEQ[step]});color:${dark ? "#fff" : "var(--fg)"}">${pct(v)}</span>`;
}
function trendChip(d) {
  const m = { "растёт": ["up", "↑"], "падает": ["down", "↓"], "стабильно": ["flat", "→"] }[d.trend];
  if (!m) return `<span class="chip na" title="${d.trend}"><i aria-hidden="true">·</i>мало данных</span>`;
  return `<span class="chip ${m[0]}" title="2022–23: ${pct(d.early)} из ${d.early_n} игр; 2024–25: ${pct(d.late)} из ${d.late_n}"><i aria-hidden="true">${m[1]}</i>${d.trend} <span class="mono">${fmt(d.early)}→${fmt(d.late)}</span></span>`;
}
function render() {
  const list = DATA.filter(d => (state.k === "all" || d.k == state.k) && (state.thin === "show" || d.games >= MIN));
  const max100 = Math.max(...DATA.filter(d => d.games >= MIN).map(d => d.p100 || 0), 1);
  const max1000 = Math.max(...DATA.filter(d => d.games >= MIN).map(d => d.p1000 || 0), 1);
  $("#rows").innerHTML = list.map(d => `
    <tr tabindex="0" data-c="${d.combo}" aria-selected="${state.sel === d.combo}" class="${d.games < MIN ? "thin" : ""}">
      <td class="combo">${d.combo}${d.games < MIN ? "<small>мало игр — ориентир, не вывод</small>" : ""}</td>
      <td class="num mono">${d.games}</td>
      <td class="num">${heat(d.p100, max100)}</td>
      <td class="num">${heat(d.p1000, max1000)}</td>
      <td class="num mono">${fmt(d.median)}</td>
      <td>${trendChip(d)}</td>
      <td class="num mono" ${d.top3share > 70 ? 'style="color:var(--warn);font-weight:600"' : ""}>${pct(d.top3share)}</td>
      <td class="num mono">${d.announced}</td>
    </tr>`).join("");
  document.querySelectorAll("#rows tr").forEach(tr => {
    const pick = () => { state.sel = tr.dataset.c; render(); };
    tr.addEventListener("click", pick);
    tr.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
  });
  renderDetail();
}

function chart(series, kind) {
  // kind "games": bars of game counts; kind "p100": % reaching 100+ as bars on a 0-100 scale
  const W = 460, H = 170, L = 34, R = 8, T = 14, B = 24;
  const n = series.length;
  if (!n) return `<p class="empty">Нет игр.</p>`;
  const vals = series.map(s => kind === "games" ? s.games : (s.p100 ?? 0));
  const top = kind === "games" ? Math.max(4, ...vals) : 100;
  const nice = kind === "games" ? Math.ceil(top / 4) * 4 : 100;
  const bw = (W - L - R) / n, y = v => T + (H - T - B) * (1 - v / nice);
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = nice * i / 4, yy = y(v);
    g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}"/><text x="${L - 6}" y="${yy + 3.5}" text-anchor="end">${kind === "games" ? v : v + "%"}</text>`;
  }
  const every = Math.ceil(n / 9);
  series.forEach((s, i) => {
    const v = vals[i], x = L + i * bw + 2, w = Math.max(3, bw - 4), yy = y(v);
    const fill = s.inc ? "var(--bar-inc)" : "var(--bar)";
    const r = Math.min(4, w / 2, H - B - yy);
    const path = v > 0 ? `M${x},${H - B} V${yy + r} Q${x},${yy} ${x + r},${yy} H${x + w - r} Q${x + w},${yy} ${x + w},${yy + r} V${H - B} Z` : "";
    const tip = `${s.p}${s.inc ? " (неполный период)" : ""}: ${s.games} игр, 100+ отзывов у ${pct(s.p100)}`;
    g += `<g class="hit" data-tip="${tip}"><rect x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}" fill="transparent"/>${path ? `<path d="${path}" fill="${fill}"/>` : ""}</g>`;
    if (i % every === 0 || i === n - 1) g += `<text x="${x + w / 2}" y="${H - 7}" text-anchor="middle">${s.p.replace("-H", "·")}</text>`;
  });
  const last = n - 1;
  g += `<text class="val" x="${L + last * bw + bw / 2}" y="${y(vals[last]) - 5}" text-anchor="middle">${kind === "games" ? vals[last] : pct(vals[last])}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${kind === "games" ? "Число вышедших игр по периодам" : "Доля игр со 100+ отзывами по периодам"}">${g}</svg>`;
}
function gameList(rows, empty) {
  if (!rows.length) return `<p class="empty">${empty}</p>`;
  return `<ul class="games">${rows.map(r => `<li><a href="${r.url}" target="_blank" rel="noopener">${r.name}</a>
    <span class="meta">${r.year}${r.price != null ? " · $" + r.price : ""}${r.pos != null ? " · " + Math.round(r.pos) + "%👍" : ""}</span>
    <span class="mono">${r.reviews.toLocaleString("ru-RU")}</span></li>`).join("")}</ul>`;
}
function renderDetail() {
  const d = DATA.find(x => x.combo === state.sel);
  if (!d) { $("#detail").innerHTML = `<div class="panel" style="grid-column:1/-1"><p class="empty">Выберите сочетание в таблице — здесь появятся динамика по годам и примеры игр.</p></div>`; return; }
  const s = state.period === "year" ? d.years : d.halves;
  $("#detail").innerHTML = `
    <div class="panel" style="grid-column:1/-1">
      <header><h2>${d.combo}</h2>
        <div class="seg" id="f-period">
          <button type="button" data-p="year" aria-pressed="${state.period === "year"}">По годам</button>
          <button type="button" data-p="half" aria-pressed="${state.period === "half"}">По полугодиям</button>
        </div></header>
      <div class="kpis">
        <div class="kpi"><div class="v">${pct(d.p100)}</div><div class="k">набрали 100+ (с 2022)</div></div>
        <div class="kpi"><div class="v">${pct(d.p1000)}</div><div class="k">набрали 1000+</div></div>
        <div class="kpi"><div class="v">${d.games}</div><div class="k">игр с 2022</div></div>
        <div class="kpi"><div class="v">${d.announced}</div><div class="k">анонсов на 2026–27</div></div>
      </div>
    </div>
    <div class="panel"><div class="label">Сколько игр вышло</div>${chart(s, "games")}</div>
    <div class="panel"><div class="label">Доля набравших 100+ отзывов</div>${chart(s, "p100")}</div>
    <div class="panel"><div class="label">Середина рынка: 100–2000 отзывов, с 2022</div>${gameList(d.mid, "Таких игр нет.")}</div>
    <div class="panel"><div class="label">Крупнейшие с 2022</div>${gameList(d.top, "Игр нет.")}</div>`;
  document.querySelectorAll("#f-period button").forEach(b => b.addEventListener("click", () => { state.period = b.dataset.p; renderDetail(); }));
  bindTips();
}
function bindTips() {
  const tip = $("#tip");
  document.querySelectorAll("#detail .hit").forEach(h => {
    h.addEventListener("mousemove", e => { tip.textContent = h.dataset.tip; tip.hidden = false;
      tip.style.left = Math.min(e.clientX + 12, innerWidth - 250) + "px"; tip.style.top = (e.clientY + 14) + "px"; });
    h.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}
function seg(id, key, attr) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.addEventListener("click", () => {
    state[key] = b.dataset[attr];
    document.querySelectorAll(`#${id} button`).forEach(x => x.setAttribute("aria-pressed", x === b));
    render();
  }));
}
seg("f-k", "k", "k"); seg("f-thin", "thin", "v");
state.sel = DATA[0] && DATA[0].combo;
render();
</script>
"""

if __name__ == "__main__":
    main()
