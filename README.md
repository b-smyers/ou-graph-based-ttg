# OU Graph Based Time-To-Graduation
A graph-based approach to accurately estimating time-to-graduation at Ohio University.

## Shared Setup
```bash
cp .env.sample .env
uv sync
```

## Neo4j Setup
### WSL
1. Download and install neo4j desktop
2. Create a DB and click the three dots on the DB
7. Set `.env` variable `NEO4J_PASSWORD` (and `NEO4J_USERNAME` if you are not using the default)
3. Select "Open > neo4j.conf"
4. Uncomment or add "server.default_listen_address=0.0.0.0"
5. Start/Restart DB through Neo4j desktop application
6. In WSL find your windows IP using `ip route | grep default`
7. Set `.env` variable `NEO4J_DB_URI=neo4j://<Windows-IP>:7687`

## Running
### Populating Database
```bash
uv run load.py data/catalog.sample.json
```

### Finding Longest Requirement Chain
```bash
uv run longest_chain.py "CS 2401"
```