#!/usr/bin/env bash
# Run: bash tests/test_ci_window_check.sh
set -u
S=scripts/ci_window_check.sh; fail=0
check() { got=$(bash "$S" "$2" 2026-10-27 2026-12-26 "$3"); [ "$got" = "run=$1" ] && echo "ok   $2 $3 -> $got" || { echo "FAIL $2 $3 -> $got (want run=$1)"; fail=1; }; }
check false schedule 2026-10-26
check true  schedule 2026-10-27
check true  schedule 2026-11-30
check true  schedule 2026-12-26
check false schedule 2026-12-27
check true  workflow_dispatch 2026-10-26
check true  workflow_dispatch 2027-01-05
exit $fail
