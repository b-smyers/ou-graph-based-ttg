# WSL Setup
1. Download and install neo4j desktop
2. Create a DB and click the three dots on the DB
3. Select "Open > neo4j.conf"
4. Uncomment or add "server.default_listen_address=0.0.0.0"
5. Start/Restart DB through desktop interface
6. In WSL find windows IP using `ip route | grep default`
7. Set `.env` variable `NEO4J_DB_URI=neo4j://<Windows-IP>:7687`
8. Done. You are setup.

Extract classNumber, title, and requisite from courses
```bash
perl -00 -nE '
    while (/"classNumber":\s*([0-9]+).*?"title":\s*"([^"]*)".*?"requisite":\s*(null|"[^"]*")/sg) {
        say qq|{"classNumber": $1, "title": "$2", "requisite": $3}|;
    }
' courses.json > requirements.json
```