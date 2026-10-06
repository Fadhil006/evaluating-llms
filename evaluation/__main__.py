"""Run offline fixtures or explicitly opt into capped live evaluation."""

import argparse
import json

from .runner import DEFAULT_MODELS, run, run_live


def main():
    parser = argparse.ArgumentParser(description="Fixture evaluation by default; live requires --live")
    parser.add_argument("--dataset", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixtures", help="JSON {model: {item_id: answer or {status, answer/error}}}")
    mode.add_argument("--live", action="store_true", help="explicitly opt into real provider requests")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--models", nargs="+", help="fixture model labels")
    parser.add_argument("--model", help="exact allowlisted free model ID (live only)")
    parser.add_argument("--provider", help="pinned provider slug (live only)")
    parser.add_argument("--max-requests", type=int, default=4, help="cumulative live attempt cap, at most 40")
    args = parser.parse_args()
    if args.live:
        if not args.model or not args.provider or args.models:
            parser.error("--live requires --model and --provider; --models is fixture-only")
    elif args.model or args.provider or args.max_requests != 4:
        parser.error("--model, --provider and --max-requests are live-only")
    try:
        result = (run_live(args.dataset, args.run_dir, args.model, args.provider, args.max_requests)
                  if args.live else run(args.dataset, args.fixtures, args.run_dir,
                                        args.models if args.models is not None else DEFAULT_MODELS))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"run failed: {exc}\n")
    print(json.dumps(result, indent=2))
    if result["paused"]:
        parser.exit(2, "Paused: inspect saved state before resuming; unresolved live attempts require manual intervention.\n")


if __name__ == "__main__":
    main()
