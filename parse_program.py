import json
import re
import os
import requests
import sys
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("[ERROR] GEMINI_API_KEY not set", file=sys.stderr)
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash-lite"
PROMPT_PATH = "prompt_parse_program.md"
PROGRAMS_DIRECTORY = "data/programs/"

OUTPUT_FILE = "program.bs7477.json"
PROGRAM_URL = "https://www.catalogs.ohio.edu/preview_program.php?catoid=104&poid=34482"

with open(PROMPT_PATH, "r") as file:
    SYSTEM_PROMPT = file.read()

ALLOWED_TYPES = {
    "NONE",
    "PERMISSION",
    "GPA",
    "LEVEL",
    "COURSE",
    "PLACEMENT",
    "AND",
    "OR",
    "CREDITS_FROM",
    "CHOOSE_N",
    "OTHER",
}


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=16),
)
def fetch_with_retry(url: str, **kwargs) -> str:
    """Fetch URL with retry logic and return text."""
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp.text


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=16),
)
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


def sanitize_requisite(obj: dict) -> dict:
    if not isinstance(obj, dict):
        print(f"[DEBUG] {obj}")
        raise ValueError("Requisite must be an object")

    t = obj.get("type")
    if t not in ALLOWED_TYPES:
        raise ValueError(f"Invalid requisite type: {t}")

    if t == "NONE":
        return {"type": "NONE"}

    if t == "PERMISSION":
        return {"type": "PERMISSION", "authority": obj["authority"]}

    if t == "GPA":
        return {"type": "GPA", "gpa": float(obj["gpa"])}

    if t == "LEVEL":
        return {"type": "LEVEL", "level": obj["level"].lower()}

    if t == "COURSE":
        return {"type": "COURSE", "course": obj["course"], "timing": obj["timing"]}

    if t == "PLACEMENT":
        return {
            "type": "PLACEMENT",
            "subject": obj["subject"],
            "level": obj["level"],
        }

    if t in ("AND", "OR"):
        reqs = obj.get("requirements")
        if not isinstance(reqs, list) or not reqs:
            raise ValueError("AND/OR requires non-empty requirements list")

        return {
            "type": t,
            "requirements": [sanitize_requisite(r) for r in reqs],
        }

    if t == "CREDITS_FROM":
        reqs = obj.get("requirements")
        if not isinstance(reqs, list) or not reqs:
            raise ValueError("CREDITS_FROM requires non-empty requirements list")

        return {
            "type": t,
            "credits_required": float(obj["credits_required"]),
            "requirements": [sanitize_requisite(r) for r in reqs],
        }

    if t == "CHOOSE_N":
        reqs = obj.get("requirements")
        if not isinstance(reqs, list) or not reqs:
            raise ValueError("AND/OR requires non-empty requirements list")

        return {
            "type": t,
            "choose": int(obj["choose"]),
            "requirements": [sanitize_requisite(r) for r in reqs],
        }

    if t == "OTHER":
        return {"type": "OTHER", "other": obj["other"]}

    raise AssertionError("Unreachable")


def parse_program(raw_text):
    prompt = f"Wrap all requirements in an AND requirement.\nProgram page requirements: {raw_text}"
    response = prompt_model(prompt)

    try:
        parsed = json.loads(response.text or "")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from LLM: {response.text}") from e

    sanitized = sanitize_requisite(parsed)
    return sanitized


def main():
    try:
        html = fetch_with_retry(PROGRAM_URL, allow_redirects=True, timeout=5)
    except Exception as e:
        print(f"[ERROR] Failed to fetch initial page: {e}")
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")

    core_divs = soup.find_all("div", class_="acalog-core")

    texts = []
    for div in core_divs:
        text = div.get_text(separator="\n", strip=True)
        # collapse 3+ newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        texts.append(text)

    raw_text = "\n\n".join(texts)

    parsed_program = parse_program(raw_text)

    output_json = {
        "catoid": 104,
        "poid": 34482,
        "catalog_name": "Ohio University 2025-2026 Undergraduate Catalog",
        "catalog_year": 2026,
        "catalog_archived": False,
        "program_type": "Major Program (Baccalaureate)",
        "program_name": "Artificial Intelligence Major (B.S.)",
        "link": "https://www.catalogs.ohio.edu/preview_program.php?catoid=104&poid=34482",
        "requisite": parsed_program,
    }

    with open(PROGRAMS_DIRECTORY + OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
