#!/usr/bin/env bash
# SafeTrace container entrypoint.
#
# Usage:
#   ui                       → launch the Streamlit UI (default)
#   ingest FILE [FILE ...]   → run main.py ingest
#   query "TEXT"             → run main.py query
#   bash                     → drop into a shell
set -euo pipefail

cd /app

case "${1:-ui}" in
  ui)
    shift || true
    # `maxUploadSize` / `maxMessageSize` are in MB. Default Streamlit caps are
    # 200 MB; we lift them to 51 200 MB (50 GB) so large videos can be uploaded.
    # Override via STREAMLIT_SERVER_MAX_UPLOAD_SIZE / _MESSAGE_SIZE.
    exec streamlit run frontend/app.py \
        --server.address "${STREAMLIT_SERVER_ADDRESS:-0.0.0.0}" \
        --server.port "${STREAMLIT_SERVER_PORT:-8501}" \
        --server.maxUploadSize "${STREAMLIT_SERVER_MAX_UPLOAD_SIZE:-51200}" \
        --server.maxMessageSize "${STREAMLIT_SERVER_MAX_MESSAGE_SIZE:-51200}" \
        --server.headless true "$@"
    ;;
  ingest|query)
    exec python main.py "$@"
    ;;
  bash|sh)
    exec /bin/bash
    ;;
  *)
    exec "$@"
    ;;
esac
