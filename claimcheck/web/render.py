"""
The page, as one HTML string. Server-side, inline SVG, no JavaScript, no CDN:
nothing on it can fail to load at a race track.
"""
from __future__ import annotations

import html
import urllib.parse
from typing import Dict, List, Optional

import numpy as np

from claimcheck.check import thresholds as th
from claimcheck.check.claim import CAUSES
from claimcheck.check.measure import METRICS
from claimcheck.check.stats import LABEL

E = html.escape

CSS = """
:root{--bg:#f6f7f9;--panel:#fff;--ink:#14181f;--muted:#5d6675;--line:#e1e5eb;--soft:#eef1f5;
--accent:#0b5fff;--ok:#16794a;--ok-bg:#e3f4ea;--no:#b42318;--no-bg:#fde8e6;--maybe:#9a5b00;--maybe-bg:#fdf0d9;
--drv:#d1430b;--ref:#0b5fff;--grid:#e8ebf0}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0e1116;--panel:#161a21;--ink:#e8ebf0;
--muted:#9aa3b2;--line:#283040;--soft:#1d232d;--accent:#5b9dff;--ok:#4cc38a;--ok-bg:#12301f;--no:#ff7b6b;
--no-bg:#3a1714;--maybe:#f0b44c;--maybe-bg:#33270f;--drv:#ff8a4c;--ref:#5b9dff;--grid:#232a35}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}header{background:var(--panel);border-bottom:1px solid var(--line);padding:12px 20px;
display:flex;gap:18px;align-items:baseline;flex-wrap:wrap}header h1{font-size:17px;margin:0;letter-spacing:.2px}
header h1 span{color:var(--muted);font-weight:500}.meta{color:var(--muted);font-size:13px}
main{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:16px;padding:16px 20px;max-width:1400px;margin:0 auto}
@media (max-width:980px){main{grid-template-columns:1fr;padding:12px 16px}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:0 0 10px}
form.ask{display:flex;gap:8px}form.ask input[type=text]{flex:1;min-width:0;font-size:17px;padding:11px 12px;
border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--line);background:var(--soft);color:var(--ink);padding:9px 14px}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.chips a{font-size:13px;text-decoration:none;
background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:3px 10px;color:var(--ink)}
.stamp{display:inline-block;font-weight:800;letter-spacing:1px;text-transform:uppercase;font-size:20px;
padding:6px 14px;border-radius:8px;border:2px solid currentColor}
.s-supported{color:var(--ok);background:var(--ok-bg)}.s-contradicted{color:var(--no);background:var(--no-bg)}
.s-cant_tell{color:var(--maybe);background:var(--maybe-bg)}
.headline{font-size:18px;margin:12px 0 6px;line-height:1.4}.understood{color:var(--muted);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px}td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{font-size:11.5px;font-weight:700;padding:1px 7px;border-radius:999px;white-space:nowrap}
.where{display:flex;height:26px;border-radius:6px;overflow:hidden;margin:6px 0 2px;border:1px solid var(--line)}
.where div{display:flex;align-items:center;justify-content:center;font-size:12px;color:#fff;min-width:0}
.legend{display:flex;gap:14px;font-size:12px;color:var(--muted);flex-wrap:wrap}.sw{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:5px}
.box{background:var(--soft);border-radius:8px;padding:10px 12px;margin-top:10px;font-size:14px}
.caveats{color:var(--muted);font-size:13px;margin:10px 0 0;padding-left:18px}
.fb{display:flex;gap:8px;margin-top:14px;align-items:center;flex-wrap:wrap}.fb span{color:var(--muted);font-size:13px}
.stack{display:grid;gap:16px;align-content:start}svg{display:block;width:100%;height:auto}
details summary{cursor:pointer;color:var(--muted);font-size:13px}.hist a{text-decoration:none;color:var(--ink)}
.hist li{margin:0 0 8px;font-size:13.5px}.hist ul{list-style:none;padding:0;margin:0}.small{font-size:12.5px;color:var(--muted)}
.empty{color:var(--muted);font-size:14px}
"""


def _pill(stamp: str) -> str:
    return f'<span class="pill s-{stamp}">{E(LABEL[stamp])}</span>'


def _q(text: str) -> str:
    return "/?" + urllib.parse.urlencode({"q": text})


# ---- SVG ---------------------------------------------------------------------

def track_svg(track, highlight=None, w=340, h=300) -> str:
    x, y = track.path_x, track.path_y
    pad = 30
    k = min((w - 2 * pad) / (x.max() - x.min() or 1), (h - 2 * pad) / (y.max() - y.min() or 1))
    ox = pad + ((w - 2 * pad) - (x.max() - x.min()) * k) / 2
    oy = pad + ((h - 2 * pad) - (y.max() - y.min()) * k) / 2
    X = lambda v: ox + (v - x.min()) * k
    Y = lambda v: h - (oy + (v - y.min()) * k)
    pts = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(x[::2], y[::2]))
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Track map with corner numbers">',
           f'<polyline points="{pts}" fill="none" stroke="var(--line)" stroke-width="9" stroke-linejoin="round"/>',
           f'<polyline points="{pts}" fill="none" stroke="var(--muted)" stroke-width="2" stroke-linejoin="round"/>']
    if highlight is not None:
        s = np.linspace(highlight.entry_m, highlight.exit_m, 60)
        seg = " ".join(f"{X(np.interp(v, track.path_s, x)):.1f},{Y(np.interp(v, track.path_s, y)):.1f}" for v in s)
        out.append(f'<polyline points="{seg}" fill="none" stroke="var(--drv)" stroke-width="6" stroke-linecap="round"/>')
    sx, sy = track.xy_at(0.0)
    out.append(f'<rect x="{X(sx) - 4:.1f}" y="{Y(sy) - 4:.1f}" width="8" height="8" fill="var(--ink)"><title>start/finish</title></rect>')
    cx, cy = float(np.mean(x)), float(np.mean(y))
    for c in track.corners:
        ax, ay = track.xy_at(c.apex_m)
        # Label outside the loop: push away from the centroid.
        dx, dy = ax - cx, ay - cy
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        lx = min(max(X(ax + dx / n * 18 / k), 12.0), w - 12.0)
        ly = min(max(Y(ay + dy / n * 18 / k), 12.0), h - 8.0)
        on = highlight is not None and c.name == highlight.name
        out.append(f'<circle cx="{X(ax):.1f}" cy="{Y(ay):.1f}" r="3" fill="{"var(--drv)" if on else "var(--ink)"}"/>')
        out.append(f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="middle" font-size="12" '
                   f'font-weight="{700 if on else 500}" fill="{"var(--drv)" if on else "var(--ink)"}">{c.name}</text>')
    out.append("</svg>")
    return "".join(out)


def trace_svg(checker, verdict, w=760) -> str:
    """Speed, pedals and the accumulating time difference through the corner."""
    c = verdict.corner
    laps = {lp.key: lp for lp in checker.data.laps}
    dk, rk = verdict.plot_laps
    if c is None or dk is None or rk is None or dk not in laps or rk not in laps:
        return ""
    d, r = laps[dk], laps[rk]
    lo, hi = c.entry_m - 30.0, c.exit_m + 30.0
    s = np.arange(lo, hi, 2.0)
    def at(lap, ch):
        return np.interp(s, lap.s, np.nan_to_num(ch))
    vd, vr = at(d, d.v_kph), at(r, r.v_kph)
    bd, br = at(d, d.brake), at(r, r.brake)
    td, tr = at(d, d.throttle), at(r, r.throttle)
    dt = (np.interp(s, d.s, d.t) - np.interp(s, r.s, r.t))
    dt -= float(np.interp(c.entry_m, s, dt))

    L, R, T = 46, 12, 10
    hv, hp, hd, gap = 170, 46, 90, 16
    H = T + hv + gap + hp + gap + hp + gap + hd + 26
    pw = w - L - R
    X = lambda v: L + (v - lo) / (hi - lo) * pw
    vmax = max(vd.max(), vr.max()) * 1.05
    vmin = max(min(vd.min(), vr.min()) * 0.85 - 5, 0)
    Yv = lambda v: T + hv - (v - vmin) / (vmax - vmin) * hv
    y2 = T + hv + gap
    Yb = lambda v: y2 + hp - np.minimum(v, 120.0) / 120.0 * hp
    y3 = y2 + hp + gap
    Yt = lambda v: y3 + hp - v / 100.0 * hp
    y4 = y3 + hp + gap
    dmax = max(abs(dt).max(), 0.05) * 1.15
    Yd = lambda v: y4 + hd / 2 - v / dmax * (hd / 2)

    def line(xs, ys, color, width=2.0, dash=""):
        pts = " ".join(f"{X(a):.1f},{b:.1f}" for a, b in zip(xs, ys))
        da = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{da} stroke-linejoin="round"/>'

    out = [f'<svg viewBox="0 0 {w} {H:.0f}" role="img" aria-label="Corner traces">']
    # Phase bands.
    shades = {"entry": 0.05, "mid": 0.11, "exit": 0.05}
    for name, (a, b) in c.phases().items():
        if b > a:
            out.append(f'<rect x="{X(a):.1f}" y="{T}" width="{X(b) - X(a):.1f}" height="{H - T - 26:.0f}" '
                       f'fill="var(--accent)" opacity="{shades[name]}"/>')
            out.append(f'<text x="{(X(a) + X(b)) / 2:.1f}" y="{H - 8:.0f}" text-anchor="middle" font-size="11" fill="var(--muted)">{name}</text>')
    for yy, label in ((T, "speed, km/h"), (y2, "brake, bar"), (y3, "throttle, %"), (y4, "Δ time, s")):
        out.append(f'<text x="{L + 6}" y="{yy + 11:.0f}" font-size="11" font-weight="600" fill="var(--muted)">{label}</text>')
    for v in np.linspace(vmin, vmax, 4)[1:-1]:
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{Yv(v):.1f}" y2="{Yv(v):.1f}" stroke="var(--grid)"/>'
                   f'<text x="{L - 6}" y="{Yv(v) + 4:.1f}" text-anchor="end" font-size="10" fill="var(--muted)">{v:.0f}</text>')
    out.append(f'<line x1="{L}" x2="{w - R}" y1="{Yd(0):.1f}" y2="{Yd(0):.1f}" stroke="var(--muted)" stroke-width="0.8"/>')
    for v in (-dmax / 1.15, dmax / 1.15):
        out.append(f'<text x="{L - 6}" y="{Yd(v) + 4:.1f}" text-anchor="end" font-size="10" fill="var(--muted)">{v:+.2f}</text>')
    out.append(line(s, Yv(vr), "var(--ref)"))
    out.append(line(s, Yv(vd), "var(--drv)"))
    out.append(line(s, Yb(br), "var(--ref)", 1.6))
    out.append(line(s, Yb(bd), "var(--drv)", 1.6))
    out.append(line(s, Yt(tr), "var(--ref)", 1.6))
    out.append(line(s, Yt(td), "var(--drv)", 1.6))
    out.append(line(s, Yd(dt), "var(--drv)", 2.2))
    # Distance axis.
    for v in np.arange(np.ceil(lo / 100) * 100, hi, 100):
        out.append(f'<text x="{X(v):.1f}" y="{H - 20:.0f}" text-anchor="middle" font-size="10" fill="var(--muted)">{v:.0f} m</text>')
    out.append("</svg>")
    legend = (f'<div class="legend"><span><i class="sw" style="background:var(--drv)"></i>{E(d.label)} (median lap in this corner)</span>'
              f'<span><i class="sw" style="background:var(--ref)"></i>{E(r.label)} (comparison, fastest in this corner)</span>'
              f'<span>Δ time: above zero = {E(d.driver)} behind, from the corner entry</span></div>')
    return "".join(out) + legend


# ---- the card ------------------------------------------------------------------

def _num(metric: str, v) -> str:
    if v is None:
        return "—"
    label, unit, dec = METRICS[metric]
    if metric == "full_throttle_share":
        return f"{v * 100:.0f} %"
    return f"{v:.{dec}f}{(' ' + unit) if unit else ''}"


def _diff(metric: str, t: dict) -> str:
    if t.get("mean_driver") is None:
        return "—"
    d = t["mean_driver"] - t["mean_ref"]
    lo, hi = sorted((t["direction_low"], t["direction_high"]))
    if metric == "full_throttle_share":
        return f"{d * 100:+.0f} pp <span class='small'>({lo * 100:+.0f} … {hi * 100:+.0f})</span>"
    label, unit, dec = METRICS[metric]
    return f"{d:+.{dec}f} {unit} <span class='small'>({lo:+.{dec}f} … {hi:+.{dec}f})</span>"


def verdict_card(checker, v, check_id: Optional[str]) -> str:
    d = v.to_dict()
    parts = [f'<section class="card"><span class="stamp s-{v.stamp}">{E(v.label)}</span>',
             f'<p class="headline">{E(v.headline)}</p>',
             f'<div class="understood">Understood: <b>{E(v.understood)}</b>'
             + (f' · compared with {E(v.reference)}' if v.reference else "") + "</div>"]
    if v.corner is not None and v.tests:
        drv = E(v.driver or "")
        rows = []
        for t, td in zip(v.tests, d["tests"]):
            c = t.comparison
            if c is not None:
                td["direction_low"], td["direction_high"] = t.direction * c.low, t.direction * c.high
            label = METRICS[t.metric][0]
            claim = "time in the corner" if t.name == "effect" else t.label
            rows.append(
                f"<tr><td>{E(claim)}<div class='small'>{E(label)}</div></td>"
                f"<td class='num'>{_num(t.metric, c.mean_driver if c else None)}"
                f"<div class='small'>{c.n_driver if c else 0} laps</div></td>"
                f"<td class='num'>{_num(t.metric, c.mean_ref if c else None)}"
                f"<div class='small'>{c.n_ref if c else 0} laps</div></td>"
                f"<td class='num'>{_diff(t.metric, td) if c else '—'}</td>"
                f"<td class='num'>{_num(t.metric, th.TOL[t.metric]) if t.metric in th.TOL else ''}</td>"
                f"<td>{_pill(t.stamp)}" + (f"<div class='small'>{E(t.note)}</div>" if t.note else "")
                + (f"<div class='small'>{max(t.share, 0):.0%} of the loss in its phase</div>"
                   if t.share is not None and t.name != "effect" and v.spec.effect else "")
                + "</td></tr>")
        parts.append("<table style='margin-top:14px'><tr><th>claim</th>"
                     f"<th>{drv}</th><th>comparison</th><th>difference (90 % range)</th>"
                     "<th>matters from</th><th>result</th></tr>" + "".join(rows) + "</table>")
    if v.where:
        tot = sum(abs(x) for x in v.where.values()) or 1.0
        cols = {"entry": "#5b6b85", "mid": "#8a6fb0", "exit": "#2f8f83"}
        bars = "".join(
            f'<div style="width:{abs(x) / tot * 100:.1f}%;background:{cols[k]};opacity:{1 if x > 0 else .45}" '
            f'title="{k}: {x:+.3f} s">{k} {x:+.2f}</div>' for k, x in v.where.items() if abs(x) / tot > 0.04)
        parts.append(f"<div style='margin-top:14px' class='small'>Where {E(v.driver or '')}'s time goes in "
                     f"{E(v.corner.name)}, against the comparison (faded = gained)</div><div class='where'>{bars}</div>")
    if v.pointers:
        items = []
        for p in v.pointers:
            items.append(f"<li>{E(v.driver or '')} <b>{E(_diff_plain(p))}</b>"
                         + (f" — {max(p.share, 0):.0%} of the loss is in that phase" if p.share is not None else "")
                         + "</li>")
        parts.append("<div class='box'><b>What the data points to instead</b> "
                     "<span class='small'>(a pointer, not a verdict)</span><ul style='margin:6px 0 0'>"
                     + "".join(items) + "</ul></div>")
    if v.caveats:
        parts.append("<ul class='caveats'>" + "".join(f"<li>{E(c)}</li>" for c in v.caveats) + "</ul>")
    if check_id:
        q = E(v.spec.text)
        parts.append(
            "<form class='fb' method='post' action='/feedback'>"
            f"<input type='hidden' name='id' value='{E(check_id)}'><input type='hidden' name='q' value='{q}'>"
            "<span>Engineer:</span>"
            "<button name='judgement' value='agree'>Agrees</button>"
            "<button name='judgement' value='disagree'>Disagrees</button>"
            "<button name='judgement' value='unsure'>Not sure</button></form>")
    parts.append("</section>")
    return "".join(parts)


def _diff_plain(t) -> str:
    from claimcheck.check.verdict import _diff_words
    c = t.comparison
    return _diff_words(t.metric, c.mean_driver - c.mean_ref)


def _examples(checker) -> List[str]:
    drivers = checker.data.drivers
    corners = checker.track.corners
    d1 = drivers[0]
    d2 = drivers[1] if len(drivers) > 1 else None
    braked = [c for c in corners if c.ref_brake_m is not None]
    c1 = braked[0].name if braked else corners[0].name
    c2 = braked[len(braked) // 2].name if braked else corners[-1].name
    ex = [f"{d1} loses time in {c1} because he brakes early",
          f"{d1} is late on the throttle in {c2}",
          f"{d1} coasts in {c2}"]
    if d2:
        ex.insert(1, f"{d1} loses time to {d2} in {c2}")
    ex.append(f"{d1} verliert Zeit in Kurve {c1[1:]}, weil er zu früh bremst")
    return ex


def page(checker, verdict=None, check_id=None, history: Optional[list] = None,
         query: str = "", banner: str = "") -> str:
    data, track = checker.data, checker.track
    ref = track.reference
    files = ", ".join(f["name"] for f in data.files)
    drivers = " · ".join(f"{d}: {len(data.valid(d))}/{len([l for l in data.laps if l.driver == d])} laps"
                         for d in data.drivers)
    tr_note = ("Claude reads the sentence, statistics decide" if checker.translator is not None
               else "rule parser reads the sentence, statistics decide")
    head = (f"<header><h1>AI Copilot <span>· Claim check</span></h1>"
            f"<div class='meta'>{E(files)}</div><div class='meta'>{E(drivers)}</div>"
            f"<div class='meta'>reference path: {E(ref.label)} ({ref.time_s:.3f} s) · {len(track.corners)} corners · "
            f"{E(tr_note)} · rules {E(th.VERSION)}</div></header>")
    chips = "".join(f'<a href="{E(_q(t))}">{E(t)}</a>' for t in _examples(checker))
    form = (f"<section class='card'><form class='ask' method='get' action='/'>"
            f"<input type='text' name='q' autofocus autocomplete='off' value='{E(query)}' "
            f"placeholder='e.g. {E(_examples(checker)[0])}'>"
            f"<button class='primary'>Check</button></form><div class='chips'>{chips}</div>"
            + (f"<p class='small' style='margin:10px 0 0'>{E(banner)}</p>" if banner else "") + "</section>")
    left = [form]
    if verdict is not None:
        left.append(verdict_card(checker, verdict, check_id))
        svg = trace_svg(checker, verdict)
        if svg:
            left.append(f"<section class='card'><h2>{E(verdict.corner.name)}, metre by metre</h2>{svg}</section>")
        if verdict.rows:
            rows = "".join(
                f"<tr><td>{E(r['role'])}</td><td>{E(r['driver'])}</td><td class='num'>{r['lap']}</td>"
                f"<td class='num'>{r['lap_time_s']:.3f}</td><td class='num'>{_num('corner_time_s', r['corner_time_s'])}</td>"
                f"<td class='num'>{_num('brake_point_m', r['brake_point_m'])}</td><td class='num'>{_num('v_min_kph', r['v_min_kph'])}</td>"
                f"<td class='num'>{_num('throttle_on_m', r['throttle_on_m'])}</td><td class='num'>{_num('coasting_s', r['coasting_s'])}</td></tr>"
                for r in verdict.rows)
            left.append("<section class='card'><details><summary>Every lap in this corner</summary>"
                        "<table style='margin-top:8px'><tr><th>role</th><th>driver</th><th>lap</th><th>lap time</th>"
                        "<th>corner time</th><th>brake point</th><th>min speed</th><th>throttle pick-up</th>"
                        "<th>coasting</th></tr>" + rows + "</table></details></section>")
    else:
        left.append("<section class='card'><p class='empty'>Type what you believe about a driver and a corner. "
                    "The answer is one of three stamps, with the laps and the numbers behind it. "
                    "<b>Can't tell yet</b> is an honest answer, not an error.</p></section>")

    corner_rows = "".join(
        f"<tr><td><a href='{E(_q(f'{data.drivers[0]} loses time in {c.name}'))}'>{c.name}</a>"
        + (f" <span class='small'>{E(', '.join(c.names))}</span>" if c.names else "")
        + f"</td><td>{c.direction}</td><td class='num'>{c.apex_m:.0f} m</td><td class='num'>{c.v_min_kph:.0f}</td></tr>"
        for c in track.corners)
    right = [f"<section class='card'><h2>Track, as the tool numbers it</h2>"
             f"{track_svg(track, verdict.corner if verdict is not None else None)}"
             "<p class='small'>Numbers come from the data, not the official map. "
             "If they differ, start with <code>--alias Hairpin=T6</code>.</p>"
             f"<table><tr><th>corner</th><th>turn</th><th>apex</th><th>min km/h</th></tr>{corner_rows}</table></section>"]
    if history:
        latest: Dict[str, dict] = {}
        for h in history:
            if h.get("type") == "check":
                latest.pop(h["claim"], None)
                latest[h["claim"]] = h
        items = "".join(
            f"<li>{_pill(h['stamp'])} <a href='{E(_q(h['claim']))}'>{E(h['claim'])}</a></li>"
            for h in reversed(list(latest.values())[-10:]))
        right.append(f"<section class='card hist'><h2>Checked this session</h2><ul>{items}</ul></section>")
    title = "AI Copilot claim check"
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title>"
            f"<style>{CSS}</style></head><body>{head}<main><div class='stack'>{''.join(left)}</div>"
            f"<div class='stack'>{''.join(right)}</div></main></body></html>")
