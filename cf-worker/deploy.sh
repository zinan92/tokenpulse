#!/bin/bash
# TokenPulse global ranking server — one-shot deploy to Cloudflare.
#
# Prereq (one time):  node /opt/homebrew/lib/node_modules/wrangler/bin/wrangler.js login
# Then:               bash cf-worker/deploy.sh
set -e
cd "$(dirname "$0")"

W="node /opt/homebrew/lib/node_modules/wrangler/bin/wrangler.js"
UUID_RE='[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

echo "=== Step 1: D1 database ==="
EXISTING_ID=$(grep -oE "database_id *= *\"$UUID_RE\"" wrangler.toml | grep -oE "$UUID_RE" | head -1)
if [ -n "$EXISTING_ID" ]; then
    # Idempotent: wrangler.toml already points at a real DB — reuse it, don't
    # create a second one or silently fail the PLACEHOLDER sed on re-runs.
    echo "  reusing existing database_id = $EXISTING_ID"
else
    DB_OUT=$($W d1 create tokenpulse-rankings 2>&1 || true)
    echo "$DB_OUT"
    DB_ID=$(echo "$DB_OUT" | grep -oE "$UUID_RE" | head -1)
    if [ -z "$DB_ID" ]; then
        echo ""
        echo "Could not auto-detect database_id (it may already exist)."
        echo "Run '$W d1 list' to find it, then paste the database_id here:"
        read -r DB_ID
    fi
    echo "  database_id = $DB_ID"
    sed -i.bak "s/database_id *= *\"PLACEHOLDER\"/database_id = \"$DB_ID\"/" wrangler.toml
    rm -f wrangler.toml.bak
fi

echo ""
echo "=== Step 2: create remote schema ==="
$W d1 execute tokenpulse-rankings --remote --file=schema.sql

echo ""
echo "=== Step 3: deploy worker ==="
DEPLOY_OUT=$($W deploy 2>&1)
echo "$DEPLOY_OUT"
WORKER_URL=$(echo "$DEPLOY_OUT" | grep -oE 'https://[a-zA-Z0-9.-]+\.workers\.dev' | head -1)

echo ""
echo "============================================"
echo "  Deployed:  $WORKER_URL"
echo "============================================"
echo ""
echo "Final step — add this to config.json (next to \"share\"):"
echo "  \"ranking\": { \"enabled\": true, \"url\": \"$WORKER_URL\" }"
