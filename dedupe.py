#!/usr/bin/env python3
"""
dedupe.py

Deduplicate a large JSON file by keeping only unique combinations of:
- subject
- catalogNumber
- component

Usage:
    python dedupe.py input.json [output.json]

If output.json is not provided, results are written to stdout.
"""

import sys
import json

KEYS = ("subject", "catalogNumber", "component")


def die(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        die("Usage: dedupe.py <input.json> [output.json]")

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) >= 3 else None

    seen = set()
    deduped = []

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        die(f"Failed to read JSON: {e}")

    if not isinstance(data, list):
        die("Top-level JSON must be an array")

    for idx, obj in enumerate(data):
        if not isinstance(obj, dict):
            continue

        try:
            key = tuple(obj[k] for k in KEYS)
        except KeyError:
            # Skip entries missing required fields
            continue

        if key in seen:
            continue

        seen.add(key)
        deduped.append(obj)

    try:
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(deduped, f, indent=2)
        else:
            json.dump(deduped, sys.stdout, indent=2)
    except Exception as e:
        die(f"Failed to write output: {e}")


if __name__ == "__main__":
    main()
