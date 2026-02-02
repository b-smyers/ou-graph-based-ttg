import sys
import json
import re
from typing import List, Dict, Set, Tuple
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import requests

BASE_URL = "https://www.catalogs.ohio.edu/content.php"
OUTPUT_FILE = "programs.json"
PROGRAM_TYPES = [
    "Certificate",
    "Major Program (Associate)",
    "Major Program (Baccalaureate)",
    "Minor",
]


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


def extract_catalogs(html: str) -> List[Tuple[int, str, int, bool]]:
    """Extract catalog information from HTML."""
    catalog_pattern = re.compile(
        r'<option value="(\d+)".*>((?:Ohio|OHIO) University [^\d]*(\d\d)?\d\d\s*-\s*((?:\d\d)?\d\d).*)<\/option>'
    )

    catalogs = []
    seen_ids = set()

    for match in catalog_pattern.finditer(html):
        catoid = int(match.group(1))
        if catoid in seen_ids:
            continue

        seen_ids.add(catoid)
        catalog_year = match.group(4)
        if len(catalog_year) == 2 and match.group(3):
            catalog_year = match.group(3) + catalog_year

        catalog_name = match.group(2)
        archived = "archived" in catalog_name.lower()
        catalogs.append((catoid, catalog_name, int(catalog_year), archived))

    return catalogs


def extract_navoids(html: str) -> Set[int]:
    """Extract navigation IDs from HTML."""
    navoid_pattern = re.compile(
        r'<a href=".*?catoid=\d+&navoid=(\d+)".*?>Curricula .*?<\/a>'
    )
    return {int(match.group(1)) for match in navoid_pattern.finditer(html)}


def extract_programs_from_html(html: str, catalog_info: Tuple) -> List[Dict]:
    """Extract all programs from a curricula page HTML."""
    catoid, navoid, catalog_name, catalog_year, archived = catalog_info
    programs = []

    # Compile patterns once
    link_pattern = re.compile(
        r'<a href="preview_program\.php\?catoid=\d+&poid=(\d+)&returnto=\d+">(.*?)<\/a>'
    )

    for program_type in PROGRAM_TYPES:
        # Find the section for this program type
        section_pattern = re.compile(
            rf"<p[^>]*><strong>{re.escape(program_type)}</strong></p>.*?<ul[^>]*>(.*?)</ul>",
            re.DOTALL | re.IGNORECASE,
        )

        section_match = section_pattern.search(html)
        if not section_match:
            continue

        ul_content = section_match.group(1)

        # Extract all programs in this section
        for match in link_pattern.finditer(ul_content):
            poid = int(match.group(1))
            program_name = match.group(2).strip()

            programs.append(
                {
                    "catoid": catoid,
                    "poid": poid,
                    "catalog_name": catalog_name,
                    "catalog_year": catalog_year,
                    "catalog_archived": archived,
                    "program_type": program_type,
                    "program_name": program_name,
                    "link": f"https://www.catalogs.ohio.edu/preview_program.php?catoid={catoid}&poid={poid}",
                }
            )

    return programs


def main():
    print("[INFO] Collecting catalog IDs and curricula pages")

    # Step 1: Get initial page and extract catalogs
    try:
        initial_html = fetch_with_retry(BASE_URL, allow_redirects=True, timeout=5)
    except Exception as e:
        print(f"[ERROR] Failed to fetch initial page: {e}")
        sys.exit(1)

    catalogs = extract_catalogs(initial_html)
    print(f"[INFO] Found {len(catalogs)} catalogs")

    if not catalogs:
        print("[ERROR] No catalog IDs could be found")
        sys.exit(1)

    # Step 2: Collect curricula pages for each catalog
    curricula_pages = []

    for catalog_info in catalogs:
        catoid = catalog_info[0]

        # For the first catalog, we might already have the HTML from initial fetch
        if catoid == catalogs[0][0]:
            html = initial_html
        else:
            url = f"{BASE_URL}?catoid={catoid}"
            try:
                html = fetch_with_retry(url, allow_redirects=True, timeout=5)
            except Exception as e:
                print(f"[WARN] Failed to fetch catalog {catoid}: {e}")
                continue

        navoids = extract_navoids(html)
        for navoid in navoids:
            curricula_pages.append((catoid, navoid, *catalog_info[1:]))

    print(f"[INFO] Found {len(curricula_pages)} curricula pages")

    if not curricula_pages:
        print("[ERROR] No curricula pages could be found")
        sys.exit(1)

    # Step 3: Extract programs from each curricula page
    print("[INFO] Collecting programs")
    all_programs = []

    for page_info in curricula_pages:
        catoid, navoid = page_info[0], page_info[1]
        url = f"{BASE_URL}?catoid={catoid}&navoid={navoid}"

        try:
            html = fetch_with_retry(url, allow_redirects=True, timeout=5)
            programs = extract_programs_from_html(html, page_info)
            all_programs.extend(programs)
        except Exception as e:
            print(f"[WARN] Failed to fetch curricula page {catoid}/{navoid}: {e}")
            continue

    # Save results
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_programs, f, indent=2)

    print(f"[INFO] Extracted {len(all_programs)} programs and saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
