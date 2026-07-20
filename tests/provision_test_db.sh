#!/usr/bin/env bash
# Provisions a dedicated, disposable test database (nirikshan_test) on the
# same MySQL server the dev stack already uses - completely separate from
# the real "nirikshan" database, so running the test suite can never touch
# real data. Applies every migration in migrations/, in the same numeric
# order the real `migrate` docker-compose service uses, so the test schema
# is identical to production.
#
# Usage: ./tests/provision_test_db.sh   (run from the repo root, or anywhere)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MYSQL_PWD_VAL="$(grep MYSQL_ROOT_PASSWORD .env | cut -d= -f2)"
TEST_DB="${TEST_DB_NAME:-nirikshan_test}"

DB_APP_USER="$(grep '^DB_USER=' .env | cut -d= -f2)"

echo "[provision] dropping + recreating ${TEST_DB} ..."
docker compose exec -T -e MYSQL_PWD="$MYSQL_PWD_VAL" mysql mysql -u root -e "
DROP DATABASE IF EXISTS ${TEST_DB};
CREATE DATABASE ${TEST_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON ${TEST_DB}.* TO '${DB_APP_USER}'@'%';
FLUSH PRIVILEGES;
"

echo "[provision] applying migrations..."
for f in $(ls migrations/*.sql | sort -V); do
  echo "  -> $(basename "$f")"
  docker compose exec -T -e MYSQL_PWD="$MYSQL_PWD_VAL" mysql mysql -u root "${TEST_DB}" < "$f"
done

echo "[provision] done - ${TEST_DB} is ready."
