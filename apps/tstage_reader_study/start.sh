#!/usr/bin/env bash
# Start a local static-file server for the tstage_reader_study app.
# Default port 8765.  Usage:  ./start.sh [port]
PORT="${1:-8765}"
cd "$(dirname "$0")"
echo "Serving tstage_reader_study on http://127.0.0.1:${PORT}/"
echo "Pass 1 (no AI):    http://127.0.0.1:${PORT}/?reader=YOUR_ID&pass=1"
echo "Pass 2 (with AI):  http://127.0.0.1:${PORT}/?reader=YOUR_ID&pass=2"
exec python3 -m http.server "${PORT}" --bind 127.0.0.1
