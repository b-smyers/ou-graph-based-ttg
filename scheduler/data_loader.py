"""
data_loader.py

Handles loading and parsing of course and program data from JSON files.
Provides utilities for retrieving courses and calculating academic levels.
"""

import json
from typing import List

from scheduling_types import (
    Requirement,
    RequirementType,
    Course,
    GPA,
    Level,
    Placement,
    Permission,
    Other,
    Empty,
    Or,
    And,
    CreditsFrom,
    ChooseN,
    ParsedCourse,
    OfferingPattern,
)
from logger import logger

# Global course catalog
COURSES: List[ParsedCourse] = []

PROGRAMS_DIRECTORY = "data/programs/"


def load_json(path):
    """Load and parse a JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError as e:
        raise FileNotFoundError(f"File not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse {path} as JSON: {e}") from e


def parse_requirements(requirement_list) -> List[Requirement]:
    """Parse a list of requirement dictionaries into Requirement objects."""
    parsed = []
    for item in requirement_list:
        requirement_type = item["type"]
        match requirement_type:
            case RequirementType.NONE:
                parsed.append(Empty())
            case RequirementType.PERMISSION:
                parsed.append(Permission(**item))
            case RequirementType.LEVEL:
                parsed.append(Level(**item))
            case RequirementType.PLACEMENT:
                parsed.append(Placement(**item))
            case RequirementType.GPA:
                parsed.append(GPA(**item))
            case RequirementType.COURSE:
                parsed.append(Course(**item))
            case RequirementType.OR:
                parsed.append(
                    Or(
                        type=RequirementType.OR,
                        requirements=parse_requirements(item["requirements"]),
                    )
                )
            case RequirementType.AND:
                parsed.append(
                    And(
                        type=RequirementType.AND,
                        requirements=parse_requirements(item["requirements"]),
                    )
                )
            case RequirementType.CREDITS_FROM:
                parsed.append(
                    CreditsFrom(
                        credits_required=item["credits_required"],
                        requirements=parse_requirements(item["requirements"]),
                    )
                )
            case RequirementType.CHOOSE_N:
                parsed.append(
                    ChooseN(
                        choose=item["choose"],
                        requirements=parse_requirements(item["requirements"]),
                    )
                )
            case RequirementType.OTHER:
                parsed.append(Other(**item))
            case _:
                logger.error(
                    f"Invalid program data. No requirement type matched for {requirement_type}"
                )
                exit(1)
    return parsed


def get_course(code) -> ParsedCourse | None:
    """Retrieve a course by its code from the global catalog."""
    for course in COURSES:
        if course.code == code:
            return course
    return None


def get_level(completed_courses: List[str]) -> Level:
    """Calculate academic level based on completed courses."""
    total_credits = 0
    for code in completed_courses:
        course = get_course(code)
        if not course:
            logger.warn(f"Not counting course '{code}' for credits level")
            continue
        total_credits += course.min_credits

    if total_credits > 90:
        return Level(level="senior")
    elif total_credits > 60:
        return Level(level="junior")
    elif total_credits > 30:
        return Level(level="sophomore")
    else:
        return Level(level="freshman")


def initialize_courses(courses_json_path: str):
    """Load and initialize the global COURSES list from a JSON file."""
    global COURSES
    COURSES.clear()

    courses_data = load_json(courses_json_path)
    for course in courses_data:
        course_requirements = parse_requirements([course["requisite"]])
        COURSES.append(
            ParsedCourse(
                name=course["name"],
                code=course["code"],
                requisite_string=course["requisite_string"],
                requisite=course_requirements,
                component=course["component"],
                bricks=course["bricks"],
                min_credits=course["min_credits"],
                max_credits=course["max_credits"],
                pattern=OfferingPattern(course["pattern"]),
            )
        )
