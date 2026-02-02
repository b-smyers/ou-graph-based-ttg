from create_schedule import CourseGraph


def test_add_course():
    graph = CourseGraph()
    graph.add_course("CS101")
    assert "CS101" in graph.graph


def test_add_requires():
    graph = CourseGraph()
    graph.add_requires("CS102", "CS101")

    assert "CS102" in graph.graph
    assert "CS101" in graph.graph
    assert "CS101" in graph.get_prerequisites("CS102")


def test_add_concurrent():
    graph = CourseGraph()
    graph.add_concurrent("CS102", "LAB102")

    assert "CS102" in graph.graph
    assert "LAB102" in graph.graph
    assert "LAB102" in graph.get_concurrent_requirements("CS102")


def test_get_prerequisites_empty():
    graph = CourseGraph()
    graph.add_course("CS101")
    assert graph.get_prerequisites("CS101") == set()


def test_get_concurrent_requirements_empty():
    graph = CourseGraph()
    graph.add_course("CS101")
    assert graph.get_concurrent_requirements("CS101") == set()
