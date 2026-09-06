"""CLI command to audit and verify link integrity across all public items.

Usage:
    python -m app.cli.verify_links [--live]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.link_validator import validate_public_items_links
from app.core.public_loader import PublicContentLoader


async def main() -> int:
    parser = argparse.ArgumentParser(description="Audit link integrity for abtahi.fyi public plane.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform active network reachability checks against canonical URLs.",
    )
    args = parser.parse_args()

    loader = PublicContentLoader()
    items = loader.load_all_items()
    link_items = [item for item in items if item.canonical_url]

    print(f"Auditing {len(link_items)} public items with canonical URLs (live={args.live})...\n")

    results = await validate_public_items_links(link_items, live_network_check=args.live)
    failed = False

    for item in link_items:
        res = results.get(item.id)
        if not res:
            continue
        if res.is_valid:
            status_text = f"HTTP {res.status_code}" if res.status_code else "SYNTAX OK"
            print(f" [PASS] {item.id} -> {res.url} ({status_text})")
        else:
            failed = True
            print(f" [FAIL] {item.id} -> {res.url} | Error: {res.error_message}")

    print("\n" + "=" * 60)
    if failed:
        print("LINK INTEGRITY AUDIT FAILED: Broken or invalid URLs detected.")
        return 1
    else:
        print("LINK INTEGRITY AUDIT PASSED: All canonical links are sound.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
