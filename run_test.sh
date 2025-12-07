#!/usr/bin/env bash
set -euo pipefail
BASE_URL=${BASE_URL:-http://localhost:8000}
LOG_DIR=${LOG_DIR:-tests/logs}

# 使用已激活环境的python与pip
PY=python
mkdir -p "$LOG_DIR"

run_case() {
  name="$1"; cmd="$2"; log="$LOG_DIR/$name.log"
  echo "$name test case [RUN] "
  if bash -lc "$cmd" > "$log" 2>&1; then
    echo "$name test case [OK] passed"
  else
    echo "$name test case [FAIL] (详见 $log)"
  fi
}

run_case "ref_i2v_module" "$PY tests/ref_i2v_module/run_test.py \"$BASE_URL\""
run_case "v2t_module" "$PY tests/v2t_module/run_test.py"
run_case "tosutil" "$PY tests/tosutil/run_test.py"
run_case "i2v_and_t2v_module" "$PY tests/i2v_and_t2v_module/run_test.py \"$BASE_URL\""
