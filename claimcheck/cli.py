"""
claimcheck — the command line.

    claimcheck serve  FILES... [--driver AA] [--driver "AA=1-6,BB=7-12"] [--alias Hairpin=T6]
    claimcheck check  FILES... -c "AA loses time in T1 because he brakes early"
    claimcheck corners FILES...
    claimcheck laps   FILES...
    claimcheck demo   [--dir synthetic]       synthetic sessions

`--driver` is given once per file, in file order. FILES may be folders, in
which case every `.vbo` inside is loaded in name order.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import List, Optional

from claimcheck.check import log as checklog
from claimcheck.check.measure import METRICS
from claimcheck.check.stats import LABEL


def _aliases(items: Optional[List[str]]) -> dict:
    out = {}
    for item in items or []:
        if "=" in item:
            name, target = item.split("=", 1)
            out[name.strip()] = target.strip().upper()
    return out


def _translator(args):
    if args.no_claude:
        return None
    from claimcheck.check import translate
    if not translate.available():
        return None
    try:
        return translate.ClaudeTranslator()
    except Exception:
        return None


def _checker(args):
    import json
    from claimcheck.check.checker import Checker
    profile = None
    if getattr(args, "track", None):
        profile = json.loads(Path(args.track).read_text(encoding="utf-8"))
    return Checker(args.files, args.driver, _aliases(args.alias), _translator(args), profile)


def cmd_laps(args) -> int:
    ck = _checker(args)
    print(f"{'driver':8} {'file':44} {'lap':>4} {'time':>10}  valid")
    for lp in ck.data.laps:
        m, s = divmod(lp.time_s, 60)
        print(f"{lp.driver:8} {lp.source[:44]:44} {lp.number:>4} {int(m)}:{s:06.3f}  "
              f"{'yes' if lp.valid else 'no  ' + lp.why_invalid}")
    print(f"\nreference path: {ck.track.reference.label} · loaded in {ck.load_s:.2f} s")
    return 0


def cmd_corners(args) -> int:
    ck = _checker(args)
    print(f"{ck.track.length_m:.0f} m · reference {ck.track.reference.label}\n")
    print(f"{'corner':7} {'turn':6} {'apex m':>7} {'min km/h':>9} {'peak g':>7} {'ref brake m':>12}")
    for c in ck.track.corners:
        bp = f"{c.ref_brake_m:.0f}" if c.ref_brake_m is not None else "—"
        names = f"  ({', '.join(c.names)})" if c.names else ""
        print(f"{c.name:7} {c.direction:6} {c.apex_m:7.0f} {c.v_min_kph:9.0f} {c.peak_g:7.2f} {bp:>12}{names}")
    if args.save_track:
        from claimcheck.check.track import save_profile
        save_profile(ck.track, ck.data.origin, args.save_track, args.save_track,
                     [f["name"] for f in ck.data.files])
        print(f"\ntrack profile written to {args.save_track}: rename corners to the official numbers "
              f"there, then pass --track {args.save_track} to every later session.")
    return 0


def print_verdict(v) -> None:
    print(f"\n  [{LABEL[v.stamp].upper()}]  {v.headline}\n")
    print(f"  understood: {v.understood}")
    if v.reference:
        print(f"  compared with: {v.reference}")
    for t in v.tests:
        c = t.comparison
        label, unit, dec = METRICS[t.metric]
        if c is None:
            print(f"  - {t.label:24} {LABEL[t.stamp]:15} {t.note}")
            continue
        lo, hi = sorted((t.direction * c.low, t.direction * c.high))
        print(f"  - {('time' if t.name == 'effect' else t.label):24} {LABEL[t.stamp]:15} "
              f"{c.mean_driver:.{dec}f} vs {c.mean_ref:.{dec}f} {unit}  "
              f"diff {c.mean_driver - c.mean_ref:+.{dec}f} ({lo:+.{dec}f} … {hi:+.{dec}f}), "
              f"{c.n_driver} vs {c.n_ref} laps"
              + (f", {max(t.share, 0):.0%} of loss in phase" if t.share is not None and t.name != 'effect' else ""))
    if v.where:
        print("  where: " + "  ".join(f"{k} {x:+.3f} s" for k, x in v.where.items()))
    for p in v.pointers:
        print(f"  pointer (not a verdict): {p.label}")
    for c in v.caveats:
        print("  · " + "\n    ".join(textwrap.wrap(c, 96)))


def cmd_check(args) -> int:
    ck = _checker(args)
    for claim in args.claim:
        v = ck.check(claim)
        print(f"\n> {claim}")
        print_verdict(v)
        if args.log:
            checklog.write_check(args.log, v, ck.data.files, getattr(v, "rule_spec", None),
                                 getattr(v, "llm_spec", None))
    return 0


def cmd_serve(args) -> int:
    from claimcheck.web.server import serve
    ck = _checker(args)
    print(f"loaded {len(ck.data.laps)} laps ({len(ck.data.valid())} valid) from "
          f"{len(ck.data.files)} file(s) in {ck.load_s:.2f} s · {len(ck.track.corners)} corners · "
          f"{'Claude translator on' if ck.translator else 'rule parser only'}")
    serve(ck, args.host, args.port, args.log or checklog.DEFAULT, not args.no_browser)
    return 0


def cmd_demo(args) -> int:
    from claimcheck import synth
    d = Path(args.dir) if args.dir else Path(tempfile.mkdtemp(prefix="claimcheck-demo-"))
    files = synth.demo(d)
    print(f"synthetic sessions in {d}: BB brakes 15 m early at T2, 15 m late on the throttle at T5")
    args.files = [str(f) for f in files]
    args.driver = ["AA", "BB"]
    return cmd_serve(args)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="claimcheck", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, files=True):
        if files:
            p.add_argument("files", nargs="+", help=".vbo files or folders")
        p.add_argument("--driver", action="append", help="driver per file, in order: AA or AA=1-6,BB=7-12")
        p.add_argument("--alias", action="append", help="corner nickname, e.g. Hairpin=T6")
        p.add_argument("--no-claude", action="store_true", help="rule parser only, never call the API")
        p.add_argument("--track", help="track profile JSON: pinned corner names (see corners --save-track)")
        p.add_argument("--log", help=f"append checks here (serve default: {checklog.DEFAULT})")

    p = sub.add_parser("laps", help="every lap, and whether it counts"); common(p); p.set_defaults(fn=cmd_laps)
    p = sub.add_parser("corners", help="the corners as the tool numbers them"); common(p)
    p.add_argument("--save-track", help="write a track profile pinning these corners by GPS apex")
    p.set_defaults(fn=cmd_corners)
    p = sub.add_parser("check", help="check claims in the terminal"); common(p)
    p.add_argument("-c", "--claim", action="append", required=True); p.set_defaults(fn=cmd_check)
    for name, fn, files in (("serve", cmd_serve, True), ("demo", cmd_demo, False)):
        p = sub.add_parser(name, help="the local page" if name == "serve" else "the page, on synthetic data")
        common(p, files)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--no-browser", action="store_true")
        if name == "demo":
            p.add_argument("--dir")
        p.set_defaults(fn=fn)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"claimcheck: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
