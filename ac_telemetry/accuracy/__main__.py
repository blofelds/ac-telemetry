"""CLI: ``python -m ac_telemetry.accuracy …``

Works offline on session artefacts even when the runtime has accuracy off.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ac_telemetry.accuracy.paths import gt_path, session_dir
from ac_telemetry.accuracy.score import (
    load_gt_list,
    prefills_from_csv,
    save_gt,
    score_session,
)
from ac_telemetry.store.laps import LapStore


def _cmd_prefill(args: argparse.Namespace) -> int:
    store = LapStore(Path(args.data_dir))
    laps = store.list_laps(session_id=args.session_id, limit=500)
    draft = prefills_from_csv(laps)
    out = {"session_id": args.session_id, "laps": draft}
    text = json.dumps(out, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote GT prefill → {args.output} ({len(draft)} laps)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def _cmd_gt(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.gt_file).read_text(encoding="utf-8"))
    gt_laps = load_gt_list(raw)
    path = save_gt(
        data_dir=Path(args.data_dir),
        session_id=args.session_id,
        gt_laps=gt_laps,
        subdir=args.subdir,
    )
    print(f"Saved GT ({len(gt_laps)} laps) → {path}")
    if args.score:
        return _score(args, gt_laps)
    return 0


def _score(args: argparse.Namespace, gt_laps: list | None = None) -> int:
    data_dir = Path(args.data_dir)
    sid = args.session_id
    subdir = args.subdir
    if gt_laps is None:
        path = gt_path(session_dir(data_dir, sid, subdir=subdir))
        if not path.is_file():
            print(f"Missing GT file: {path}", file=sys.stderr)
            return 2
        gt_laps = load_gt_list(json.loads(path.read_text(encoding="utf-8")))
    report = score_session(
        data_dir=data_dir,
        session_id=sid,
        gt_laps=gt_laps,
        subdir=subdir,
        lap_store=LapStore(data_dir),
    )
    print(
        f"write%={report['write_pct']}% "
        f"({report['write_matches']}/{report['gt_laps']}) "
        f"ocr-sample%={report['ocr_sample_pct']}% "
        f"misses={report['write_misses']} extras={report['write_extras']}"
    )
    print(f"score → {report['artefact_dir']}/score.md")
    print(f"review → {report['artefact_dir']}/review.md")
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    return _score(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ac_telemetry.accuracy",
        description=(
            "Stint LAST accuracy: GT prefill/confirm + write%/ocr-sample% scores. "
            "Runtime capture requires accuracy.enabled; scoring works offline."
        ),
    )
    parser.add_argument(
        "--data-dir",
        default="data/sessions",
        help="Session CSV root (default: data/sessions)",
    )
    parser.add_argument(
        "--subdir",
        default="accuracy",
        help="Accuracy artefact subdir under data-dir (default: accuracy)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prefill = sub.add_parser(
        "prefill", help="Draft GT list from laps.csv for a session"
    )
    p_prefill.add_argument("session_id")
    p_prefill.add_argument(
        "-o", "--output", default=None, help="Write JSON file (default: stdout)"
    )
    p_prefill.set_defaults(func=_cmd_prefill)

    p_gt = sub.add_parser("gt", help="Save confirmed GT JSON and optionally score")
    p_gt.add_argument("session_id")
    p_gt.add_argument("gt_file", help="JSON file: {laps:[...]} or bare list")
    p_gt.add_argument(
        "--score",
        action="store_true",
        help="Compute scores after saving GT",
    )
    p_gt.set_defaults(func=_cmd_gt)

    p_score = sub.add_parser(
        "score", help="Score session using saved gt.json under accuracy/"
    )
    p_score.add_argument("session_id")
    p_score.set_defaults(func=_cmd_score)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
