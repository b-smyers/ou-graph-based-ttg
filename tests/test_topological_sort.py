from create_schedule import CourseGraph, topological_sort


def test_topological_sort_linear_chain():
    graph = CourseGraph()
    graph.add_requires("CS102", "CS101")
    graph.add_requires("CS201", "CS102")

    sorted_courses, has_cycle = topological_sort(graph, ["CS101", "CS102", "CS201"])

    assert not has_cycle
    idx_101 = sorted_courses.index("CS101")
    idx_102 = sorted_courses.index("CS102")
    idx_201 = sorted_courses.index("CS201")

    assert idx_101 < idx_102 < idx_201


def test_topological_sort_cycle_detection():
    graph = CourseGraph()
    graph.add_requires("CS101", "CS102")
    graph.add_requires("CS102", "CS101")

    sorted_courses, has_cycle = topological_sort(graph, ["CS101", "CS102"])

    assert has_cycle
    assert sorted_courses == []


def test_topological_sort_independent_courses():
    graph = CourseGraph()
    graph.add_course("CS101")
    graph.add_course("CS102")
    graph.add_course("MATH101")

    sorted_courses, has_cycle = topological_sort(graph, ["CS101", "CS102", "MATH101"])

    assert not has_cycle
    assert len(sorted_courses) == 3
