"""
requirement_simplifier.py

Handles simplification of requirement trees based on student context (completed courses,
placements, GPA, academic level).
"""

from typing import List
from scheduling_types import (
    Requirement,
    RequirementType,
    Empty,
    Or,
    And,
    CreditsFrom,
    ChooseN,
    Config,
)
from logger import logger
from data_loader import get_course
from utils import extract_course_codes


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
            logger.warn(f"Ignoring non-existent required course {req.course}")
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
