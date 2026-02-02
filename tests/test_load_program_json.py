import json
import pytest

from create_schedule import load_program_json


def test_load_program_json_valid(tmp_path):
    program_file = tmp_path / "program.json"
    test_program = {
        "program_name": "Test",
        "code": "TEST",
        "credits": 120,
        "requisite": {},
    }
    program_file.write_text(json.dumps(test_program))

    result = load_program_json(str(program_file))
    assert result == test_program


def test_load_program_json_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_program_json("/nonexistent/program.json")


def test_load_program_json_invalid_json(tmp_path):
    program_file = tmp_path / "program.json"
    program_file.write_text("{invalid json")

    with pytest.raises(ValueError, match="Failed to parse"):
        load_program_json(str(program_file))
