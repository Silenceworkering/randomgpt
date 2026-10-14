#!/bin/sh
# Run on the dedicated host with a clone of this repository and a configured .env.
set -eu
cd "$(dirname "$0")/.."
# flock serializes deployments; failing build never stops the running bot.
exec 9>/tmp/dedlainych-deploy.lock
flock -n 9 || exit 1
git pull --ff-only
docker compose build bot
docker compose exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U dedlainych -d dedlainych -Fc' > /tmp/dedlainych-predeploy.dump
mkdir -p backups
chmod 700 backups
mv /tmp/dedlainych-predeploy.dump backups/predeploy.dump
chmod 600 backups/predeploy.dump
docker compose stop bot
# Migrations must be backward compatible. Failed migration leaves the bot stopped for inspection.
docker compose run --rm --no-deps bot alembic upgrade head
docker compose up -d --no-build bot backup
docker compose ps
