"""
utils.py

Shared utility functions for scheduling and requirement processing.
"""

from typing import Set
from scheduling_types import (
    Requirement,
    RequirementType,
    Course,
    Or,
    And,
    CreditsFrom,
    ChooseN,
)


def pattern_allows(pattern, is_spring: bool, year: int):
    """Return True if a course with `pattern` may be scheduled in the term.

    - `is_spring`: True for spring semesters, False for fall semesters
    - `year`: integer year (e.g., 2025)
    """
    if not pattern:
        return True

    p = pattern.lower()
    # summer terms are not supported by the scheduler; treat summer-only as disallowed
    if p == "summer":
        return False
    if p == "fall and spring":
        return True
    if p == "fall":
        return not is_spring
    if p == "spring":
        return is_spring
    if p == "fall even":
        return (not is_spring) and (year % 2 == 0)
    if p == "fall odd":
        return (not is_spring) and (year % 2 == 1)
    if p == "spring even":
        return is_spring and (year % 2 == 0)
    if p == "spring odd":
        return is_spring and (year % 2 == 1)
    if p == "summer even":
        return False
    if p == "summer odd":
        return False
    if p == "irregular":
        # allowed any time, but caller may choose to warn
        return True
    if p == "arranged":
        return True
    if p == "deactivated":
        return False

    # Unknown patterns default to allowed
    return True


def extract_course_codes(req: Requirement) -> Set[str]:
    """
    Recursively collect all course codes from Course leaves anywhere in the tree.
    """
    codes = set()
    if isinstance(req, Course):
        codes.add(req.course)
    # All composite types (And, Or, CreditsFrom, ChooseN) have a 'requirements' list
    if (
        isinstance(req, Or)
        or isinstance(req, And)
        or isinstance(req, CreditsFrom)
        or isinstance(req, ChooseN)
    ):
        for child in req.requirements:
            codes.update(extract_course_codes(child))
    return codes


def collect_all_course_codes(req) -> Set[str]:
    """
    Recursively collect all course codes from any Course leaf.
    Handles both a single node and a list of nodes.
    """
    codes = set()

    # If req is a list, process each element
    if isinstance(req, list):
        for item in req:
            codes.update(collect_all_course_codes(item))
        return codes

    # If it's a Course leaf (identified by its type)
    if hasattr(req, "type") and req.type == RequirementType.COURSE:
        if hasattr(req, "course"):
            codes.add(req.course)
        return codes

    # If it's a composite node with a 'requirements' list (AND, OR, etc.)
    if hasattr(req, "requirements") and isinstance(req.requirements, list):
        for child in req.requirements:
            codes.update(collect_all_course_codes(child))

    return codes
