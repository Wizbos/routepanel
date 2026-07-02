#!/usr/bin/env python3
# scripts/seed_library.py
import json, sqlite3, sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "/etc/routepanel/db.sqlite"
lib_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/routepanel/service_library.json"

db = sqlite3.connect(db_path)
with open(lib_path) as f:
    packs = json.load(f)

for p in packs:
    db.execute(
        "INSERT OR IGNORE INTO service_library(id, name, domains, cidrs) VALUES(?,?,?,?)",
        (p["id"], p["name"], json.dumps(p["domains"]), json.dumps(p.get("cidrs", [])))
    )
db.commit()
db.close()
print(f"Seeded {len(packs)} service packs into {db_path}")
