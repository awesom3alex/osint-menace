#!/bin/sh
set -eu
python -c 'import workspace_store; workspace_store.recover(); workspace_store.recover_research()'
exec gunicorn --config gunicorn.conf.py --bind 0.0.0.0:8080 --workers 1 --threads 4 --timeout 240 app:app
