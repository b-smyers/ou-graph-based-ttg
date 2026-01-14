#!/usr/bin/env python3

import os
import sys
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("[ERROR] GEMINI_API_KEY not set", file=sys.stderr)
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-2.0-flash-lite"

SYSTEM_PROMPT = """
You are a strict JSON parser for university course requisites.

Output exactly ONE JSON object matching this schema and nothing else.

Allowed forms only:

{ "type": "NONE" }

{ "type": "LEVEL", "level": "Choose one: freshman, sophomore, junior, senior" }

{ "type": "COURSE", "course": "SUBJECT NUMBER" }

{ "type": "PLACEMENT", "placement": "Placement Name" }

{ "type": "AND", "requirements": [ <requisite objects> ] }

{ "type": "OR", "requirements": [ <requisite objects> ] }

Rules:
- No extra fields
- No comments
- No markdown
- Nested AND / OR is allowed
- If no prerequisite exists, return { "type": "NONE" }
"""

ALLOWED_TYPES = {"NONE", "LEVEL", "COURSE", "PLACEMENT", "AND", "OR"}

# --------------------
# Validation / Sanitization
# --------------------


def sanitize_requisite(obj: dict) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("Requisite must be an object")

    t = obj.get("type")
    if t not in ALLOWED_TYPES:
        raise ValueError(f"Invalid requisite type: {t}")

    if t == "NONE":
        return {"type": "NONE"}

    if t == "LEVEL":
        return {"type": "LEVEL", "level": obj["level"].lower()}

    if t == "COURSE":
        return {"type": "COURSE", "course": obj["course"]}

    if t == "PLACEMENT":
        return {"type": "PLACEMENT", "placement": obj["placement"]}

    if t in ("AND", "OR"):
        reqs = obj.get("requirements")
        if not isinstance(reqs, list) or not reqs:
            raise ValueError("AND/OR requires non-empty requirements list")

        return {
            "type": t,
            "requirements": [sanitize_requisite(r) for r in reqs],
        }

    raise AssertionError("Unreachable")


# --------------------
# LLM Parsing
# --------------------


def parse_requisite(raw_text) -> dict:
    # Fast path — no LLM
    if raw_text is None:
        return {"type": "NONE"}

    if isinstance(raw_text, str):
        cleaned = raw_text.strip().lower()
        if cleaned == "" or cleaned in {
            "none",
            "n/a",
            "no prerequisite",
            "no prerequisites",
        }:
            return {"type": "NONE"}

    prompt = f"Requisite text:\n{raw_text}"

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]},
            {"role": "user", "parts": [{"text": prompt}]},
        ],
        config={
            "temperature": 0,
            "response_mime_type": "application/json",
        },
    )

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from LLM: {response.text}") from e

    print(parsed)
    sanitized = sanitize_requisite(parsed)
    print(sanitized)

    return sanitized


# --------------------
# Main
# --------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: parse_requisites.py <input.json> [output.json]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) >= 3 else None

    with open(input_path, "r", encoding="utf-8") as f:
        raw_courses = json.load(f)

    if not isinstance(raw_courses, list):
        print("[ERROR] Top-level JSON must be an array", file=sys.stderr)
        sys.exit(1)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("[")  # start JSON array

        total = len(raw_courses)

        for i, c in enumerate(raw_courses):
            print(f"Processing {i + 1}/{total}")

            # Explicit field mapping
            name = c.get("title")
            code = f"{c.get('subject')} {c.get('catalogNumber')}"
            raw_req = c.get("requisite")

            if not name or not code:
                raise ValueError("Course missing required name or code")

            course_obj = {
                "name": name,
                "code": code,
                "requisite": parse_requisite(raw_req),
            }

            # Write comma if not first item
            if i > 0:
                f.write(",\n")
            json.dump(course_obj, f, ensure_ascii=False)
            if raw_req:
                break

        f.write("]")  # end JSON array

    print(f"All courses saved to {output_path}")


if __name__ == "__main__":
    main()
