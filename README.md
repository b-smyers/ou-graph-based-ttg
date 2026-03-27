# OU Schedule Generator

Schedule generator

## Tools

- `course_offerings_tool.py` - Integrates with course offerings APIs to fetch course data locally.
- `dedupe.py` - Deduplicates JSON files by unique subject, catalog number, and component combinations.
- `get_course_patterns.py` - Fetches course patterns from university catalog and adds them to courses.
- `get_programs.py` - Fetches all programs from catalogs and saves to JSON.
- `parse_courses.py` - Uses LLM to parse course requisite strings into computer-readable form.
- `parse_program.py` - Uses LLM to parse program pages into computer-readable form.
- `scheduler/create_schedule.py` - Generates personalized academic schedules based on program requirements.