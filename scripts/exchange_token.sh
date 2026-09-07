#!/usr/bin/env bash
#
# Exchanges a short-lived Instagram token for a 60-day one, and explains in plain
# English what went wrong when the exchange fails.
#
# Values are read from the tty and passed to curl via stdin, so nothing lands in
# your shell history or in `ps` output.
#
# Usage:  ./scripts/exchange_token.sh

set -euo pipefail

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

echo "Exchange a short-lived Instagram token for a 60-day one."
echo
echo "Before you start, confirm all three:"
echo "  1. The secret below is the INSTAGRAM app secret (Use cases -> API setup"
echo "     with Instagram login), NOT the app secret under App settings -> Basic."
echo "  2. You generated the short-lived token AFTER the last app-secret reset."
echo "  3. You generated it within the last hour."
echo

read -rsp "Instagram app secret: " APP_SECRET < /dev/tty; echo
read -rsp "Short-lived access token: " SHORT_TOKEN < /dev/tty; echo

# Trim accidental whitespace/newlines from pasting - a common cause of failure.
APP_SECRET="$(printf '%s' "$APP_SECRET" | tr -d '[:space:]')"
SHORT_TOKEN="$(printf '%s' "$SHORT_TOKEN" | tr -d '[:space:]')"

echo
echo "app secret:  ${#APP_SECRET} chars (expected 32)"
echo "short token: ${#SHORT_TOKEN} chars (expected 100+)"
echo

RESPONSE="$(curl -sS --config - <<CURLCFG
url = "https://graph.instagram.com/access_token"
get
data-urlencode = "grant_type=ig_exchange_token"
data-urlencode = "client_secret=${APP_SECRET}"
data-urlencode = "access_token=${SHORT_TOKEN}"
CURLCFG
)"

printf '%s' "$RESPONSE" | python3 -c '
import json, sys

RAW = sys.stdin.read()
try:
    data = json.loads(RAW)
except ValueError:
    sys.exit(f"Unexpected response from Instagram:\n{RAW[:400]}")

if "access_token" in data:
    days = int(data.get("expires_in", 0)) // 86400
    print(f"SUCCESS - long-lived token valid for about {days} days.\n")
    print("Store it now (it will not be shown again):\n")
    print(data["access_token"])
    sys.exit(0)

err = data.get("error") or {}
message = err.get("message", "") or str(data)
low = message.lower()

if "client secret" in low:
    cause = """The app secret is wrong.

  Most likely you used the app secret from App settings -> Basic. That is the
  Facebook app secret; this endpoint only accepts the INSTAGRAM app secret.

  Find it at: Use cases -> Manage messaging & content on Instagram ->
  API setup with Instagram login. It sits directly right of "Instagram app ID",
  behind a "Show" button.

  If you reset that secret recently, the short-lived token you generated BEFORE
  the reset is also dead - generate a new one after copying the new secret."""
elif "expired" in low or "session" in low:
    cause = """The short-lived token has expired.

  These last about an hour. Go back to API setup with Instagram login ->
  Generate access tokens, click "Generate token" again, and rerun this
  immediately."""
elif "decrypt" in low or "malformed" in low or "cannot parse" in low:
    cause = """The token does not belong to this app.

  The token and the app secret must come from the same Meta app. Copy both from
  the same "API setup with Instagram login" page."""
elif "oauth" in low or "invalid" in low:
    cause = """The token was rejected.

  Usually this means the Instagram Tester invite was never accepted. Check
  Instagram -> Settings -> Apps and websites -> Tester invites, accept it, then
  generate a fresh token."""
else:
    cause = "  See the message above; nothing was stored."

print(f"FAILED: {message}\n")
print(cause)
sys.exit(1)
'
