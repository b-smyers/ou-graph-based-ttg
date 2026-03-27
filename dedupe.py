"""
dedupe.py

Deduplicate a large JSON file by keeping only unique combinations of:
- subject
- catalogNumber
- component

Usage:
    python dedupe.py input.json <output.json>
"""

import sys
import json

KEYS = ("subject", "catalogNumber", "component")


def main():
    if len(sys.argv) < 3:
        print("Usage: dedupe.py <input.json> <output.json>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    seen = set()
    deduped = []

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print("[ERROR] Top-level JSON must be an array", file=sys.stderr)
        sys.exit(1)

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
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(deduped, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to write output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
