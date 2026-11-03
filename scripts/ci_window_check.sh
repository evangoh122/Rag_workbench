#!/usr/bin/env bash
# Decide whether a scheduled run falls inside the allowed date window.
# Usage: ci_window_check.sh <event_name> <start YYYY-MM-DD> <end YYYY-MM-DD> [today YYYY-MM-DD]
# Prints "run=true" or "run=false". Only `schedule` events are gated; every other
# event (workflow_dispatch, ...) always runs. Dates are UTC and inclusive.
set -euo pipefail
event="$1"; start="$2"; end="$3"; today="${4:-$(date -u +%F)}"
if [ "$event" != "schedule" ]; then echo "run=true"; exit 0; fi
# ISO dates compare correctly as strings.
if [[ "$today" < "$start" || "$today" > "$end" ]]; then echo "run=false"; else echo "run=true"; fi
