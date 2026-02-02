# get_course_patterns.py: Fetch course patterns from university catalog and add them to existing data.
import sys
import os
import json
import re
import requests


def parse_args(args):
    if len(args) != 1:
        raise ValueError("Usage: get_course_patterns.py <courses_path>")

    courses_path = args[0]
    if not os.path.exists(courses_path):
        raise ValueError(f"Error: Path '{courses_path}' does not exist.")
    if not os.path.isfile(courses_path):
        raise ValueError(f"Error: Path '{courses_path}' must be a file.")

    return courses_path


def get_pattern_tag(pattern_string: str) -> str:
    """Convert catalog pattern string to simplified lowercase tag"""
    pattern_string = pattern_string.strip()

    # Pattern mapping based on the simplified tags
    pattern_mapping = {
        "Summer Semester, Every Year": "summer",
        "Every Fall and Spring": "fall_and_spring",
        "Fall Semester, Even Years": "fall_even",
        "Spring Semester, Odd Years": "spring_odd",
        "Spring Semester, Every Year": "spring",
        "Fall Semester, Every Year": "fall",
        "Fall Semester, Odd Years": "fall_odd",
        "Spring Semester, Even Years": "spring_even",
        "Summer Semester, Even Years": "summer_even",
        "Summer Semester, Odd Years": "summer_odd",
        "Irregular": "irregular",
        "Arranged": "arranged",
        "Deactivated": "deactivated",
    }

    return pattern_mapping.get(pattern_string, "unknown")


def main(courses_path: str):
    url = "https://ohio.catalog.acalog.com/content.php?catoid=104&navoid=11681"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch course patterns. Status code: {response.status_code}")
        return

    # Load courses json
    with open(courses_path, "r") as f:
        courses = json.load(f)

    # Initialize all courses with "unknown" pattern
    for course in courses:
        course["pattern"] = "unknown"

    # Extract course patterns from catalog
    regex = r"<td[^\/]*?>([A-Z0-9]+)<\/td>\s*?<td.*?>([A-Z0-9]+?)<\/td>\s*?<td.*?>(.+?)<\/td>"
    matches = re.findall(regex, response.text, re.DOTALL)

    # Track which courses were found in catalog
    found_courses = set()

    for match in matches:
        subject = match[0].strip()
        number = match[1].strip()
        pattern_string = match[2].strip()
        code = f"{subject} {number}"
        if len(subject) > 8 or len(number) > 5:  # Debugging invalid entries
            print("[Invalid entry found]")
            print("subject:", subject)
            print("number:", number)
            print("pattern_string:", pattern_string)

        # Get pattern tag
        pattern_tag = get_pattern_tag(pattern_string)

        # Find the course by code and update pattern
        for course in courses:
            if course["code"] == code:
                course["pattern"] = pattern_tag
                found_courses.add(code)
                break

    # Report on courses not found in catalog
    all_course_codes = {course["code"] for course in courses}
    not_found = all_course_codes - found_courses
    if not_found:
        print(f"Warning: {len(not_found)} courses not found in catalog:")
        for code in sorted(not_found)[:10]:  # Show first 10
            print(f"  {code}")
        if len(not_found) > 10:
            print(f"  ... and {len(not_found) - 10} more")

    # Write back courses json with patterns
    with open(courses_path, "w") as f:
        json.dump(courses, f, indent=4)

    print(f"Updated {len(found_courses)} courses with patterns")
    print(f"Total courses in file: {len(courses)}")


if __name__ == "__main__":
    courses_path = parse_args(sys.argv[1:])
    main(courses_path)
