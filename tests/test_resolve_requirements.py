import pytest

from create_schedule import RequirementNode, resolve_requirements


def test_resolve_single_course(sample_course_by_code):
    course_code = list(sample_course_by_code.keys())[0]
    req = RequirementNode("COURSE", code=course_code, timing="COMPLETED")
    courses, constraints = resolve_requirements(req, sample_course_by_code)
    assert courses == [course_code]
    assert constraints == {}


def test_resolve_and_requirements(sample_course_by_code):
    course_codes = list(sample_course_by_code.keys())[:2]
    if len(course_codes) < 2:
        pytest.skip("Need at least 2 courses in database")
    req1 = RequirementNode("COURSE", code=course_codes[0], timing="COMPLETED")
    req2 = RequirementNode("COURSE", code=course_codes[1], timing="COMPLETED")
    parent = RequirementNode("AND", requirements=[req1, req2])

    courses, constraints = resolve_requirements(parent, sample_course_by_code)
    assert set(courses) == {course_codes[0], course_codes[1]}


def test_resolve_or_requirements_chooses_first(sample_course_by_code):
    course_codes = list(sample_course_by_code.keys())[:2]
    if len(course_codes) < 2:
        pytest.skip("Need at least 2 courses in database")
    req1 = RequirementNode("COURSE", code=course_codes[0], timing="COMPLETED")
    req2 = RequirementNode("COURSE", code=course_codes[1], timing="COMPLETED")
    parent = RequirementNode("OR", requirements=[req1, req2])

    courses, constraints = resolve_requirements(parent, sample_course_by_code)
    assert courses == [course_codes[0]]


def test_resolve_missing_course_logs_error(sample_course_by_code):
    req = RequirementNode("COURSE", code="NONEXISTENT", timing="COMPLETED")
    courses, constraints = resolve_requirements(req, sample_course_by_code)
    assert courses == []


def test_resolve_credits_from_greedy(sample_course_by_code):
    course_codes = list(sample_course_by_code.keys())[:2]
    if len(course_codes) < 2:
        pytest.skip("Need at least 2 courses in database")
    req1 = RequirementNode("COURSE", code=course_codes[0], timing="COMPLETED")
    req2 = RequirementNode("COURSE", code=course_codes[1], timing="COMPLETED")

    parent = RequirementNode(
        "CREDITS_FROM", credits_required=6, requirements=[req1, req2]
    )

    courses, constraints = resolve_requirements(parent, sample_course_by_code)
    assert len(courses) > 0
    assert all(course in course_codes for course in courses)


def test_resolve_choose_n_greedy(sample_course_by_code):
    course_codes = list(sample_course_by_code.keys())[:3]
    if len(course_codes) < 3:
        pytest.skip("Need at least 3 courses in database")
    reqs = [
        RequirementNode("COURSE", code=course_codes[0], timing="COMPLETED"),
        RequirementNode("COURSE", code=course_codes[1], timing="COMPLETED"),
        RequirementNode("COURSE", code=course_codes[2], timing="COMPLETED"),
    ]

    parent = RequirementNode("CHOOSE_N", choose_n=2, requirements=reqs)
    courses, constraints = resolve_requirements(parent, sample_course_by_code)

    assert len(courses) == 2
    assert courses[0] in course_codes
    assert courses[1] in course_codes
