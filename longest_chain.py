from dotenv import load_dotenv
import os
import sys
from neo4j import GraphDatabase
from typing import List

load_dotenv()

# --------------------
# Config
# --------------------
URI = os.getenv("NEO4J_DB_URI")
AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

if not URI or not AUTH[0] or not AUTH[1]:
    print("[ERROR] Missing Neo4j configuration in environment")
    exit(1)

if len(sys.argv) < 2:
    print("Usage: longest_chain.py <COURSE_CODE> [COURSE_CODE ...]")
    exit(1)

COURSE_CODES = sys.argv[1:]

driver = GraphDatabase.driver(URI, auth=AUTH)  # type: ignore
driver.verify_connectivity()

# --------------------
# Core logic
# --------------------


def find_longest_chain(tx, course_codes: List[str]):
    """
    Returns the longest prerequisite chain (as course codes) among the given courses.
    """

    query = """
    MATCH (start:Course)
    WHERE start.code IN $codes

    // Traverse through ReqGroup transparently, but only count Course nodes
    MATCH path = (start)-[:REQUIRES*]->(end:Course)

    WITH
        path,
        [n IN nodes(path) WHERE n:Course | n.code] AS course_chain

    RETURN
        course_chain,
        size(course_chain) AS length
    ORDER BY length DESC
    LIMIT 1
    """

    result = tx.run(query, codes=course_codes)
    record = result.single()

    if record is None:
        return [], 0

    return record["course_chain"], record["length"]


# --------------------
# Entry point
# --------------------


def main():
    with driver.session() as session:
        chain, length = session.execute_read(find_longest_chain, COURSE_CODES)

    if length == 0:
        print("No prerequisite chains found.")
        return

    print("Longest prerequisite chain:")
    print(" → ".join(chain))
    print(f"Length: {length}")


if __name__ == "__main__":
    main()
