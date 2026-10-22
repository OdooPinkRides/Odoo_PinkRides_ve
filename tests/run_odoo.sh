#!/usr/bin/env bash
set -euo pipefail
: "${ODOO_SOURCE:?Set ODOO_SOURCE to the official Odoo 19 source directory}"
: "${PGPASSWORD:?Set the disposable CI database password}"
mkdir -p tests/artifacts
python "$ODOO_SOURCE/odoo-bin" \
  --addons-path="$PWD,$ODOO_SOURCE/addons,$ODOO_SOURCE/odoo/addons" \
  --db_host=127.0.0.1 --db_port=5432 --db_user=odoo --db_password="$PGPASSWORD" \
  --database=pink_routemanager_test --without-demo=all \
  --init=pink_routemanager --test-enable --test-tags=/pink_routemanager \
  --stop-after-init --no-http --workers=0 --max-cron-threads=0 \
  --log-level=test --logfile=tests/artifacts/odoo.log
python tests/check_odoo_log.py tests/artifacts/odoo.log
