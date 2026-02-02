from create_schedule import parse_requirement


def test_parse_none_requirement():
    req = parse_requirement({"type": "NONE"})
    assert req.type == "NONE"


def test_parse_course_requirement():
    req = parse_requirement(
        {"type": "COURSE", "course": "cs101", "timing": "COMPLETED"}
    )
    assert req.type == "COURSE"
    assert req.data["code"] == "CS101"
    assert req.data["timing"] == "COMPLETED"


def test_parse_and_requirement():
    req = parse_requirement(
        {
            "type": "AND",
            "requirements": [
                {"type": "COURSE", "course": "CS101"},
                {"type": "COURSE", "course": "CS102"},
            ],
        }
    )
    assert req.type == "AND"
    assert len(req.data["requirements"]) == 2


def test_parse_or_requirement():
    req = parse_requirement(
        {
            "type": "OR",
            "requirements": [
                {"type": "COURSE", "course": "CS101"},
                {"type": "COURSE", "course": "CS102"},
            ],
        }
    )
    assert req.type == "OR"
    assert len(req.data["requirements"]) == 2


def test_parse_unknown_requirement():
    req = parse_requirement({"type": "UNKNOWN"})
    assert req.type == "NONE"
