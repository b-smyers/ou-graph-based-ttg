from create_schedule import extract_all_course_codes


def test_extract_single_course():
    requisite = {"type": "COURSE", "course": "CS101"}
    codes = extract_all_course_codes(requisite)
    assert codes == {"CS101"}


def test_extract_nested_and():
    requisite = {
        "type": "AND",
        "requirements": [
            {"type": "COURSE", "course": "CS101"},
            {"type": "COURSE", "course": "CS102"},
        ],
    }
    codes = extract_all_course_codes(requisite)
    assert codes == {"CS101", "CS102"}


def test_extract_nested_or():
    requisite = {
        "type": "OR",
        "requirements": [
            {"type": "COURSE", "course": "CS101"},
            {"type": "COURSE", "course": "CS102"},
        ],
    }
    codes = extract_all_course_codes(requisite)
    assert codes == {"CS101", "CS102"}


def test_extract_credits_from():
    requisite = {
        "type": "CREDITS_FROM",
        "credits_required": 12,
        "requirements": [
            {"type": "COURSE", "course": "ELEC301"},
            {"type": "COURSE", "course": "ELEC302"},
        ],
    }
    codes = extract_all_course_codes(requisite)
    assert codes == {"ELEC301", "ELEC302"}


def test_extract_choose_n():
    requisite = {
        "type": "CHOOSE_N",
        "choose": 2,
        "requirements": [
            {"type": "COURSE", "course": "ELEC301"},
            {"type": "COURSE", "course": "ELEC302"},
            {"type": "COURSE", "course": "ELEC303"},
        ],
    }
    codes = extract_all_course_codes(requisite)
    assert codes == {"ELEC301", "ELEC302", "ELEC303"}


def test_extract_deeply_nested():
    requisite = {
        "type": "AND",
        "requirements": [
            {"type": "COURSE", "course": "CS101"},
            {
                "type": "OR",
                "requirements": [
                    {"type": "COURSE", "course": "CS201"},
                    {"type": "COURSE", "course": "CS202"},
                ],
            },
        ],
    }
    codes = extract_all_course_codes(requisite)
    assert codes == {"CS101", "CS201", "CS202"}
