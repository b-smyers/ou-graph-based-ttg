import math
import json
import requests

base_url = "https://ais.kube.ohio.edu/api/course-offerings"

endpoints = {
    "INSTRUCTORS": "/data/instructors",
    "SUBJECTS": "/data/subjects",
    "TERMS": "/data/terms",
    "DEFAULT": "/data/terms/default",
    "BUILDINGS": "/data/buildings",
    "PROGRAMS": "/data/programs",
    "CATALOG_URLS": "/data/catalog-urls",
    "BRICKS": "/data/bricks",
    "THEMES": "/data/bricks/themes",
    "COUNTS": "/search/counts",
    "QUERY": "/search/query",
}


def get_endpoint_res(name):
    target_url = base_url + endpoints[name]
    r = requests.get(target_url)
    r.raise_for_status()
    return r


def get_endpoint(name):
    filename = input(f"Enter filename (default {name}): ").strip()

    r = get_endpoint_res(name)

    with open(f"{filename or name}.json", "w", encoding="utf-8") as f:
        f.write(r.text)

    print(f"[ Success ]: Saved {filename or name}.json\n")


def get_courses():
    # Get term year
    r = get_endpoint_res("TERMS")
    unique_years_list = sorted({item["year"] for item in r.json()}, reverse=True)
    print("Term Years: ")
    choice = -1
    while choice <= 0 or choice > len(unique_years_list):
        for i, year in enumerate(unique_years_list):
            print(f"{i + 1}. {year}")
        choice = int(input("Enter term year option (default 1): ") or 1)
    term_year = unique_years_list[choice - 1]

    # Get term semester
    print("Term Semesters:\n1. Fall\n2. Spring\n3. Summer")

    term_semesters = []

    while not term_semesters:
        print("Examples: <enter>, 1, 1 2")
        raw = input("Enter term year option(s): ").strip()

        # <enter> → no selection
        if not raw:
            break

        try:
            choices = {int(c) for c in raw.split()}
        except ValueError:
            print("Invalid input. Use numbers separated by spaces.")
            continue

        invalid = [c for c in choices if c < 1 or c > 3]
        if invalid:
            print("Invalid option(s):", invalid)
            continue

        if 1 in choices:
            term_semesters.append("FALL")
        if 2 in choices:
            term_semesters.append("SPRING")
        if 3 in choices:
            term_semesters.extend(["SUMMER1", "SUMMER2", "SUMMERFULL"])

        selected_terms = [
            f"{item['strm']}::{item['code']}"
            for item in r.json()
            if item["year"] == term_year and item["code"] in term_semesters
        ]

        if len(selected_terms) == 0:
            print("[ Error ]: No terms with those options exist")
            return

    # Construct payload
    payload = {
        "terms": selected_terms,
        "campuses": ["ATHN"],
        "program": "",
        "subjects": [],
        "catalogNumber": "",
        "name": "",
        "topic": "",
        "level": "ALL",
        "status": ["OPEN", "WAITLIST", "FULL", "MAJORS", "PERMISSION"],
        "generalEducationTier1": [],
        "generalEducationTier2": [],
        "generalEducationTier3": [],
        "themes": [],
        "bricks": [],
        "isSync": True,
        "isAsync": True,
        "instructors": [],
        "description": "",
        "offeredInPerson": True,
        "offeredOnline": True,
        "startTime": "",
        "endTime": "",
        "days": [],
        "eligibleGrades": "",
        "building": [],
    }

    # Step 1: Get total count
    r = requests.post(base_url + endpoints["COUNTS"], json=payload)
    r.raise_for_status()
    course_count = r.json()["ATHN"]
    if course_count > 1000:
        print(f"\n[ Warning ]: This request will fetch {course_count} courses!")
    answer = input("This will take a while, are you sure you want to continue? [Y/n] ")
    if answer.lower() == "n":
        print("Action aborted.")
        return

    page_size = 50
    page_count = math.ceil(course_count / page_size)
    params = {"selectedTab": "ATHN", "page": 0, "pageSize": page_size}

    # Step 2: Clear and open file for streaming write
    with open("COURSES.json", "w", encoding="utf-8") as f:
        f.write("[")  # start JSON array

        for i in range(page_count):
            params["page"] = i
            r = requests.post(
                base_url + endpoints["QUERY"], params=params, json=payload
            )
            r.raise_for_status()
            courses = r.json()["results"]

            for j, course in enumerate(courses):
                if i != 0 or j != 0:
                    f.write(",\n")
                json.dump(course, f, ensure_ascii=False)

            print(f"Page {i + 1}/{page_count}")

        f.write("]")  # end JSON array

    print("All courses saved to COURSES.json")


options = [
    {
        "id": 1,
        "text": "Get instructors",
        "function": lambda: get_endpoint("INSTRUCTORS"),
    },
    {"id": 2, "text": "Get subjects", "function": lambda: get_endpoint("SUBJECTS")},
    {"id": 3, "text": "Get terms", "function": lambda: get_endpoint("TERMS")},
    {"id": 4, "text": "Get buildings", "function": lambda: get_endpoint("BUILDINGS")},
    {"id": 5, "text": "Get programs", "function": lambda: get_endpoint("PROGRAMS")},
    {
        "id": 6,
        "text": "Get catalog URLs",
        "function": lambda: get_endpoint("CATALOG_URLS"),
    },
    {"id": 7, "text": "Get bricks", "function": lambda: get_endpoint("BRICKS")},
    {"id": 8, "text": "Get themes", "function": lambda: get_endpoint("THEMES")},
    {"id": 9, "text": "Get courses", "function": get_courses},
    {"id": 0, "text": "Quit"},
]


def main():
    choice = -1
    while True:
        for opt in options:
            print(f"{opt['id']}. {opt['text']}")

        choice = int(input("Choose an option: "))
        if choice == 0:
            return

        for opt in options:
            if opt["id"] == choice:
                opt["function"]()  # actually call it
                break

    # for name, path in endpoints.items():
    #     target_url = base_url + path
    #     r = requests.get(target_url)
    #     r.raise_for_status()

    #     with open(f"{name}.json", "w", encoding="utf-8") as f:
    #         f.write(r.text)

    #     print(f"Saved {name}.json")


if __name__ == "__main__":
    main()
