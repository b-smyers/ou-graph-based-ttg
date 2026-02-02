import pytest

from create_schedule import CourseGraph, generate_semesters


def test_generate_semesters_simple(sample_course_by_code):
    required = list(sample_course_by_code.keys())[:2]
    if len(required) < 2:
        pytest.skip("Need at least 2 courses in database")
    graph = CourseGraph()

    semesters = generate_semesters(required, graph, sample_course_by_code, 15)

    assert len(semesters) > 0
    scheduled = set()
    for sem_name, courses in semesters:
        scheduled.update(courses)
    assert set(c.upper() for c in required) == scheduled


def test_generate_semesters_respects_credits_limit(sample_course_by_code):
    required = list(sample_course_by_code.keys())[:4]
    if len(required) < 4:
        pytest.skip("Need at least 4 courses in database")
    graph = CourseGraph()
    credits_per_sem = 6

    semesters = generate_semesters(
        required, graph, sample_course_by_code, credits_per_sem
    )

    for sem_name, courses in semesters:
        total_credits = sum(
            sample_course_by_code[c.upper()].get("min_credits", 0) for c in courses
        )
        assert total_credits <= credits_per_sem
