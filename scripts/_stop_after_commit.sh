#!/usr/bin/env bash
cd "d:/New folder (2)/Rag_workbench"
PY="D:/New folder (2)/Rag_workbench/.venv/Scripts/python.exe"
while true; do
  if grep -aq "Stored .* chunks for" embed_additional_annual.stdout.log; then
    "$PY" -c "import psutil;[p.kill() for p in psutil.process_iter(['name','cmdline']) if p.info['name']=='python.exe' and p.info['cmdline'] and any(str(c).endswith('embed_additional.py') for c in p.info['cmdline'])]"
    echo "WATCHER: ACLS committed -> killed ingestion at $(date +%T)"
    break
  fi
  sleep 15
done
