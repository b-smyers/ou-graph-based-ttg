from dotenv import load_dotenv
load_dotenv()
import os
from neo4j import GraphDatabase
import uuid
import json

# Config
CATALOG_PATH = os.getenv("CATALOG_PATH")
URI = os.getenv("NEO4J_DB_URI")
AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

if not CATALOG_PATH:
    print("[ ERROR ]: Missing CATALOG_PATH. Did you set the env?")
    exit()
if not URI:
    print("[ ERROR ]: Missing NEO4J_DB_URI. Did you set the env?")
    exit()
if not AUTH[0] or not AUTH[1]:
    print("[ ERROR ]: Missing NEO4J_USERNAME or NEO4J_PASSWORD. Did you set the env?")
    exit()

driver = GraphDatabase.driver(URI, auth=AUTH)
driver.verify_connectivity()

# Load catalog from external JSON file
with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)

# Utility functions
def clear_db(session):
    """
    Remove all nodes and relationships from the database.
    """
    session.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))

def create_course(tx, course_code, course_name):
    tx.run(
        "MERGE (c:Course {code: $code}) "
        "SET c.name = $name",
        code=course_code, name=course_name
    )


def create_reqgroup(tx, group_type):
    rg_uuid = str(uuid.uuid4())
    tx.run(
        "CREATE (rg:ReqGroup {type: $type, uuid: $uuid})",
        type=group_type, uuid=rg_uuid
    )
    return rg_uuid  # return the UUID, not id(rg)


def create_requires(tx, parent_uuid, rg_uuid):
    """
    Link a ReqGroup to its parent, which can be either a Course or a parent ReqGroup.
    """
    # parent_uuid can be a Course UUID or a ReqGroup UUID
    tx.run(
        """
        MATCH (parent {uuid:$parent_uuid}), (rg:ReqGroup {uuid:$rg_uuid})
        MERGE (parent)-[:REQUIRES]->(rg)
        """,
        parent_uuid=parent_uuid,
        rg_uuid=rg_uuid
    )

def include_course(tx, rg_uuid, course_code):
    tx.run(
        "MATCH (rg:ReqGroup {uuid:$rg_uuid}), (c:Course {code:$course_code}) "
        "MERGE (rg)-[:INCLUDES]->(c)",
        rg_uuid=rg_uuid, course_code=course_code
    )

def include_reqgroup(tx, rg_uuid, child_rg_uuid):
    tx.run(
        "MATCH (rg:ReqGroup {uuid:$rg_uuid}), (child:ReqGroup {uuid:$child_uuid}) "
        "MERGE (rg)-[:INCLUDES]->(child)",
        rg_uuid=rg_uuid, child_uuid=child_rg_uuid
    )

def include_placement(tx, rg_uuid, placement_uuid):
    tx.run(
        "MATCH (rg:ReqGroup {uuid:$rg_uuid}), (p:Placement {uuid:$p_uuid}) "
        "MERGE (rg)-[:INCLUDES]->(p)",
        rg_uuid=rg_uuid, p_uuid=placement_uuid
    )

def create_placement(tx, placement_name):
    placement_uuid = str(uuid.uuid4())
    tx.run(
        "CREATE (p:Placement {name: $name, uuid: $uuid})",
        name=placement_name, uuid=placement_uuid
    )
    return placement_uuid

# Recursive function to process requisites
def process_course(tx, course):
    # 1. create course node
    course_uuid = create_course(tx, course["code"], course["name"])

    # 2. process its requisites recursively
    req = course.get("requisite", {"type": "NONE"})
    if req["type"] != "NONE":
        process_requisite(tx, req, parent_uuid=course_uuid)

    return course_uuid

# Recursive function to process requisites
def process_requisite(tx, req, parent_uuid):
    t = req.get("type", "NONE")

    if t == "NONE":
        return None

    elif t == "COURSE":
        return {"type": "COURSE", "id": req["course"]}

    elif t == "PLACEMENT":
        placement_name = req.get("placement", "UNKNOWN")
        placement_uuid = create_placement(tx, placement_name)
        return {"type": "PLACEMENT", "id": placement_uuid}

    elif t in ("AND", "OR"):
        # create ReqGroup node
        rg_uuid = create_reqgroup(tx, t)

        # link group to parent (could be Course or parent ReqGroup)
        create_requires(tx, parent_uuid, rg_uuid)

        # process children
        for child in req.get("requirements", []):
            child_result = process_requisite(tx, child, parent_uuid=rg_uuid)
            if child_result is None:
                continue

            child_type = child_result["type"]
            child_id = child_result["id"]

            if child_type == "COURSE":
                include_course(tx, rg_uuid, child_id)
            elif child_type == "PLACEMENT":
                include_placement(tx, rg_uuid, child_id)
            elif child_type == "REQGROUP":
                include_reqgroup(tx, rg_uuid, child_id)
            else:
                raise ValueError(f"Unknown child type: {child_type}")

        return {"type": "REQGROUP", "id": rg_uuid}

    else:
        raise ValueError(f"Unknown requisite type: {t}")

def main():
    with driver.session() as session:
        clear_db(session)

        for course in catalog:
            session.execute_write(process_course, course)

    print("[INFO] Catalog loaded into Neo4j successfully.")

if __name__ == "__main__":
    main()
