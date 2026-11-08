"""Command line interface for the synthetic dataset generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import SYNTHETIC_DIR, build_benchmark


def cmd_build(args) -> None:
    out_dir = Path(args.out) if args.out else SYNTHETIC_DIR
    summary = build_benchmark(out_dir=out_dir)
    print(json.dumps(summary["summary"], indent=2))
    print(f"Wrote {out_dir / 'cities.joblib'}")
    print(f"Wrote {out_dir / 'benchmark.json'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthetic EV charging-demand generator")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="generate the 400-city benchmark")
    build.add_argument("--out", type=Path, default=None, help="output directory (default: data/synthetic)")
    build.set_defaults(func=cmd_build)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
