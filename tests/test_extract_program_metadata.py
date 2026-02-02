from create_schedule import extract_program_metadata


def test_extract_program_metadata(sample_program):
    metadata = extract_program_metadata(sample_program)

    assert metadata["name"] == sample_program["program_name"]
    assert metadata["code"] == sample_program["code"]
    assert metadata["total_credits"] == sample_program["credits"]
