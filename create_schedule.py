from dotenv import load_dotenv
import os
from logger import logger
import json
import sys
from neo4j import GraphDatabase


def get_db_credentials():
    """Load and validate Neo4j credentials from environment.

    Raises:
        ValueError: if required env vars are missing
    """
    load_dotenv()
    uri = os.getenv("NEO4J_DB_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    if not uri:
        raise ValueError("Missing NEO4J_DB_URI. Did you set the env?")
    if not username or not password:
        raise ValueError(
            "Missing NEO4J_USERNAME or NEO4J_PASSWORD. Did you set the env?"
        )

    return uri, (username, password)


def create_driver(uri, auth):
    """Create and verify a Neo4j driver connection.

    Args:
        uri: Neo4j database URI
        auth: tuple of (username, password)

    Returns:
        Neo4j driver instance

    Raises:
        Exception: if driver verification fails
    """
    driver = GraphDatabase.driver(uri, auth=auth)  # type: ignore
    driver.verify_connectivity()
    return driver


def parse_args(argv):
    """Parse and validate command-line arguments.

    Args:
        argv: list of command-line arguments (excluding script name)

    Returns:
        tuple of (program_path, credits_per_semester)

    Raises:
        ValueError: if arguments are invalid
    """
    if len(argv) < 2:
        raise ValueError(
            "Usage: create_schedule.py <program.json> <credits-per-semester>"
        )

    program_path = argv[0]
    try:
        credits_per_semester = int(argv[1])
    except ValueError:
        raise ValueError(f"credits-per-semester must be an integer, got: {argv[1]}")

    if not os.path.exists(program_path):
        raise ValueError(f"{program_path} does not exist")
    if not os.path.isfile(program_path):
        raise ValueError(f"{program_path} must be a file")
    if not credits_per_semester:
        raise ValueError("credits-per-semester must be a positive integer")

    if credits_per_semester < 12:
        logger.info("Credits Per Semester: Part-time enrollment")
    elif credits_per_semester <= 20:
        logger.info("Credits Per Semester: Full-time enrollment")
    elif credits_per_semester > 20:
        logger.info("Credits Per Semester: Overloaded enrollment")
    else:
        raise ValueError(f"Invalid credits per semester: {credits_per_semester}")

    return program_path, credits_per_semester


## Read
def find_course_by_code(tx, code):
    result = tx.run(
        """
        MATCH (node:COURSE {
            code: $code
        })
        RETURN node
        """,
        code=code,
    )

    record = result.single()
    if record is None:
        return
    node = record["node"]
    return node


def find_by_uuid(tx, node_uuid):
    result = tx.run(
        """
        MATCH (node {
            uuid: $uuid
        })
        RETURN node
        """,
        uuid=node_uuid,
    )

    record = result.single()
    if record is None:
        return
    node = record["node"]
    return node


def find_prerequisites(tx, course_code):
    """Find all courses that must be completed before taking the given course.

    Traverses through ReqGroup nodes to collect all prerequisite Course nodes.
    """
    result = tx.run(
        """
        MATCH (course:COURSE {code: $code})-[:REQUIRES*]->(prereq:COURSE)
        RETURN DISTINCT prereq
        """,
        code=course_code,
    )
    return [record["prereq"] for record in result]


def find_concurrent_requirements(tx, course_code):
    """Find all courses that must be taken concurrently with the given course (CONCURRENT relationship)."""
    result = tx.run(
        """
        MATCH (course:COURSE {code: $code})-[:CONCURRENT]->(concurrent)
        RETURN concurrent
        """,
        code=course_code,
    )
    return [record["concurrent"] for record in result]


def build_course_index(tx, program):
    """Build an in-memory index of all courses mentioned in the program.

    Returns:
        - course_by_code: dict mapping uppercase course codes to course nodes
        - course_by_uuid: dict mapping UUIDs to course nodes
    """
    course_by_code = {}
    course_by_uuid = {}

    # Extract all course codes from the program requisites
    course_codes = extract_all_course_codes(program.get("requisite", {}))

    logger.info(f"Extracted {len(course_codes)} unique course codes from program")

    # Query database for each course
    for i, code in enumerate(sorted(course_codes)):
        if i % 50 == 0:
            logger.info(f"Looking up courses {i}/{len(course_codes)}")

        node = find_course_by_code(tx, code)
        if node is None:
            logger.warn(f"Course not found in database: {code}")
            continue

        course_by_code[code.upper()] = node
        if "uuid" in node:
            course_by_uuid[node["uuid"]] = node

    logger.info(f"Successfully indexed {len(course_by_code)} courses")
    return course_by_code, course_by_uuid


def extract_all_course_codes(requisite, codes=None):
    """Recursively extract all course codes from a requisite structure."""
    if codes is None:
        codes = set()

    req_type = requisite.get("type", "NONE")

    if req_type == "COURSE":
        course_code = requisite.get("course", "").upper()
        if course_code:
            codes.add(course_code)
    elif req_type in ("AND", "OR", "CREDITS_FROM", "CHOOSE_N"):
        requirements = requisite.get("requirements", [])
        for req in requirements:
            extract_all_course_codes(req, codes)

    return codes


class RequirementNode:
    """Represents a parsed requirement node from the program."""

    def __init__(self, req_type, **kwargs):
        self.type = req_type
        self.data = kwargs


def parse_requirement(requisite):
    """Parse a requisite object into a RequirementNode.

    Handles all requirement types:
    - NONE: No requirement
    - COURSE: Specific course requirement with timing
    - LEVEL: Academic level requirement (freshman, sophomore, junior, senior)
    - PLACEMENT: Placement level requirement
    - PERMISSION: Permission requirement (assumed satisfied)
    - GPA: GPA requirement (assumed satisfied with 4.0 constant)
    - OTHER: Other requirements (assumed satisfied)
    - AND: All requirements must be satisfied
    - OR: At least one requirement must be satisfied
    - CREDITS_FROM: N credits from a list of options
    - CHOOSE_N: Choose N courses from a list of options
    """
    req_type = requisite.get("type", "NONE")

    if req_type == "NONE":
        return RequirementNode("NONE")

    elif req_type == "COURSE":
        course = requisite.get("course", "").upper()
        timing = requisite.get("timing", "COMPLETED")
        return RequirementNode("COURSE", code=course, timing=timing)

    elif req_type == "LEVEL":
        level = requisite.get("level", "").lower()
        return RequirementNode("LEVEL", level=level)

    elif req_type == "PLACEMENT":
        subject = requisite.get("subject", "")
        level = requisite.get("level", "")
        return RequirementNode("PLACEMENT", subject=subject, level=level)

    elif req_type == "PERMISSION":
        authority = requisite.get("authority", "Instructor")
        return RequirementNode("PERMISSION", authority=authority)

    elif req_type == "GPA":
        gpa = requisite.get("gpa", 4.0)
        return RequirementNode("GPA", gpa=gpa)

    elif req_type == "OTHER":
        other = requisite.get("other", "")
        return RequirementNode("OTHER", description=other)

    elif req_type == "AND":
        requirements = [
            parse_requirement(req) for req in requisite.get("requirements", [])
        ]
        return RequirementNode("AND", requirements=requirements)

    elif req_type == "OR":
        requirements = [
            parse_requirement(req) for req in requisite.get("requirements", [])
        ]
        return RequirementNode("OR", requirements=requirements)

    elif req_type == "CREDITS_FROM":
        credits_required = requisite.get("credits_required", 0)
        requirements = [
            parse_requirement(req) for req in requisite.get("requirements", [])
        ]
        return RequirementNode(
            "CREDITS_FROM", credits_required=credits_required, requirements=requirements
        )

    elif req_type == "CHOOSE_N":
        choose_n = requisite.get("choose", 1)
        requirements = [
            parse_requirement(req) for req in requisite.get("requirements", [])
        ]
        return RequirementNode("CHOOSE_N", choose_n=choose_n, requirements=requirements)

    else:
        logger.warn(f"Unknown requirement type: {req_type}")
        return RequirementNode("NONE")


def resolve_requirements(req_node, course_by_code, visited_reqs=None):
    """Recursively resolve a requirement tree into a list of required courses and constraints.

    Returns:
        - courses: list of course codes that must be taken
        - constraints: dict of additional constraints (levels, placements, etc.)
    """
    if visited_reqs is None:
        visited_reqs = set()

    # Detect cycles
    node_id = id(req_node)
    if node_id in visited_reqs:
        logger.error("Cycle detected in requirements!")
        return [], {}
    visited_reqs.add(node_id)

    courses = []
    constraints = {}

    if req_node.type == "NONE":
        return courses, constraints

    elif req_node.type == "COURSE":
        code = req_node.data["code"]
        if code in course_by_code or code.upper() in course_by_code:
            courses.append(code)
        else:
            logger.error(f"Course not found in database: {code}")
        return courses, constraints

    elif req_node.type == "LEVEL":
        level = req_node.data["level"]
        constraints["level"] = level
        return courses, constraints

    elif req_node.type == "PLACEMENT":
        subject = req_node.data["subject"]
        level = req_node.data["level"]
        constraints.setdefault("placements", []).append(
            {"subject": subject, "level": level}
        )
        return courses, constraints

    elif req_node.type == "PERMISSION":
        # Assume permission is satisfied
        logger.debug("PERMISSION requirement assumed satisfied")
        return courses, constraints

    elif req_node.type == "GPA":
        gpa = req_node.data["gpa"]
        # TODO: Implement GPA checking once system supports it
        logger.debug(f"GPA requirement {gpa} assumed satisfied (using 4.0 constant)")
        return courses, constraints

    elif req_node.type == "OTHER":
        # TODO: Implement OTHER requirement checking
        description = req_node.data.get("description", "Unknown")
        logger.debug(f"OTHER requirement '{description}' assumed satisfied")
        return courses, constraints

    elif req_node.type == "AND":
        # All requirements must be satisfied
        for req in req_node.data["requirements"]:
            sub_courses, sub_constraints = resolve_requirements(
                req, course_by_code, visited_reqs.copy()
            )
            courses.extend(sub_courses)
            # Merge constraints
            for key, value in sub_constraints.items():
                if key not in constraints:
                    constraints[key] = value
                elif isinstance(value, list):
                    constraints[key].extend(value)
        return courses, constraints

    elif req_node.type == "OR":
        # Choose the first option (greedy, deterministic)
        if req_node.data["requirements"]:
            logger.debug("OR requirement: choosing first option (greedy)")
            first_req = req_node.data["requirements"][0]
            return resolve_requirements(first_req, course_by_code, visited_reqs.copy())
        return courses, constraints

    elif req_node.type == "CREDITS_FROM":
        credits_required = req_node.data["credits_required"]
        requirements = req_node.data["requirements"]

        # Greedy: select courses/options until we reach credit requirement
        total_credits = 0
        selected_courses = []

        for req in requirements:
            if total_credits >= credits_required:
                break

            sub_courses, sub_constraints = resolve_requirements(
                req, course_by_code, visited_reqs.copy()
            )

            # Calculate credits for this option
            option_credits = 0
            for course_code in sub_courses:
                if course_code.upper() in course_by_code:
                    node = course_by_code[course_code.upper()]
                    course_credits = node.get("min_credits", 0)
                    if isinstance(course_credits, (int, float)):
                        option_credits += course_credits

            selected_courses.extend(sub_courses)
            total_credits += option_credits

            # Merge constraints
            for key, value in sub_constraints.items():
                if key not in constraints:
                    constraints[key] = value
                elif isinstance(value, list):
                    constraints[key].extend(value)

        if total_credits < credits_required:
            logger.warn(
                f"Could not satisfy CREDITS_FROM requirement: {total_credits}/{credits_required} credits"
            )

        return selected_courses, constraints

    elif req_node.type == "CHOOSE_N":
        choose_n = req_node.data["choose_n"]
        requirements = req_node.data["requirements"]

        # Greedy: select first N options
        selected_courses = []
        logger.debug(
            f"CHOOSE_N requirement: selecting {choose_n} of {len(requirements)} options (greedy)"
        )

        for i in range(min(choose_n, len(requirements))):
            req = requirements[i]
            sub_courses, sub_constraints = resolve_requirements(
                req, course_by_code, visited_reqs.copy()
            )
            selected_courses.extend(sub_courses)

            # Merge constraints
            for key, value in sub_constraints.items():
                if key not in constraints:
                    constraints[key] = value
                elif isinstance(value, list):
                    constraints[key].extend(value)

        return selected_courses, constraints

    else:
        logger.error(f"Unknown requirement type during resolution: {req_node.type}")
        return courses, constraints


class CourseGraph:
    """Represents the dependency graph of courses."""

    def __init__(self):
        self.graph = {}  # course_code -> {'requires': [course_codes], 'concurrent': [course_codes]}

    def add_course(self, course_code):
        """Add a course to the graph."""
        if course_code not in self.graph:
            self.graph[course_code] = {"requires": set(), "concurrent": set()}

    def add_requires(self, parent_code, child_code):
        """Add a REQUIRES edge."""
        self.add_course(parent_code)
        self.add_course(child_code)
        self.graph[parent_code]["requires"].add(child_code)

    def add_concurrent(self, parent_code, child_code):
        """Add a CONCURRENT edge."""
        self.add_course(parent_code)
        self.add_course(child_code)
        self.graph[parent_code]["concurrent"].add(child_code)

    def get_prerequisites(self, course_code):
        """Get all courses that must be completed before this course."""
        if course_code not in self.graph:
            return set()
        return self.graph[course_code]["requires"]

    def get_concurrent_requirements(self, course_code):
        """Get all courses that must be taken concurrently with this course."""
        if course_code not in self.graph:
            return set()
        return self.graph[course_code]["concurrent"]


def build_dependency_graph(tx, required_courses, course_by_code):
    """Build an in-memory dependency graph for all required courses.

    Phase 3.1: For each course, retrieve all REQUIRES and CONCURRENT relationships
    from the Neo4j database.
    """
    graph = CourseGraph()

    # Build set of required course codes (uppercase) for filtering
    required_upper = set(c.upper() for c in required_courses)

    # For each required course, fetch its prerequisites and concurrent requirements
    for i, course_code in enumerate(sorted(required_courses)):
        if i % 50 == 0:
            logger.info(f"Building dependency graph {i}/{len(required_courses)}")

        graph.add_course(course_code.upper())

        # Get prerequisites from database
        prerequisites = find_prerequisites(tx, course_code)

        # Add only those prerequisites that are in our required courses
        for prereq_node in prerequisites:
            if "code" in prereq_node:
                prereq_code = prereq_node["code"].upper()
                if prereq_code in required_upper:
                    graph.add_requires(course_code.upper(), prereq_code)

        # Get concurrent requirements
        concurrents = find_concurrent_requirements(tx, course_code)
        for concurrent_node in concurrents:
            if "code" in concurrent_node:
                concurrent_code = concurrent_node["code"].upper()
                if concurrent_code in required_upper:
                    graph.add_concurrent(course_code.upper(), concurrent_code)

    logger.info(f"Built dependency graph with {len(graph.graph)} courses")

    return graph


def topological_sort(graph, required_courses):
    """Perform topological sort on the course dependency graph.

    Phase 3.2: Implement DFS-based topological sort with cycle detection.

    Returns:
        - sorted_courses: list of courses in topological order
        - has_cycle: boolean indicating if a cycle was detected
    """
    visited = {}  # 0: unvisited, 1: visiting, 2: visited
    sorted_courses = []
    has_cycle = False

    for course in required_courses:
        visited[course.upper()] = 0

    def dfs(course):
        nonlocal has_cycle

        if course not in visited:
            visited[course] = 0

        if visited[course] == 1:
            # Cycle detected
            logger.error(f"Cycle detected in prerequisites involving {course}")
            has_cycle = True
            return

        if visited[course] == 2:
            # Already processed
            return

        visited[course] = 1  # Mark as visiting

        # Visit all prerequisites
        for prereq in graph.get_prerequisites(course):
            if prereq in visited:
                dfs(prereq)

        visited[course] = 2  # Mark as visited
        sorted_courses.append(course)

    # Process all required courses
    for course in sorted(required_courses):
        course_upper = course.upper()
        if visited.get(course_upper, 0) == 0:
            dfs(course_upper)

    if has_cycle:
        logger.error("Cannot proceed with scheduling due to cycles in prerequisites")
        return [], True

    return sorted_courses, False


def check_prerequisites_satisfied(
    course_code, graph, completed_courses, accumulated_credits, placements
):
    """Check if all prerequisites for a course are satisfied.

    Phase 3.3: Implement prerequisite checking for REQUIRES, CONCURRENT, LEVEL, and PLACEMENT.
    """
    # Check REQUIRES prerequisites (must be completed before)
    for prereq in graph.get_prerequisites(course_code):
        if prereq not in completed_courses:
            return False, f"Requires {prereq}"

    # Check CONCURRENT prerequisites (must be taken at same time or before)
    # These will be handled separately during scheduling

    return True, None


class ScheduleState:
    """Tracks the state of a semester schedule."""

    def __init__(self):
        self.semesters = []  # List of lists: each inner list is courses for a semester
        self.completed_courses = set()
        self.accumulated_credits = 0
        self.concurrent_requirements = {}  # course_code -> [list of courses that must be taken with it]


def generate_semesters(
    required_courses,
    graph,
    course_by_code,
    credits_per_semester,
    start_year=2025,
    start_spring=True,
):
    """Generate a course schedule respecting prerequisites and credit limits.

    Phase 4: Implement scheduling algorithm.
    Returns:
        - list of semesters, each containing list of course codes
    """
    state = ScheduleState()

    # Track which courses still need to be scheduled
    # Normalize all course codes to uppercase for comparison
    courses_to_schedule = set(course.upper() for course in required_courses)
    current_year = start_year
    is_spring = start_spring

    max_iterations = 20  # Prevent infinite loops
    iteration = 0

    while courses_to_schedule and iteration < max_iterations:
        iteration += 1
        semester_courses = []
        semester_credits = 0

        # Try to add courses to this semester (in sorted order for determinism)
        for course_code in sorted(courses_to_schedule):
            if course_code not in course_by_code:
                logger.warn(f"Course not in database: {course_code}")
                courses_to_schedule.discard(course_code)
                continue

            # Check prerequisites - must be satisfied by PREVIOUSLY completed courses
            # NOT by courses in the current semester (except for CONCURRENT relationships)
            prereqs_ok, prereq_msg = check_prerequisites_satisfied(
                course_code,
                graph,
                state.completed_courses,
                state.accumulated_credits,
                {},
            )
            if not prereqs_ok:
                continue

            # Check if we can add this course
            course_node = course_by_code[course_code]
            course_credits = course_node.get("min_credits", 0)
            if isinstance(course_credits, str):
                try:
                    course_credits = int(course_credits)
                except Exception:
                    course_credits = 3  # Default

            if semester_credits + course_credits <= credits_per_semester:
                semester_courses.append(course_code)
                semester_credits += course_credits
                courses_to_schedule.discard(course_code)

        if semester_courses:
            # Record this semester
            semester_name = f"{'Spring' if is_spring else 'Fall'} {current_year}"
            state.semesters.append((semester_name, semester_courses))

            # Update state
            state.completed_courses.update(semester_courses)
            state.accumulated_credits += semester_credits

            logger.info(
                f"{semester_name}: {', '.join(semester_courses)} ({semester_credits} credits)"
            )
        else:
            if courses_to_schedule:
                logger.error(
                    f"Cannot schedule remaining courses: {', '.join(sorted(courses_to_schedule))}"
                )
            break

        # Move to next semester
        if is_spring:
            is_spring = False
        else:
            is_spring = True
            current_year += 1

    if iteration >= max_iterations:
        logger.error("Scheduling took too many iterations, possible infinite loop")

    return state.semesters


def load_program_json(program_path):
    """Load and parse program.json file.

    Args:
        program_path: path to program JSON file

    Returns:
        parsed program dictionary

    Raises:
        FileNotFoundError: if file does not exist
        ValueError: if JSON is malformed
    """
    try:
        with open(program_path, "r", encoding="utf-8") as f:
            program = json.load(f)
        return program
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Program file not found: {program_path}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse program.json as JSON: {e}") from e


def extract_program_metadata(program):
    """Extract program metadata from program.json."""
    metadata = {
        "name": program.get("program_name", "Unknown"),
        "code": program.get("code", "Unknown"),
        "total_credits": program.get("credits", 0),
        "catalog_year": program.get("catalog_year", None),
        "program_type": program.get("program_type", "Unknown"),
    }
    return metadata


def main(program_path, credits_per_semester, driver):
    """Main scheduling pipeline.

    Args:
        program_path: path to program.json file
        credits_per_semester: number of credits per semester
        driver: Neo4j driver instance

    Raises:
        various exceptions from parsing, validation, or scheduling phases
    """
    # Phase 1.1: Parse Program JSON
    logger.info("Phase 1.1: Loading and parsing program.json")
    program = load_program_json(program_path)
    metadata = extract_program_metadata(program)
    logger.info(f"Loaded program: {metadata['name']} ({metadata['code']})")
    logger.info(f"Total credits required: {metadata['total_credits']}")
    logger.info(f"Credits per semester: {credits_per_semester}")

    with driver.session() as session:
        # Phase 1.2 & 1.3: Build course index
        logger.info("Phase 1.2-1.3: Building course lookup index")
        course_by_code, course_by_uuid = session.execute_read(
            build_course_index, program
        )

        # Phase 2: Requirement Analysis
        logger.info("Phase 2: Analyzing requirements")
        root_requisite = program.get("requisite", {"type": "NONE"})
        parsed_req = parse_requirement(root_requisite)
        required_courses, constraints = resolve_requirements(parsed_req, course_by_code)

        logger.info(f"Extracted {len(required_courses)} required courses")
        logger.debug(f"Constraints: {constraints}")

        # Phase 3: Build Dependency Graph
        logger.info("Phase 3: Building dependency graph")
        graph = session.execute_read(
            build_dependency_graph, required_courses, course_by_code
        )

        # Phase 3.2: Topological Sort
        logger.info("Phase 3.2: Performing topological sort")
        sorted_courses, has_cycle = topological_sort(graph, required_courses)
        if has_cycle:
            exit(1)

        # Phase 4: Generate Schedule
        logger.info("Phase 4: Generating schedule")
        semesters = generate_semesters(
            required_courses, graph, course_by_code, credits_per_semester
        )

        # Phase 5: Output Schedule
        logger.info("===== GENERATED SCHEDULE =====")
        for semester_name, courses in semesters:
            logger.info(f"{semester_name}: {', '.join(courses)}")

        logger.info(f"Total semesters: {len(semesters)}")
        total_credits = 0
        for semester_name, courses in semesters:
            semester_credits = 0
            for c in courses:
                if c in course_by_code:
                    cred = course_by_code[c].get("min_credits", 0)
                    if isinstance(cred, str):
                        try:
                            cred = int(cred)
                        except Exception:
                            cred = 0
                    semester_credits += cred
            total_credits += semester_credits
        logger.info(f"Total credits scheduled: {total_credits}")


if __name__ == "__main__":
    try:
        program_path, credits_per_semester = parse_args(sys.argv[1:])
        uri, auth = get_db_credentials()
        driver = create_driver(uri, auth)
        main(program_path, credits_per_semester, driver)
    except (ValueError, FileNotFoundError, Exception) as e:
        logger.error(str(e))
        sys.exit(1)
