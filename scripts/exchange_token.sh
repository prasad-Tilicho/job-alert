#!/usr/bin/env bash
# Thin wrapper so the documented path keeps working.
exec python3 "$(cd "$(dirname "$0")" && pwd)/exchange_token.py"
