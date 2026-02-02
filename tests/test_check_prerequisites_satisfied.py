from create_schedule import CourseGraph, check_prerequisites_satisfied


def test_check_prerequisites_satisfied_all_met():
    graph = CourseGraph()
    graph.add_requires("CS102", "CS101")

    satisfied, msg = check_prerequisites_satisfied("CS102", graph, {"CS101"}, 0, {})
    assert satisfied is True
    assert msg is None


def test_check_prerequisites_not_satisfied():
    graph = CourseGraph()
    graph.add_requires("CS102", "CS101")

    satisfied, msg = check_prerequisites_satisfied("CS102", graph, set(), 0, {})
    assert satisfied is False
    assert "CS101" in msg
