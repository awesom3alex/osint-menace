#!/bin/sh
set -eu
python -c 'import workspace_store; workspace_store.recover()'
exec gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 4 --timeout 240 app:app
