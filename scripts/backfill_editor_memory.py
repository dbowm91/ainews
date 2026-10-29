#!/usr/bin/env python3
"""Preview or run the restartable legacy-to-category-memory import."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app import create_app  # noqa: E402
from services.memory.lifecycle import backfill_legacy_memories  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--execute", action="store_true", help="Persist this batch; default is dry run")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        result = backfill_legacy_memories(
            batch_size=args.batch_size,
            offset=args.offset,
            dry_run=not args.execute,
        )
    print(json.dumps({"mode": "execute" if args.execute else "dry_run", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
