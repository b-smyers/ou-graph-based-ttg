#!/usr/bin/env python3

import os
import sys
import json
import signal
from tenacity import retry, wait_random_exponential
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("[ERROR] GEMINI_API_KEY not set", file=sys.stderr)
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-2.0-flash-lite"

with open("prompt.md", "r") as file:
    SYSTEM_PROMPT = file.read()

ALLOWED_TYPES = {"NONE", "GPA", "LEVEL", "COURSE", "PLACEMENT", "AND", "OR", "OTHER"}

# --------------------
# Validation / Sanitization
# --------------------


def sanitize_requisite(obj: dict) -> dict:
    if not isinstance(obj, dict):
        print(f"[DEBUG] {obj}")
        raise ValueError("Requisite must be an object")

    t = obj.get("type")
    if t not in ALLOWED_TYPES:
        raise ValueError(f"Invalid requisite type: {t}")

    if t == "NONE":
        return {"type": "NONE"}

    if t == "GPA":
        return {"type": "GPA", "gpa": float(obj["gpa"])}

    if t == "LEVEL":
        return {"type": "LEVEL", "level": obj["level"].lower()}

    if t == "COURSE":
        return {"type": "COURSE", "course": obj["course"]}

    if t == "PLACEMENT":
        return {
            "type": "PLACEMENT",
            "subject": obj["subject"],
            "level": int(obj["level"]),
        }

    if t in ("AND", "OR"):
        reqs = obj.get("requirements")
        if not isinstance(reqs, list) or not reqs:
            raise ValueError("AND/OR requires non-empty requirements list")

        return {
            "type": t,
            "requirements": [sanitize_requisite(r) for r in reqs],
        }

    if t == "OTHER":
        return {"type": "OTHER", "other": obj["other"]}

    raise AssertionError("Unreachable")


# --------------------
# LLM Parsing
# --------------------


@retry(wait=wait_random_exponential(multiplier=1, max=60))
def prompt_model(prompt):
    return client.models.generate_content(
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

    response = prompt_model(prompt)

    try:
        parsed = json.loads(response.text or "")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from LLM: {response.text}") from e

    sanitized = sanitize_requisite(parsed)
    return sanitized


# --------------------
# Signal Handler
# --------------------

interrupted = False
processed_courses = []


def signal_handler(sig, frame):
    global interrupted
    if not interrupted:
        interrupted = True
        print("\n\n[INFO] Interrupt received. Saving processed courses and exiting...")
        # Don't exit immediately - let the main loop handle cleanup
        raise KeyboardInterrupt


# --------------------
# Main
# --------------------


def main():
    global interrupted, processed_courses

    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)

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

    # Check if output file exists and read existing courses
    existing_courses = []
    existing_course_codes = set()

    if output_path and os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_courses = json.load(f)
                if isinstance(existing_courses, list):
                    # Extract course codes from existing courses
                    existing_course_codes = {
                        course.get("code")
                        for course in existing_courses
                        if course.get("code")
                    }
                    print(
                        f"[INFO] Found {len(existing_course_codes)} existing courses in output file"
                    )
                else:
                    print(
                        "[WARNING] Output file exists but is not a JSON array, will overwrite",
                        file=sys.stderr,
                    )
                    existing_courses = []
                    existing_course_codes = set()
        except (json.JSONDecodeError, IOError) as e:
            print(
                f"[WARNING] Could not read existing output file: {e}, will overwrite",
                file=sys.stderr,
            )
            existing_courses = []
            existing_course_codes = set()

    # Start with existing courses
    processed_courses = existing_courses.copy()

    total = len(raw_courses)
    processed_count = len(existing_courses)
    skipped = 0
    new_processed = 0
    errors = 0

    try:
        # Process new courses
        for i, c in enumerate(raw_courses):
            # Check for interrupt
            if interrupted:
                print("\n[INFO] Interrupt detected. Saving current progress...")
                break

            # Generate course code to check if it already exists
            course_code = f"{c.get('subject')} {c.get('catalogNumber')}"

            # Skip if course already exists in output
            if course_code in existing_course_codes:
                skipped += 1
                continue

            print(f"Processing {i + 1}/{total}: {course_code}")

            # Explicit field mapping
            name = c.get("title")
            raw_req = c.get("requisite")

            if not name or not course_code:
                print(
                    f"[WARNING] Course missing required name or code: {c}",
                    file=sys.stderr,
                )
                errors += 1
                continue

            try:
                course_obj = {
                    "name": name,
                    "code": course_code,
                    "requisite_string": raw_req,
                    "requisite": parse_requisite(raw_req),
                }
                processed_courses.append(course_obj)
                existing_course_codes.add(course_code)
                new_processed += 1
                processed_count += 1

            except KeyboardInterrupt:
                # Re-raise KeyboardInterrupt to break out of the loop
                interrupted = True
                print(
                    "\n[INFO] Interrupt during processing. Saving current progress..."
                )
                break
            except Exception as e:
                print(
                    f"[ERROR] Failed to parse requisite for {course_code}: {e}",
                    file=sys.stderr,
                )
                # Create a fallback object with NONE type
                course_obj = {
                    "name": name,
                    "code": course_code,
                    "requisite_string": raw_req,
                    "requisite": {"type": "NONE"},
                }
                processed_courses.append(course_obj)
                existing_course_codes.add(course_code)
                new_processed += 1
                processed_count += 1
                errors += 1

    except KeyboardInterrupt:
        # This handles KeyboardInterrupt raised by the signal handler
        pass

    # Always write the processed courses to file
    try:
        print(f"\nSaving {len(processed_courses)} courses to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(processed_courses, f, ensure_ascii=False, indent=2)

        print(f"\nSummary:")
        print(f"  Total courses in input: {total}")
        print(f"  Already processed (from file): {len(existing_courses)}")
        print(f"  Skipped (already in file): {skipped}")
        print(f"  Newly processed this run: {new_processed}")
        print(f"  Processing errors: {errors}")
        print(f"  Total in output file: {len(processed_courses)}")

        if interrupted:
            print(f"\n[INFO] Processing interrupted. Progress saved to {output_path}")
            print(f"       Resume by running the same command again.")
            sys.exit(130)  # Standard exit code for SIGINT
        else:
            print(f"\n[SUCCESS] All courses processed and saved to {output_path}")

    except Exception as e:
        print(f"\n[ERROR] Failed to save output file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
