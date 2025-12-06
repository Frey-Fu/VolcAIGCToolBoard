#!/usr/bin/env bash
set -euo pipefail
uvicorn main_server:app --host 0.0.0.0 --port 8000 --workers 2