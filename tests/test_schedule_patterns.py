from pathlib import Path

from create_schedule import main, load_program_json, build_course_index, pattern_allows


def test_generated_schedule_respects_patterns(neo4j_driver):
    program_path = Path("data/programs/program.bs7241.json")
    program = load_program_json(str(program_path))

    # Build course index from live DB to inspect patterns
    with neo4j_driver.session() as session:
        course_by_code, _ = session.execute_read(build_course_index, program)

    # Generate schedule using the real driver
    semesters = main(str(program_path), 15, neo4j_driver)

    # Verify each scheduled course is allowed by its pattern for that semester
    for semester_name, courses in semesters:
        parts = semester_name.split()
        term = parts[0].lower()
        year = int(parts[1])
        is_spring = term == "spring"

        for c in courses:
            node = course_by_code.get(c.upper(), {})
            pattern = node.get("pattern") if node else None
            assert pattern_allows(pattern, is_spring, year), (
                f"Course {c} scheduled in {semester_name} but pattern '{pattern}' disallows it"
            )
