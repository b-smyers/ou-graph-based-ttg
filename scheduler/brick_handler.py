"""
brick_handler.py

Manages brick requirements, tracking, and reporting.
"""

import math
import re
from typing import Dict, List
from scheduling_types import ParsedCourse
from logger import logger


def initialize_bricks() -> Dict[str, Dict[str, float]]:
    """Initialize the bricks dictionary with requirements."""
    return {
        "FWS": {"current": 0.0, "required": 3.0},
        "FAW": {"current": 0.0, "required": 3.0},
        "FQR": {"current": 0.0, "required": 3.0},
        "FIE": {"current": 0.0, "required": 2.0},
        "PHTC": {"current": 0.0, "required": 3.0},
        "PHA": {"current": 0.0, "required": 3.0},
        "PNS": {"current": 0.0, "required": 3.0},
        "PSBS": {"current": 0.0, "required": 3.0},
        "ACSW": {"current": 0.0, "required": 3.0},
        "ANW": {"current": 0.0, "required": 3.0},
        "ACNW": {"current": 0.0, "required": 3.0},
        "BSL": {"current": 0.0, "required": 1.0},
        "BER": {"current": 0.0, "required": 1.0},
        "BDP": {"current": 0.0, "required": 1.0},
        "BLD": {"current": 0.0, "required": 1.0},
        "CAP": {"current": 0.0, "required": 2.0},
    }


def update_bricks_from_courses(
    bricks: Dict[str, Dict[str, float]], courses: List[ParsedCourse]
) -> None:
    """Update brick counts based on scheduled courses."""
    for course in courses:
        for brick_str in course.bricks:
            match = re.search(r"\(([A-Z]+)\)", brick_str)
            if not match:
                logger.error(
                    f"Brick string could not be matched to a category: {brick_str}"
                )
                continue
            category = match.group(1)
            if category in bricks:
                bricks[category]["current"] += course.min_credits
            else:
                logger.warn(
                    f"Unknown brick category '{category}' from course {course.code}"
                )


def report_bricks(bricks: Dict[str, Dict[str, float]]) -> None:
    """Print brick satisfaction status."""
    print("\n=== Final Bricks Status ===")
    for key in bricks.keys():
        brick = bricks[key]
        if brick["current"] < brick["required"]:
            print(
                f"{key} - {brick['current']:.1f} / {brick['required']:.1f} (remaining: {brick['required'] - brick['current']:.1f})"
            )
        else:
            print(
                f"{key} - SATISFIED ({brick['current']:.1f} / {brick['required']:.1f})"
            )


def get_remaining_brick_count(bricks: Dict[str, Dict[str, float]]) -> int:
    """Return number of remaining bricks needed."""
    # assume each brick is 3 credits for now, but this could be adjusted if needed
    return sum(
        math.ceil((brick["required"] - brick["current"]) / 3)
        for brick in bricks.values()
        if brick["current"] < brick["required"]
    )
