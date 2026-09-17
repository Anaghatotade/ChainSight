#!/bin/bash
# =============================================================================
# rebrand.sh — renames the project from "SCIP" to "ChainSight"
#
# Run this ONCE from the project root (the folder containing docker-compose.yml).
#
# On Windows:
#   - Easiest: open the project folder, right-click -> "Open Git Bash here",
#     then run:  bash rebrand.sh
#   - Or via WSL: open a WSL terminal, cd to the Windows path (usually under
#     /mnt/c/Users/...), then run:  bash rebrand.sh
#
# On Mac/Linux:
#   cd supply-chain-platform && bash rebrand.sh
#
# Safe to re-run: if already renamed, it just won't find anything to change.
# =============================================================================
set -e

if [ ! -f "docker-compose.yml" ]; then
  echo "ERROR: run this script from the project root (the folder with docker-compose.yml in it)."
  exit 1
fi

echo "Renaming backend identifiers (DB user/password/db name)..."
sed -i.bak \
  -e 's/scip_user/chainsight_user/g' \
  -e 's/scip_pass/chainsight_pass/g' \
  -e 's/scip_db/chainsight_db/g' \
  backend/app/core/config.py

echo "Renaming demo user emails..."
sed -i.bak -e 's/@scip\.io/@chainsight.io/g' backend/app/etl/seed_users.py

echo "Renaming backend logger name..."
sed -i.bak -e 's/logging\.getLogger("scip")/logging.getLogger("chainsight")/' backend/app/main.py

echo "Updating docker-compose.yml (container names, volumes, db credentials)..."
sed -i.bak \
  -e 's/scip_db/chainsight_db/g' \
  -e 's/scip_user/chainsight_user/g' \
  -e 's/scip_pass/chainsight_pass/g' \
  -e 's/scip_backend_cache/chainsight_backend_cache/g' \
  -e 's/scip_pgdata/chainsight_pgdata/g' \
  -e 's/scip_backend/chainsight_backend/g' \
  -e 's/scip_frontend/chainsight_frontend/g' \
  docker-compose.yml

echo "Updating frontend localStorage keys..."
sed -i.bak -e 's/scip_token/chainsight_token/g; s/scip_user/chainsight_user/g' \
  frontend/app/page.tsx frontend/contexts/AuthContext.tsx frontend/lib/api.ts

echo "Updating frontend demo login emails..."
sed -i.bak -e 's/@scip\.io/@chainsight.io/g' frontend/app/login/page.tsx

echo "Updating project title/branding text..."
sed -i.bak -e 's/PROJECT_NAME: str = "Supply Chain Intelligence Platform"/PROJECT_NAME: str = "ChainSight"/' \
  backend/app/core/config.py

sed -i.bak -e 's/title: "Supply Chain Intelligence Platform"/title: "ChainSight | Supply Chain Intelligence Platform"/' \
  frontend/app/layout.tsx

sed -i.bak -e 's|<h1 className="text-xl font-bold text-white">Supply Chain Intelligence</h1>|<h1 className="text-xl font-bold text-white">ChainSight</h1>|' \
  frontend/app/login/page.tsx

sed -i.bak -e 's|<h1 className="text-white font-bold text-lg leading-tight">Supply Chain<br />Intelligence</h1>|<h1 className="text-white font-bold text-lg leading-tight">ChainSight</h1>|' \
  frontend/components/AppShell.tsx

sed -i.bak -e 's/"name": "supply-chain-intelligence-frontend"/"name": "chainsight-frontend"/' \
  frontend/package.json

echo "Updating README.md and db/init.sql headers..."
sed -i.bak \
  -e 's/# Supply Chain Intelligence \& Decision Support Platform/# ChainSight — Supply Chain Intelligence \& Decision Support Platform/' \
  -e 's/@scip\.io/@chainsight.io/g' \
  -e 's/scip_user/chainsight_user/g' \
  -e 's/scip_pass/chainsight_pass/g' \
  -e 's/scip_db/chainsight_db/g' \
  README.md

sed -i.bak -e 's/-- Supply Chain Intelligence \& Decision Support Platform/-- ChainSight — Supply Chain Intelligence \& Decision Support Platform/' \
  db/init.sql

echo "Cleaning up .bak files created by sed..."
find . -name "*.bak" -delete

echo ""
echo "Done! The project is now branded as 'ChainSight'."
echo ""
echo "IMPORTANT NEXT STEPS:"
echo "  1. If you previously ran 'docker compose up' before this rename, the old"
echo "     database volume (named after the old scip_ names) is now orphaned."
echo "     To start completely fresh, run:"
echo "         docker compose down -v"
echo "     (the -v also deletes the old database volume so data regenerates cleanly)"
echo ""
echo "  2. Rebuild and start:"
echo "         docker compose up --build"
echo ""
echo "  3. New demo login emails are now:"
echo "         admin@chainsight.io    / Admin123!"
echo "         analyst@chainsight.io  / Analyst123!"
echo "         viewer@chainsight.io   / Viewer123!"
