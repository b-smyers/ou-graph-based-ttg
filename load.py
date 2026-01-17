from dotenv import load_dotenv
import os
import sys
from neo4j import GraphDatabase
import uuid
import json

load_dotenv()
# load.py: Clears the database before loading the data from the provided <catalog-path> into the database

# Config
CATALOG_PATH = sys.argv[1] if len(sys.argv) >= 2 else None
URI = os.getenv("NEO4J_DB_URI")
AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

if not CATALOG_PATH:
    print("Usage: load.py <catalog-path>")
    exit()
if not URI:
    print("[ ERROR ]: Missing NEO4J_DB_URI. Did you set the env?")
    exit()
if not AUTH[0] or not AUTH[1]:
    print("[ ERROR ]: Missing NEO4J_USERNAME or NEO4J_PASSWORD. Did you set the env?")
    exit()

driver = GraphDatabase.driver(URI, auth=AUTH)  # type: ignore
driver.verify_connectivity()

# Load catalog from external JSON file
with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)


# Utility functions
def clear_db(session):
    session.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))


## Create
def create_course(tx, course_code, course_name, requisite_string):
    course_uuid = str(uuid.uuid4())
    tx.run(
        """
        MERGE (c:COURSE {
            name: $name,
            uuid: $uuid,
            code: $code,
            requisite_string: $requisite_string
        })
        """,
        name=course_name,
        code=course_code,
        uuid=course_uuid,
        requisite_string=requisite_string,
    )
    return course_uuid


def create_placement(tx, subject, level):
    new_uuid = str(uuid.uuid4())
    placement_name = f"{subject} Placement Level {level}"

    # MERGE based on the unique combination of subject and level
    result = tx.run(
        """
        MERGE (p:PLACEMENT { subject: $subject, level: $level })
        ON CREATE SET 
            p.uuid = $uuid,
            p.name = $name
        RETURN p.uuid AS uuid
        """,
        subject=subject,
        level=level,
        name=placement_name,
        uuid=new_uuid,
    )

    # Return the UUID (either the pre-existing one or the one we just generated)
    record = result.single()
    return record["uuid"]


def create_level(tx, level):
    level_to_credits = {"freshman": 0, "sophomore": 30, "junior": 60, "senior": 90}
    if level not in level_to_credits:
        print(
            f"[ ERROR ]: '{level}' did not match any level options: {', '.join(list(level_to_credits.keys()))}"
        )
        return None

    level_name = level.title()
    level_req_uuid = str(uuid.uuid4())

    # Use MERGE to find or create the node based on the name
    result = tx.run(
        """
        MERGE (cr:LEVEL { name: $name })
        ON CREATE SET 
            cr.uuid = $uuid, 
            cr.credits = $credits
        RETURN cr.uuid as uuid
        """,
        name=level_name,
        uuid=level_req_uuid,
        credits=level_to_credits[level],
    )

    # Return the uuid (either the existing one or the new one)
    record = result.single()
    return record["uuid"]


def create_permission(tx, authority):
    permission_req_uuid = str(uuid.uuid4())
    tx.run(
        """
        CREATE (cr:PERMISSION {
            name: $name,
            uuid: $uuid,
            authority: $authority
        })
        """,
        name=f"Permission from {authority}",
        uuid=permission_req_uuid,
        authority=authority,
    )
    return permission_req_uuid


def create_gpa(tx, gpa):
    gpa_req_uuid = str(uuid.uuid4())
    tx.run(
        """
        CREATE (cr:GPA {
            name: $name,
            uuid: $uuid
        })
        """,
        name=f"{gpa} GPA",
        uuid=gpa_req_uuid,
        gpa=gpa,
    )
    return gpa_req_uuid


def create_other(tx, other):
    other_req_uuid = str(uuid.uuid4())
    tx.run(
        """
        CREATE (cr:OTHER {
            name: $name,
            uuid: $uuid
        })
        """,
        name=other,
        uuid=other_req_uuid,
    )
    return other_req_uuid


def create_reqgroup(tx, group_type):
    reqgroup_uuid = str(uuid.uuid4())
    tx.run(
        """
        CREATE (rg:ReqGroup {
            name: $type,
            uuid: $uuid,
            type: $type
        })
        """,
        type=group_type,
        uuid=reqgroup_uuid,
    )
    return reqgroup_uuid


def create_requires(tx, parent_uuid, child_uuid):
    tx.run(
        """
        MATCH (parent {
            uuid: $parent_uuid
        })
        MERGE (child {
            uuid: $child_uuid
        })
        MERGE (parent)-[:REQUIRES]->(child)
        """,
        parent_uuid=parent_uuid,
        child_uuid=child_uuid,
    )


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


def process_course_requisites(tx, course):
    # Find the course by its code to get its UUID
    node = find_course_by_code(tx, code=course["code"])
    if node is None:
        print("[ERROR] Could not find previously imported course.")
        return  # Course not found (should not happen)
    course_uuid = node["uuid"]

    # Process its requisites
    req = course.get("requisite", {"type": "NONE"})
    if req is not None and req["type"] != "NONE":
        process_requisite(tx, req, parent_uuid=course_uuid)


# Recursive function to process requisites
def process_requisite(tx, req, parent_uuid):
    t = req.get("type", "NONE")

    if t == "NONE":
        return None

    if t == "PERMISSION":
        permission_authority = req.get("authority", None)
        if permission_authority is not None:
            permission_uuid = create_permission(tx, permission_authority)
            create_requires(tx, parent_uuid, permission_uuid)
        else:
            print("[ERROR] 'authority' property was expected, but was not found")

    elif t == "GPA":
        gpa = req.get("gpa", None)
        if gpa is not None:
            gpa_uuid = create_gpa(tx, gpa)
            create_requires(tx, parent_uuid, gpa_uuid)
        else:
            print("[ERROR] 'gpa' property was expected, but was not found")

    elif t == "COURSE":
        course_code = req.get("course", None)
        if course_code is not None:
            node = find_course_by_code(tx, course_code)
            if node is None:
                print(
                    f"[WARN] Could not find requisite course with course code '{course_code}'."
                )
                return
            create_requires(tx, parent_uuid, node["uuid"])
        else:
            print("[ERROR] 'course' property was expected, but was not found")

    elif t == "PLACEMENT":
        placement_subject = req.get("subject", None)
        placement_level = req.get("level", None)
        if placement_subject is None:
            print("[ERROR] 'placement' property was expected, but was not found")
            return
        if placement_level is None:
            print("[ERROR] 'level' property was expected, but was not found")
            return

        placement_uuid = create_placement(tx, placement_subject, placement_level)
        create_requires(tx, parent_uuid, placement_uuid)

    elif t == "LEVEL":
        level_name = req.get("level", None)
        if level_name is not None:
            level_uuid = create_level(tx, level_name)
            create_requires(tx, parent_uuid, level_uuid)
        else:
            print("[ERROR] 'level' property was expected, but was not found")

    elif t in ("AND", "OR"):
        requirements = req.get("requirements", None)
        if requirements is not None:
            reqgroup_uuid = create_reqgroup(tx, t)
            create_requires(tx, parent_uuid, reqgroup_uuid)

            for c in requirements:
                process_requisite(tx, c, parent_uuid=reqgroup_uuid)
        else:
            print("[ERROR] 'requirements' property was expected, but was not found")

    elif t == "OTHER":
        other = req.get("other", None)
        if other is not None:
            other_uuid = create_other(tx, other)
            create_requires(tx, parent_uuid, other_uuid)
        else:
            print("[ERROR] 'other' property was expected, but was not found")

    else:
        raise ValueError(
            f"Unknown requisite type: {t}, only NONE, LEVEL, COURSE, PLACEMENT, AND, OR are allowed."
        )


def main():
    with driver.session() as session:
        print("[INFO] Cleared DB.")
        clear_db(session)

        total_courses = len(catalog)

        print(f"[INFO] Creating {total_courses} course nodes.")
        # First pass: Create all course nodes
        for i, course in enumerate(catalog):
            if i % 100 == 0:
                print(
                    f"[INFO] Creating courses {i}/{total_courses} - {round(100 * i / total_courses, 2)}%"
                )
            session.execute_write(
                create_course,
                course["code"],
                course["name"],
                course["requisite_string"] or "",
            )

        print("[INFO] Creating requisites relationships.")
        # Second pass: Process requisites
        for i, course in enumerate(catalog):
            if i % 100 == 0:
                print(
                    f"[INFO] Processing course requisites {i}/{total_courses} - {round(100 * i / total_courses, 2)}%"
                )
            session.execute_write(process_course_requisites, course)

    print("[INFO] Catalog loaded into Neo4j.")


if __name__ == "__main__":
    main()
