from __future__ import annotations
from enum import Enum
from collections import deque
from functools import total_ordering
import json
import re
import sys
import os
from typing import (
    Annotated,
    ClassVar,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)
from pydantic import BaseModel, Field
from logger import logger
# import db


class RequirementType(str, Enum):
    NONE = "NONE"
    PERMISSION = "PERMISSION"
    LEVEL = "LEVEL"
    PLACEMENT = "PLACEMENT"
    GPA = "GPA"
    COURSE = "COURSE"
    OR = "OR"
    AND = "AND"
    CREDITS_FROM = "CREDITS_FROM"
    CHOOSE_N = "CHOOSE_N"
    OTHER = "OTHER"


T = TypeVar("T", bound=RequirementType)


class BaseRequirement(BaseModel, Generic[T]):
    type: T


class Or(BaseRequirement):
    type: Literal[RequirementType.OR] = RequirementType.OR
    requirements: list[Requirement]


class And(BaseRequirement):
    type: Literal[RequirementType.AND] = RequirementType.AND
    requirements: list[Requirement]


class Course(BaseRequirement):
    type: Literal[RequirementType.COURSE] = RequirementType.COURSE
    course: str
    timing: Literal["COMPLETED", "CONCURRENT", "CONCURRENT_OR_COMPLETED"]


class GPA(BaseRequirement):
    type: Literal[RequirementType.GPA] = RequirementType.GPA
    gpa: float


@total_ordering
class Placement(BaseRequirement):
    type: Literal[RequirementType.PLACEMENT] = RequirementType.PLACEMENT
    subject: str
    level: str

    def _rank(self) -> int:
        if self.level.isdigit():
            return int(self.level)
        return 0  # DV / unknown

    def __lt__(self, other: "Placement") -> bool:
        if not isinstance(other, Placement):
            return NotImplemented
        return self._rank() < other._rank()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Placement):
            return False
        return self._rank() == other._rank()


class Permission(BaseRequirement):
    type: Literal[RequirementType.PERMISSION] = RequirementType.PERMISSION
    authority: str


@total_ordering
class Level(BaseRequirement):
    type: Literal[RequirementType.LEVEL] = RequirementType.LEVEL
    level: Literal["freshman", "sophomore", "junior", "senior"]

    _level_order = {"freshman": 0, "sophomore": 1, "junior": 2, "senior": 3}

    def __eq__(self, other):
        if not isinstance(other, Level):
            return NotImplemented
        return self.level == other.level

    def __lt__(self, other):
        if not isinstance(other, Level):
            return NotImplemented
        return self._level_order[self.level] < self._level_order[other.level]


class Other(BaseRequirement):
    type: Literal[RequirementType.OTHER] = RequirementType.OTHER
    other: str


class Empty(BaseRequirement):
    type: Literal[RequirementType.NONE] = RequirementType.NONE


class CreditsFrom(BaseRequirement):
    type: Literal[RequirementType.CREDITS_FROM] = RequirementType.CREDITS_FROM
    credits_required: float
    requirements: List[Requirement]


class ChooseN(BaseRequirement):
    type: Literal[RequirementType.CHOOSE_N] = RequirementType.CHOOSE_N
    choose: int
    requirements: List[Requirement]


Requirement = Annotated[
    Union[
        Or,
        And,
        Course,
        GPA,
        Placement,
        Permission,
        Level,
        Other,
        Empty,
        CreditsFrom,
        ChooseN,
    ],
    Field(discriminator="type"),
]


class Program(BaseModel):
    catalog_name: str
    catalog_year: int
    catalog_archived: bool
    program_type: str
    program_name: str
    program_link: str
    credits: int
    code: str
    requisite: List[Requirement]


class Config(BaseModel):
    program: Program
    completed_course_work: List[str]
    placements: List[Placement]
    gpa: float
    level: Level
    credits_per_semester: int


class ParsedCourse(BaseModel):
    name: str
    code: str
    requisite_string: Optional[str]
    requisite: List[Requirement]
    component: str
    bricks: List[str]
    min_credits: float
    max_credits: float
    pattern: str


class Foundations(BaseModel):
    WS: int = 0
    WS_required: ClassVar[Literal[3]] = 3
    AW: int = 0
    AW_required: ClassVar[Literal[3]] = 3
    QR: int = 0
    QR_required: ClassVar[Literal[3]] = 3
    IE: int = 0
    IE_required: ClassVar[Literal[2]] = 2


class Pillars(BaseModel):
    HTC: int = 0
    HTC_required: ClassVar[Literal[3]] = 3
    HA: int = 0
    HA_required: ClassVar[Literal[3]] = 3
    NS: int = 0
    NS_required: ClassVar[Literal[3]] = 3
    SBS: int = 0
    SBS_required: ClassVar[Literal[3]] = 3


class Arches(BaseModel):
    CSW: int = 0
    CSW_required: ClassVar[Literal[3]] = 3
    NW: int = 0
    NW_required: ClassVar[Literal[3]] = 3
    CNW: int = 0
    CNW_required: ClassVar[Literal[3]] = 3


class Bridges(BaseModel):
    SL: int = 0
    SL_required: ClassVar[Literal[1]] = 1
    ER: int = 0
    ER_required: ClassVar[Literal[1]] = 1
    DP: int = 0
    DP_required: ClassVar[Literal[1]] = 1
    LD: int = 0
    LD_required: ClassVar[Literal[1]] = 1


class Capstone(BaseModel):
    CAP: int = 0
    CAP_required: ClassVar[Literal[2]] = 2


def parse_args(argv):
    if len(argv) < 2:
        raise ValueError(
            "Usage: create_schedule.py <program.json> <credits-per-semester>"
        )

    program_path = argv[0]
    try:
        credits_per_semester = int(argv[1])
    except ValueError:
        raise ValueError(f"credits-per-semester must be an integer, got: {argv[1]}")

    if not os.path.exists(program_path):
        raise ValueError(f"{program_path} does not exist")
    if not os.path.isfile(program_path):
        raise ValueError(f"{program_path} must be a file")
    if not credits_per_semester:
        raise ValueError("credits-per-semester must be a positive integer")

    if credits_per_semester < 12:
        logger.info("Credits Per Semester: Part-time enrollment")
    elif credits_per_semester <= 20:
        logger.info("Credits Per Semester: Full-time enrollment")
    elif credits_per_semester > 20:
        logger.info("Credits Per Semester: Overloaded enrollment")
    else:
        raise ValueError(f"Invalid credits per semester: {credits_per_semester}")

    return program_path, credits_per_semester


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError as e:
        raise FileNotFoundError(f"File not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse {path} as JSON: {e}") from e


def parse_requirements(requirement_list) -> List[Requirement]:
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


def pattern_allows(pattern, is_spring, year):
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
    if p == "fall_and_spring":
        return True
    if p == "fall":
        return not is_spring
    if p == "spring":
        return is_spring
    if p == "fall_even":
        return (not is_spring) and (year % 2 == 0)
    if p == "fall_odd":
        return (not is_spring) and (year % 2 == 1)
    if p == "spring_even":
        return is_spring and (year % 2 == 0)
    if p == "spring_odd":
        return is_spring and (year % 2 == 1)
    if p == "summer_even":
        return False
    if p == "summer_odd":
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


def find_longest_chain(tx, course_codes: List[str], config: Config):
    """
    Returns the longest prerequisite chain (as course codes) among the given courses.
    """

    query = """
    MATCH (start:Course)
    WHERE start.code IN $codes

    // Traverse through ReqGroup transparently, but only count Course nodes
    MATCH path = (start)-[:REQUIRES*]->(end:Course)

    WITH
        path,
        [n IN nodes(path) WHERE n:Course | n.code] AS course_chain

    RETURN
        course_chain,
        size(course_chain) AS length
    ORDER BY length DESC
    LIMIT 1
    """

    result = tx.run(query, codes=course_codes)
    record = result.single()

    if record is None:
        return [], 0

    return record["course_chain"], record["length"]


courses = []


def get_course(code) -> ParsedCourse | None:
    for course in courses:
        if course.code == code:
            return course


def get_level(completed_courses: List[str]) -> Level:
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


# Get shortest subrequirement tree for each required program course
def extract_course_codes(req: Requirement) -> Set[str]:
    """
    Recursively collect all course codes from Course leaves anywhere in the tree.
    """
    codes = set()
    if isinstance(req, Course):
        codes.add(req.course)
    # All composite types (And, Or, CreditsFrom, ChooseN) have a 'requirements' list
    if hasattr(req, "requirements") and isinstance(req.requirements, list):
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


def main(config: Config):
    bricks = {
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
    # Get requirements for program and then mark off all the credit hours they already satisfy
    semesters = {}

    # We want to end up with all the required courses ordered by requirements
    # Reduce into list of required courses and remaining choice course coursework
    def get_required_courses(
        requirements: List[Requirement],
    ) -> Tuple[List[Course], List[Requirement]]:
        required_courses = []
        remaining_coursework = []
        for requirement in requirements:
            match requirement.type:
                case RequirementType.COURSE:
                    required_courses.append(requirement)
                case RequirementType.AND:
                    req_courses, rem_courses = get_required_courses(
                        requirement.requirements
                    )
                    required_courses.extend(req_courses)
                    remaining_coursework.extend(rem_courses)
                case (
                    RequirementType.OR
                    | RequirementType.CHOOSE_N
                    | RequirementType.CREDITS_FROM
                ):
                    remaining_coursework.append(requirement)
                case (
                    RequirementType.NONE
                    | RequirementType.PERMISSION
                    | RequirementType.LEVEL
                    | RequirementType.PLACEMENT
                    | RequirementType.GPA
                    | RequirementType.OTHER
                ):
                    pass
                case t:
                    raise ValueError(f"Unknown RequirementType {t}")
        return required_courses, remaining_coursework

    required_courses, remaining_coursework = get_required_courses(
        config.program.requisite
    )
    print("Required courses:", [course.course for course in required_courses])

    def simplify_requirement(
        req: Requirement,
        current_gpa: float,
        placements: List[Placement],
        completed_courses: List[str],  # list of course codes that have been completed
        level: Level,  # one of "freshman", "sophomore", "junior", "senior"
    ) -> Requirement:
        """
        Return a simplified requirement tree where:
        - Satisfied leaves become NONE.
        - AND/OR nodes are reduced (remove satisfied children, propagate satisfaction).
        - CREDITS_FROM/CHOOSE_N are only adjusted for completed courses; their children are NOT simplified.
        - PERMISSION is always left unsatisfied (with a comment).
        - OTHER is always treated as satisfied (becomes NONE).
        """

        def resolve_and(requirements: List[Requirement]) -> List[Requirement]:
            simplified_children: List[Requirement] = []
            for child in requirements:
                simp = simplify_requirement(
                    child, current_gpa, placements, completed_courses, level
                )
                if simp.type != RequirementType.NONE:
                    simplified_children.append(simp)
            return simplified_children

        def resolve_or(requirements: List[Requirement]) -> List[Requirement]:
            simplified_children: List[Requirement] = []
            for child in requirements:
                simp = simplify_requirement(
                    child, current_gpa, placements, completed_courses, level
                )
                # One satisfied child makes the whole OR satisfied
                if simp.type == RequirementType.NONE:
                    return []  # One satisfied requirement satisfies the whole condition
                simplified_children.append(simp)
            return simplified_children

        # ---------- Leaf types ----------
        if req.type == RequirementType.NONE:
            return req

        if req.type == RequirementType.COURSE:
            if req.course in completed_courses:
                return Empty()
            course = get_course(req.course)
            if not course:
                logger.warn(f"Ingoring non-existant requireed course {req.course}")
                return Empty()
            return req

        if req.type == RequirementType.GPA:
            if current_gpa >= req.gpa:
                return Empty(type=RequirementType.NONE)
            return req

        if req.type == RequirementType.PLACEMENT:
            # Note: exact match only – real‑world placement might be more complex
            for p in placements:
                if p.subject == req.subject and p >= req:
                    return Empty(type=RequirementType.NONE)
            return req

        if req.type == RequirementType.LEVEL:
            if level >= req:
                return Empty(type=RequirementType.NONE)
            return req

        if req.type == RequirementType.PERMISSION:
            # NOTE: Permission is always considered unsatisfied by default.
            # In a real system, you might check external data.
            return req

        if req.type == RequirementType.OTHER:
            # NOTE: "OTHER" is assumed to be satisfied.
            return Empty(type=RequirementType.NONE)

        # ---------- Composite logical nodes (full recursion) ----------
        if req.type == RequirementType.AND:
            simplified_children = resolve_and(req.requirements)
            # Simplify if all children are satisfied
            if not simplified_children:
                return Empty(type=RequirementType.NONE)
            return And(requirements=simplified_children)

        if req.type == RequirementType.OR:
            simplified_children = resolve_or(req.requirements)
            if not simplified_children:
                return Empty(type=RequirementType.NONE)
            return Or(requirements=simplified_children)

        # ---------- CREDITS_FROM and CHOOSE_N (no child simplification, only adjust thresholds) ----------
        if req.type == RequirementType.CREDITS_FROM:
            # Collect all course codes anywhere under this node
            codes = extract_course_codes(req)
            total_credits = 0.0
            for code in codes:
                if code in completed_courses:
                    course_info = get_course(code)
                    if course_info:
                        total_credits += course_info.min_credits
                    else:
                        logger.warn(
                            f"Course {code} not found in course catalog; assuming 0 credits."
                        )
            if total_credits >= req.credits_required:
                return Empty(type=RequirementType.NONE)
            # Return a new CreditsFrom with reduced requirement, keeping the original child list unchanged.
            return CreditsFrom(
                credits_required=req.credits_required - total_credits,
                requirements=req.requirements,  # note: children are NOT simplified
            )

        if req.type == RequirementType.CHOOSE_N:
            codes = extract_course_codes(req)
            # Count distinct completed courses among the codes
            completed_in_subtree = {code for code in codes if code in completed_courses}
            count = len(completed_in_subtree)
            if count >= req.choose:
                return Empty(type=RequirementType.NONE)
            return ChooseN(
                choose=req.choose - count,
                requirements=req.requirements,  # children unchanged
            )

        # Fallback (should never reach here if all types are covered)
        logger.error("Fallback triggered. Requirement type is uncovered.")
        return req

    def schedule_courses(
        all_required: Set[str],
        config: Config,
    ) -> List[List[str]]:
        """
        Sorts required courses into semesters using raw prerequisite trees
        (no simplification, no placements, no completed courses).
        """

        # --- Step 0: Remove already completed courses from the set to schedule ---
        completed_set = set(config.completed_course_work)
        all_required = all_required - completed_set
        logger.debug(f"All required after removing completed: {sorted(all_required)}")

        # --- Step 1: Build dependency graph by scanning raw prerequisite trees ---
        prereq_map: Dict[str, Set[str]] = {}
        reverse_map: Dict[str, Set[str]] = {}

        for course in sorted(all_required):
            course_obj = get_course(course)
            if not course_obj:
                logger.error(f"Course {course} not found in DB - skipping")
                continue

            # Get all course codes mentioned in the prerequisite tree (raw, unsimplified)
            # course_obj.requisite is typically a list of requirement nodes
            all_prereq_codes = collect_all_course_codes(course_obj.requisite)

            # Keep only those that are also in all_required (and not already completed)
            prereq_set = {c for c in all_prereq_codes if c in all_required}
            prereq_map[course] = prereq_set

            logger.debug(
                f"Course {course} - raw prerequisites (from all_required): {sorted(prereq_set)}"
            )

            for prereq in prereq_set:
                reverse_map.setdefault(prereq, set()).add(course)

        # --- Step 2: Kahn's algorithm with grouping by semester ---
        in_degree = {course: len(prereq_map[course]) for course in all_required}
        logger.debug(f"Initial in‑degrees: {in_degree}")

        queue = deque([c for c in all_required if in_degree[c] == 0])
        logger.debug(f"Initial queue (semester 1 candidates): {sorted(queue)}")

        semesters = []
        semester_num = 1
        while queue:
            current_semester = list(queue)
            semesters.append(current_semester)
            logger.debug(f"Semester {semester_num}: {sorted(current_semester)}")
            queue.clear()

            for course in current_semester:
                for dependent in reverse_map.get(course, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
            semester_num += 1

        # --- Step 3: Check for cycles ---
        assigned = sum(len(sem) for sem in semesters)
        if assigned != len(all_required):
            remaining = [c for c in all_required if in_degree.get(c, 0) > 0]
            raise ValueError(f"Cycle detected among courses: {remaining}")

        return semesters

    initial_courses = [
        course.course for course in required_courses
    ]  # e.g., ['ET 1500', 'CS 2400', ...]

    all_required = set(initial_courses)
    processed = set()
    new_courses = all_required.copy()  # courses to process in the first iteration

    iteration = 1
    while new_courses:
        print(f"\n--- Iteration {iteration} ---")
        print(f"Processing {len(new_courses)} courses: {sorted(new_courses)}")

        newly_discovered = set()

        for course_code in new_courses:
            if course_code in processed:
                continue
            processed.add(course_code)

            parsed_course = get_course(course_code)
            if not parsed_course:
                # Warn and skip (as in your original code)
                logger.warn(f"Ignoring non-existent required course {course_code}")
                continue

            # Simplify the course's prerequisite tree
            simplified_tree = simplify_requirement(
                req=And(requirements=parsed_course.requisite),
                current_gpa=config.gpa,
                placements=config.placements,
                completed_courses=config.completed_course_work,
                level=config.level,
            )

            # Extract all course codes that still appear in the simplified tree
            codes = extract_course_codes(simplified_tree)
            newly_discovered.update(codes)

        # New courses are those we haven't seen before (in all_required)
        new_courses = newly_discovered - all_required
        all_required.update(newly_discovered)

        if new_courses:
            print(
                f"Found {len(new_courses)} new prerequisite courses: {sorted(new_courses)}"
            )
        else:
            print("No new prerequisites found.")

        iteration += 1

    print("\n=== Final set of all required courses ===")
    print(sorted(all_required.difference(initial_courses)))

    # Schedule the courses into semesters
    semesters = schedule_courses(
        all_required,
        config,
    )

    print("\n=== Proposed semester schedule ===")
    for i, semester in enumerate(semesters, 1):
        print(f"Semester {i}: {sorted(semester)}")

    # print("\nSimplified course requirement tree:\n")
    # print(json.dumps(simplified_tree.model_dump(mode="json"), indent=2))

    # Simplify requirement tree of remaining coursework by removing-
    # courses already satisified by subrequirement courses

    # Required courses are courses you will absolutely take
    # Mark off bricks satisfied by these required courses
    for code in all_required:
        db_course = get_course(code)
        if not db_course:
            logger.error(f"Required course {code} not found in DB")
            return
        satisfied_bricks = db_course.bricks
        brick_regex = r"\(([A-Z]+)\)"

        for brick in satisfied_bricks:
            match = re.search(brick_regex, brick)
            if not match:
                logger.error("Brick could not be matched to a category")
                continue

            category = match.group(1)
            bricks[category]["current"] += db_course.min_credits

    print("\n=== Bricks ===")
    for key in bricks.keys():
        brick = bricks[key]
        if brick["current"] < brick["required"]:
            print(f"{key} - {brick}")
        else:
            print(f"{key} - SATISFIED ({brick['current']} / {brick['required']})")


if __name__ == "__main__":
    program_path, credits_per_semester = parse_args(sys.argv[1:])
    program_data = load_json(program_path)
    program_requirements: List[Requirement] = parse_requirements(
        program_data["requisite"][
            "requirements"
        ]  # TODO: Jank solution because 'requisite' is not an array but an object
    )
    completed_courses = []
    config = Config(
        program=Program(
            catalog_name=program_data["catalog_name"],
            catalog_year=program_data["catalog_year"],
            catalog_archived=program_data["catalog_archived"],
            program_type=program_data["program_type"],
            program_name=program_data["program_name"],
            program_link=program_data["program_link"],
            credits=program_data["credits"],
            code=program_data["code"],
            requisite=program_requirements,
        ),
        completed_course_work=completed_courses,
        placements=[
            Placement(subject="Math", level="2"),
            Placement(subject="Computer Science", level="3"),
        ],
        gpa=4.0,
        level=get_level(completed_courses),
        credits_per_semester=credits_per_semester,
    )
    courses_raw = load_json("data/courses/courses.parsed.json")
    for course in courses_raw:
        course_requirements = parse_requirements([course["requisite"]])
        courses.append(
            ParsedCourse(
                name=course["name"],
                code=course["code"],
                requisite_string=course["requisite_string"],
                requisite=course_requirements,
                component=course["component"],
                bricks=course["bricks"],
                min_credits=course["min_credits"],
                max_credits=course["max_credits"],
                pattern=course["pattern"],
            )
        )
    main(config)
