import os
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase
from logger import logger


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


def create_driver(uri, auth) -> Driver:
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


def expand_required_courses(tx, required_courses, course_by_code):
    """Expand required courses to include all transitive prerequisites.

    Starting from the initial set of required courses, recursively find all
    prerequisites and add them to the set. This ensures that implicit
    dependencies are included in the schedule.

    Args:
        tx: Neo4j transaction
        required_courses: set of initial required course codes
        course_by_code: dict mapping course codes to course info

    Returns:
        expanded_courses: set of all required courses including transitive prerequisites
    """
    expanded = set(c.upper() for c in required_courses)
    to_process = list(expanded)
    iteration = 0

    while to_process:
        iteration += 1
        if iteration % 10 == 1:
            logger.info(
                f"Expanding required courses (iteration {iteration}, found {len(expanded)} so far)"
            )

        course_code = to_process.pop(0)

        # Find all prerequisites for this course
        prerequisites = find_prerequisites(tx, course_code)

        for prereq_node in prerequisites:
            prereq_code = prereq_node["code"].upper()
            if prereq_code not in expanded:
                expanded.add(prereq_code)
                to_process.append(prereq_code)

                # Also add to course_by_code if not already there
                if prereq_code not in course_by_code:
                    course_by_code[prereq_code] = {
                        "code": prereq_code,
                        "name": prereq_node.get("name", "Unknown"),
                        "min_credits": prereq_node.get("min_credits", 0),
                    }

    logger.info(f"Expanded from {len(required_courses)} to {len(expanded)} courses")
    return expanded


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
