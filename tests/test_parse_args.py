import pytest

from create_schedule import parse_args


def test_parse_args_valid_input(tmp_path):
    program_file = tmp_path / "program.json"
    program_file.write_text("{}")

    program_path, credits = parse_args([str(program_file), "15"])
    assert program_path == str(program_file)
    assert credits == 15


def test_parse_args_missing_arguments():
    with pytest.raises(ValueError, match="Usage:"):
        parse_args([])


def test_parse_args_non_integer_credits(tmp_path):
    program_file = tmp_path / "program.json"
    program_file.write_text("{}")

    with pytest.raises(ValueError, match="must be an integer"):
        parse_args([str(program_file), "not_a_number"])


def test_parse_args_file_not_found():
    with pytest.raises(ValueError, match="does not exist"):
        parse_args(["/nonexistent/program.json", "15"])


def test_parse_args_not_a_file(tmp_path):
    with pytest.raises(ValueError, match="must be a file"):
        parse_args([str(tmp_path), "15"])
