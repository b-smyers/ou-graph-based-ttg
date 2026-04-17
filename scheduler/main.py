import json
from typing import List
from scheduling_types import (
    Requirement,
    Program,
    Config,
    Placement,
)
from data_loader import (
    load_json,
    parse_requirements,
    get_level,
    initialize_courses,
    PROGRAMS_DIRECTORY,
)
from create_schedule import create_schedule

if __name__ == "__main__":
    args = {
        "poid": 34482,
        "start_term": "fall",
        "start_year": 2026,
        "credits_per_semester": 16,
        "completed_coursework": [],
        "placements": [
            {"subject": "Math", "level": "3"},
            {"subject": "Computer Science", "level": "3"},
        ],
    }

    # Initialize the course catalog
    initialize_courses("data/courses/courses.parsed.json")

    program_data = load_json(PROGRAMS_DIRECTORY + f"program.{args['poid']}.json")
    program_requirements: List[Requirement] = parse_requirements(
        program_data["requisite"][
            "requirements"
        ]  # TODO: Jank solution because 'requisite' is not an array but an object
    )

    config = Config(
        program=Program(
            catalog_name=program_data["catalog_name"],
            catalog_year=program_data["catalog_year"],
            catalog_archived=program_data["catalog_archived"],
            program_type=program_data["program_type"],
            program_name=program_data["program_name"],
            program_link=program_data["link"],
            credits=120,
            requisite=program_requirements,
        ),
        completed_course_work=args["completed_coursework"],
        placements=[
            Placement(subject=placement["subject"], level=placement["level"])
            for placement in args["placements"]
        ],
        gpa=4.0,
        level=get_level(args["completed_coursework"]),
        credits_per_semester=args["credits_per_semester"],
        start_year=args["start_year"],
        start_term=args["start_term"],
    )

    output = create_schedule(config)
    # print(json.dumps(output, indent=2))
