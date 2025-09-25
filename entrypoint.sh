#!/bin/bash
set -e

# Parse tham số: chỉ hỗ trợ kiểu --conf 'JSON_STRING'
CONF_JSON=""

while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --conf)
      shift
      CONF_JSON="$1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [[ -n "$CONF_JSON" ]]; then
    echo "[ENTRYPOINT] Starting crawler with config: $CONF_JSON"
    python -m app.crawl_request --conf "$CONF_JSON" &
else
    echo "[ENTRYPOINT] No config provided, skip crawler"
fi

# Chạy Stop/Health API
PORT=${API_PORT:-9222}
exec uvicorn app.server:app --host 0.0.0.0 --port $PORT

