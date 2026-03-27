from __future__ import annotations
import math
from ortools.sat.python import cp_model
import json
import re
import sys
import os
from typing import (
    Dict,
    List,
    Set,
    Tuple,
)
from scheduling_types import (
    Requirement,
    RequirementType,
    OfferingPattern,
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
    Program,
    Config,
    ParsedCourse,
)
from logger import logger


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


def pattern_allows(pattern: OfferingPattern, is_spring: bool, year: int):
    """Return True if a course with `pattern` may be scheduled in the term.

    - `is_spring`: True for spring semesters, False for fall semesters
    - `year`: integer year (e.g., 2025)
    """
    if not pattern:
        return True

    p = pattern.lower()
    # summer terms are not supported by the scheduler; treat summer-only as disallowed
    if p == OfferingPattern.SUMMER:
        return False
    if p == OfferingPattern.FALL_AND_SPRING:
        return True
    if p == OfferingPattern.FALL:
        return not is_spring
    if p == OfferingPattern.SPRING:
        return is_spring
    if p == OfferingPattern.FALL_EVEN:
        return (not is_spring) and (year % 2 == 0)
    if p == OfferingPattern.FALL_ODD:
        return (not is_spring) and (year % 2 == 1)
    if p == OfferingPattern.SPRING_EVEN:
        return is_spring and (year % 2 == 0)
    if p == OfferingPattern.SPRING_ODD:
        return is_spring and (year % 2 == 1)
    if p == OfferingPattern.SUMMER_EVEN:
        return False
    if p == OfferingPattern.SUMMER_ODD:
        return False
    if p == OfferingPattern.IRREGULAR:
        # allowed any time, but caller may choose to warn
        return True
    if p == OfferingPattern.ARRANGED:
        return True
    if p == OfferingPattern.DEACTIVATED:
        return False

    # Unknown patterns default to allowed
    return True


courses: List[ParsedCourse] = []


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


def schedule_remaining_with_ortools(
    fixed_semesters: List[List[ParsedCourse]],
    remaining_requirements: List[Requirement],
    config: Config,
    max_additional_semesters: int = 8,
) -> List[List[ParsedCourse]]:
    """
    Use OR-Tools CP-SAT to assign remaining courses to semesters.
    Returns a merged schedule (fixed + chosen remaining courses).
    """
    CREDIT_SCALE = 10  # factor to convert float credits to integers

    # --- 1. Collect all candidate courses from remaining requirements ---
    candidate_codes = set()
    for req in remaining_requirements:
        candidate_codes.update(extract_course_codes(req))

    # Remove any courses already in fixed schedule
    fixed_codes = {c.code for sem in fixed_semesters for c in sem}
    candidate_codes -= fixed_codes

    # Build mapping from code to ParsedCourse and pre‑compute scaled credits
    candidate_courses = {}
    scaled_credits = {}  # code -> integer (credits * CREDIT_SCALE)
    for code in candidate_codes:
        course = get_course(code)
        if course is None:
            logger.warn(f"Candidate course {code} not found in DB; skipping")
        else:
            candidate_courses[code] = course
            scaled_credits[code] = int(course.min_credits * CREDIT_SCALE + 0.5)

    if not candidate_courses:
        logger.info("No remaining courses to schedule.")
        return fixed_semesters

    # --- 2. Fixed schedule data ---
    num_fixed_semesters = len(fixed_semesters)
    fixed_credits = [0.0] * num_fixed_semesters
    fixed_semester_index = {}  # code -> semester index (0-based)
    for i, sem in enumerate(fixed_semesters):
        for course in sem:
            fixed_semester_index[course.code] = i
            fixed_credits[i] += course.min_credits

    # --- NEW: Adjust credit limit if fixed semesters already exceed it ---
    max_fixed_credits = max(fixed_credits) if fixed_credits else 0
    effective_limit = config.credits_per_semester - 3
    if max_fixed_credits > config.credits_per_semester:
        logger.warn(
            f"Fixed schedule has a semester with {max_fixed_credits} credits, "
            f"which exceeds the desired limit of {config.credits_per_semester}. "
            f"Temporarily raising the limit to {max_fixed_credits} to allow scheduling. "
            "The final schedule will exceed the desired credit load in that semester."
        )
        effective_limit = math.ceil(max_fixed_credits)
    logger.info(f"Using credit limit of {effective_limit} credits per semester.")

    # --- 3. Determine earliest possible semester for each candidate course ---
    # based on fixed prerequisites
    earliest_semester = {}
    for code, course in candidate_courses.items():
        # Collect all prerequisite course codes from original (unsimplified) tree
        prereq_codes = collect_all_course_codes(course.requisite)
        # Only consider those that are in the fixed schedule
        fixed_prereq_sems = [
            fixed_semester_index[p] for p in prereq_codes if p in fixed_semester_index
        ]
        if fixed_prereq_sems:
            earliest = max(fixed_prereq_sems) + 1
        else:
            earliest = 0
        earliest_semester[code] = earliest

    # --- 4. Planning horizon ---
    horizon = num_fixed_semesters + max_additional_semesters

    # --- 5. Create CP model ---
    model = cp_model.CpModel()

    # Variables: x[code][s] for s in [earliest..horizon-1]
    x = {}
    for code in candidate_courses:
        earliest = earliest_semester[code]
        for s in range(earliest, horizon):
            x[code, s] = model.NewBoolVar(f"x_{code}_s{s}")  # type: ignore

    # --- 6. Constraints ---

    # Each course at most once
    for code in candidate_courses:
        vars_for_code = [
            x[code, s]
            for s in range(earliest_semester[code], horizon)
            if (code, s) in x
        ]
        if vars_for_code:
            model.Add(sum(vars_for_code) <= 1)  # type: ignore

    # Credit limit per semester (using scaled integers) with effective_limit
    target_credits_scaled = effective_limit * CREDIT_SCALE
    for s in range(horizon):
        # fixed credits for this semester (scaled)
        fixed_scaled = (
            int(fixed_credits[s] * CREDIT_SCALE + 0.5) if s < num_fixed_semesters else 0
        )
        credit_vars = []
        for code in candidate_courses:
            if (code, s) in x:
                credit_vars.append(scaled_credits[code] * x[code, s])
        if credit_vars:
            model.Add(sum(credit_vars) + fixed_scaled <= target_credits_scaled)  # type: ignore

    # Prerequisite constraints among candidate courses
    for code_c, course_c in candidate_courses.items():
        prereq_codes = collect_all_course_codes(course_c.requisite)
        for code_p in prereq_codes:
            if code_p not in candidate_courses:
                continue
            # For each semester s where c might be taken, ensure p is taken in some t < s
            for s in range(earliest_semester[code_c], horizon):
                if (code_c, s) not in x:
                    continue
                p_possible = [
                    x[code_p, t]
                    for t in range(earliest_semester[code_p], s)
                    if (code_p, t) in x
                ]
                if p_possible:
                    # If c is taken at s, then at least one of p_possible must be true
                    model.AddBoolOr(p_possible + [x[code_c, s].Not()])  # type: ignore

    # Offering pattern constraints
    for s in range(horizon):
        year_offset = s // 2
        year = config.start_year + year_offset
        is_spring = (config.start_term == "spring") if s % 2 == 0 else (s % 2 == 1)
        for code in candidate_courses:
            if (code, s) in x:
                course = candidate_courses[code]
                if not pattern_allows(course.pattern, is_spring, year):
                    model.Add(x[code, s] == 0)  # type: ignore

    # Requirement satisfaction constraints
    def collect_leaf_courses(req):
        """Return set of course codes from all Course leaves under req."""
        return extract_course_codes(req)

    for req in remaining_requirements:
        eligible_codes = collect_leaf_courses(req)
        eligible_codes = {c for c in eligible_codes if c in candidate_courses}
        if not eligible_codes:
            logger.error(f"Requirement {req.type} has no eligible courses left.")
            continue

        # Build list of variables for eligible courses across all semesters
        eligible_vars = []
        for code in eligible_codes:
            for s in range(earliest_semester[code], horizon):
                if (code, s) in x:
                    eligible_vars.append(x[code, s])

        if req.type == RequirementType.COURSE:
            model.Add(sum(eligible_vars) >= 1)  # type: ignore

        elif req.type == RequirementType.CHOOSE_N:
            model.Add(sum(eligible_vars) >= req.choose)  # type: ignore

        elif req.type == RequirementType.CREDITS_FROM:
            credit_sum = []
            for code in eligible_codes:
                for s in range(earliest_semester[code], horizon):
                    if (code, s) in x:
                        credit_sum.append(scaled_credits[code] * x[code, s])
            required_scaled = int(req.credits_required * CREDIT_SCALE + 0.5)
            model.Add(sum(credit_sum) >= required_scaled)  # type: ignore

        elif req.type == RequirementType.OR:
            # Treat as CHOOSE_1 over all leaf courses under the OR
            model.Add(sum(eligible_vars) >= 1)  # type: ignore

        elif req.type == RequirementType.AND:
            for code in eligible_codes:
                vars_for_code = [
                    x[code, s]
                    for s in range(earliest_semester[code], horizon)
                    if (code, s) in x
                ]
                model.Add(sum(vars_for_code) >= 1)  # type: ignore

        else:
            logger.warn(f"Unexpected requirement type in remaining: {req.type}")

    # --- 7. Objective: minimize the last semester used ---
    last_semester = model.NewIntVar(0, horizon - 1, "last_semester")  # type: ignore
    taken_flags = []
    for s in range(horizon):
        for code in candidate_courses:
            if (code, s) in x:
                taken_flags.append(s * x[code, s])
    if taken_flags:
        model.AddMaxEquality(last_semester, taken_flags)  # type: ignore
    model.Minimize(last_semester)  # type: ignore

    # --- 8. Solve ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # Build resulting schedule
        result_semesters = [[] for _ in range(horizon)]
        # Add fixed courses
        for s, sem_courses in enumerate(fixed_semesters):
            result_semesters[s].extend(sem_courses)
        # Add chosen courses
        for code in candidate_courses:
            for s in range(earliest_semester[code], horizon):
                if (code, s) in x and solver.Value(x[code, s]):
                    result_semesters[s].append(candidate_courses[code])
        # Filter out empty semesters at the end
        while result_semesters and not result_semesters[-1]:
            result_semesters.pop()
        return result_semesters
    else:
        logger.error("No feasible schedule found for remaining courses.")
        return fixed_semesters


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
    # Get bricks that satisfy each requirement
    bricks_courses = {
        "FWS": [],
        "FAW": [],
        "FQR": [],
        "FIE": [],
        "PHTC": [],
        "PHA": [],
        "PNS": [],
        "PSBS": [],
        "ACSW": [],
        "ANW": [],
        "ACNW": [],
        "BSL": [],
        "BER": [],
        "BDP": [],
        "BLD": [],
        "CAP": [],
    }
    for course in courses:
        for brick_str in course.bricks:
            match = re.search(r"\(([A-Z]+)\)", brick_str)
            if not match:
                logger.error(
                    f"Brick string could not be matched to a category: {brick_str}"
                )
                continue
            category = match.group(1)
            if category in bricks_courses:
                bricks_courses[category].append(course)
            else:
                logger.warn(
                    f"Unknown brick category '{category}' from course {course.code}"
                )

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
        config: Config,
        completed_courses: List[str],  # list of course codes that have been completed
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
                simp = simplify_requirement(child, config, completed_courses)
                if simp.type != RequirementType.NONE:
                    simplified_children.append(simp)
            return simplified_children

        def resolve_or(requirements: List[Requirement]) -> List[Requirement]:
            simplified_children: List[Requirement] = []
            for child in requirements:
                simp = simplify_requirement(child, config, completed_courses)
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
            if config.gpa >= req.gpa:
                return Empty(type=RequirementType.NONE)
            return req

        if req.type == RequirementType.PLACEMENT:
            # Note: exact match only – real‑world placement might be more complex
            for p in config.placements:
                if p.subject == req.subject and p >= req:
                    return Empty(type=RequirementType.NONE)
            return req

        if req.type == RequirementType.LEVEL:
            if config.level >= req:
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
    ) -> List[List[ParsedCourse]]:
        """
        Sorts required courses into semesters using raw prerequisite trees,
        course offering patterns, and credit limits.
        Returns a list of lists, where each sublist corresponds to a semester
        in chronological order.
        """

        # --- Step 0: Remove already completed courses ---
        completed_set = set(config.completed_course_work)
        all_required = all_required - completed_set

        # --- Step 1: Build dependency graph (raw prerequisites) ---
        prereq_map: Dict[str, Set[str]] = {}
        reverse_map: Dict[str, Set[str]] = {}

        for course in sorted(all_required):
            course_obj = get_course(course)
            if not course_obj:
                logger.error(f"Course {course} not found in DB - skipping")
                continue

            all_prereq_codes = collect_all_course_codes(course_obj.requisite)
            prereq_set = {c for c in all_prereq_codes if c in all_required}
            prereq_map[course] = prereq_set

            for prereq in prereq_set:
                reverse_map.setdefault(prereq, set()).add(course)

        # --- Step 2: Initialize in-degree, available set, and out-degree (for priority) ---
        in_degree = {course: len(prereq_map[course]) for course in all_required}
        available = {c for c in all_required if in_degree[c] == 0}
        remaining = set(all_required)
        semesters = []  # will hold lists of courses per semester

        # Precompute out-degree (number of courses that depend on each course)
        out_degree = {
            course: len(reverse_map.get(course, set())) for course in all_required
        }

        # --- Step 3: Simulate semesters with credit limit ---
        year = config.start_year
        is_spring = config.start_term == "spring"
        credit_limit = (
            config.credits_per_semester - 3
        )  # -3 so we dont overload with program courses first (balance with bricks)

        while remaining:
            # Determine which available courses are offered this semester
            offered_now = []
            for course in available:
                course_obj = get_course(course)
                if course_obj and pattern_allows(course_obj.pattern, is_spring, year):
                    offered_now.append(course)

            if not offered_now:
                # No courses offered – just advance time
                logger.debug(
                    f"Semester {year} {'Spring' if is_spring else 'Fall'}: no courses offered"
                )
            else:
                # Greedy selection: pick courses with highest out-degree first,
                # then smallest credits to fit more.
                # Build list of (course, credits, out_degree)
                candidates = []
                for course in offered_now:
                    course_obj = get_course(course)
                    if course_obj:
                        credits = course_obj.min_credits
                        candidates.append((course, credits, out_degree.get(course, 0)))

                # Sort: higher out-degree first, then lower credits (to pack more)
                candidates.sort(key=lambda x: (-x[2], x[1]))

                selected = []
                remaining_credits = credit_limit
                for course, credits, _ in candidates:
                    if credits <= remaining_credits:
                        selected.append(course)
                        remaining_credits -= credits
                    else:
                        # This course alone exceeds remaining capacity; skip it for now.
                        # It will remain in available for future semesters.
                        pass

                if not selected:
                    # No course could fit – this indicates a single course exceeds the limit.
                    # Raise an error because it's impossible to schedule under this limit.
                    max_credit_course = max(candidates, key=lambda x: x[1])
                    raise RuntimeError(
                        f"Course {max_credit_course[0]} requires {max_credit_course[1]} credits, "
                        f"which exceeds the per‑semester limit of {credit_limit}. "
                        "Cannot schedule required courses."
                    )

                # Schedule the selected courses this semester
                semesters.append(selected)

                # Remove them from available and remaining, update dependents
                for course in selected:
                    available.remove(course)
                    remaining.remove(course)

                    for dependent in reverse_map.get(course, []):
                        in_degree[dependent] -= 1
                        if in_degree[dependent] == 0:
                            available.add(dependent)

            # Safety check: if available is empty but courses remain, something is wrong
            if not available and remaining:
                raise RuntimeError(
                    f"No courses available to take, but {len(remaining)} courses remain unscheduled. "
                    "Possible cycle or missing prerequisite."
                )

            # Advance to next semester
            if is_spring:
                is_spring = False
                # year stays same (Fall of same calendar year)
            else:
                is_spring = True
                year += 1

        # --- Step 4: Convert course codes to course objects for final output ---
        final_semesters = []
        for sem in semesters:
            sem_courses = []
            for code in sem:
                course_obj = get_course(code)
                if course_obj:
                    sem_courses.append(course_obj)
                else:
                    logger.error(f"Course {code} not found in DB during final assembly")
            final_semesters.append(sem_courses)

        return final_semesters

    # Simplify requirement tree of remaining coursework by removing-
    # courses already satisified by subrequirement courses

    # Required courses are courses you will absolutely take
    initial_courses = [
        course.course for course in required_courses
    ]  # e.g., ['ET 1500', 'CS 2400', ...]

    all_required = set(initial_courses)
    processed = set()
    new_courses = all_required.copy()  # courses to process in the first iteration

    while new_courses:
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
                config=config,
                completed_courses=config.completed_course_work,
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

    print("\n=== Final set of all required courses ===")
    print(sorted(all_required.difference(initial_courses)))

    # Schedule the required courses into semesters
    semesters = schedule_courses(
        all_required,
        config,
    )

    # Simplify the remaining coursework by marking off courses that are now satisfied by the scheduled required courses.
    all_completed = list(set(config.completed_course_work) | all_required)
    simplified_remaining = []
    for req in remaining_coursework:
        simplified = simplify_requirement(
            req,
            config,
            all_completed,
        )
        if simplified.type != RequirementType.NONE:
            simplified_remaining.append(simplified)

    print("\n=== Base semester schedule ===")
    for i, semester in enumerate(semesters, 1):
        print(f"Semester {i}: {[course.code for course in semester]}")

        start_year = config.start_year + (i - 1) // 2
        is_spring = (config.start_term == "spring") if i == 1 else (i % 2 == 0)
        for course in semester:
            course_obj = get_course(course)
            if course_obj and not pattern_allows(
                course_obj.pattern, is_spring, start_year
            ):
                logger.error(
                    f"Course {course} cannot be taken in Semester {i} ({'Spring' if is_spring else 'Fall'} {start_year}) due to offering pattern {course_obj.pattern}"
                )

    # Schedule remaining coursework using OR-Tools
    final_schedule = schedule_remaining_with_ortools(
        fixed_semesters=semesters,
        remaining_requirements=simplified_remaining,
        config=config,
        max_additional_semesters=8,
    )

    # Gather remaining required brick types
    remaining_brick_types = []
    for key, brick in bricks.items():
        if brick["current"] < brick["required"]:
            remaining_brick_types.append(key)

    # TODO: Filter bricks_courses list for courses that could possibly be taken to fufill remaining brick requirements

    print("\n=== Final schedule ===")
    for i, semester in enumerate(final_schedule, 1):
        print(
            f"Semester {i}: {[c.code for c in semester]} (total credits: {sum(c.min_credits for c in semester)})"
        )
        # Optionally validate offering patterns again
        start_year = config.start_year + (i - 1) // 2
        is_spring = (config.start_term == "spring") if i == 1 else (i % 2 == 0)
        for course in semester:
            if not pattern_allows(course.pattern, is_spring, start_year):
                logger.error(
                    f"Course {course.code} cannot be taken in Semester {i} ({'Spring' if is_spring else 'Fall'} {start_year}) due to offering pattern {course.pattern}"
                )

    # Mark off bricks satisfied by these required courses
    # Iterate through every course in the final schedule and add its credits to the bricks it satisfies
    total_credits = 0
    for semester in final_schedule:
        for course in semester:
            total_credits += course.min_credits
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

    # Add up previously completed courses
    for code in config.completed_course_work:
        course = get_course(code)
        if course:
            total_credits += course.min_credits

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

    print("\n=== Total Credits Taken ===")
    print(f"Total Semester Credits: {total_credits}")


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
            program_link=program_data["link"],
            credits=120,
            requisite=program_requirements,
        ),
        completed_course_work=completed_courses,
        placements=[
            Placement(subject="Math", level="3"),
            Placement(subject="Computer Science", level="3"),
        ],
        gpa=4.0,
        level=get_level(completed_courses),
        credits_per_semester=credits_per_semester,
        start_year=2026,
        start_term="fall",
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
                pattern=OfferingPattern(course["pattern"]),
            )
        )
    main(config)
