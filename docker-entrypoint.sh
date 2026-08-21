#!/bin/sh
set -e

echo "==> Waiting for database connectivity..."
python << END
import sys
import time
import os
import psycopg

db_host = os.environ.get("DB_HOST", "db")
db_port = os.environ.get("DB_PORT", "5432")
db_name = os.environ.get("DB_NAME", "artikate_db")
db_user = os.environ.get("DB_USER", "artikate_user")
db_password = os.environ.get("DB_PASSWORD", "artikate_password")

conn_str = f"host={db_host} port={db_port} dbname={db_name} user={db_user} password={db_password}"

for i in range(30):
    try:
        conn = psycopg.connect(conn_str)
        conn.close()
        print("==> Database is available and responding!")
        sys.exit(0)
    except Exception as e:
        print(f"==> Waiting for database ({i+1}/30)... ({e})")
        time.sleep(1)

print("==> Database connection timeout.")
sys.exit(1)
END

echo "==> Applying database migrations..."
python manage.py migrate --noinput

echo "==> Starting application process..."
exec "$@"
