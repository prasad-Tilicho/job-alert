#!/usr/bin/env bash
#
# Exchanges a short-lived Instagram token for a 60-day one and stores every
# secret the publishing workflow needs.
#
# Nothing is echoed to the terminal, written to disk, or passed as a command-line
# argument, so no secret lands in your shell history or in `ps` output.
#
# Usage:  ./scripts/setup_secrets.sh [owner/repo]

set -euo pipefail

REPO="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
echo "Configuring secrets for: $REPO"
echo

command -v gh >/dev/null || { echo "gh CLI is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

prompt_secret() {  # prompt_secret VARNAME "Label"
  local __var="$1" __label="$2" __value=""
  while [ -z "$__value" ]; do
    read -rsp "$__label: " __value < /dev/tty
    echo
    [ -n "$__value" ] || echo "  (cannot be empty)"
  done
  printf -v "$__var" '%s' "$__value"
}

prompt_optional() { # prompt_optional VARNAME "Label" - blank is allowed
  local __var="$1" __label="$2" __value=""
  read -rsp "$__label (Enter to skip): " __value < /dev/tty
  echo
  printf -v "$__var" '%s' "$__value"
}

prompt_plain() {   # prompt_plain VARNAME "Label"
  local __var="$1" __label="$2" __value=""
  while [ -z "$__value" ]; do
    read -rp "$__label: " __value < /dev/tty
    [ -n "$__value" ] || echo "  (cannot be empty)"
  done
  printf -v "$__var" '%s' "$__value"
}

echo "--- Instagram ---"
prompt_plain  IG_USER_ID  "Instagram account ID (from 'Add account', NOT the app ID)"
prompt_secret APP_SECRET  "Instagram app secret"
prompt_secret SHORT_TOKEN "Short-lived access token"

# curl reads its config from stdin so the secrets never appear in argv.
RESPONSE="$(curl -sS --config - <<CURLCFG
url = "https://graph.instagram.com/access_token"
get
data-urlencode = "grant_type=ig_exchange_token"
data-urlencode = "client_secret=${APP_SECRET}"
data-urlencode = "access_token=${SHORT_TOKEN}"
CURLCFG
)"

LONG_TOKEN="$(printf '%s' "$RESPONSE" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except ValueError:
    sys.exit("could not parse the response from Instagram")
if "access_token" not in data:
    message = (data.get("error") or {}).get("message", data)
    sys.exit(f"token exchange failed: {message}")
days = int(data.get("expires_in", 0)) // 86400
print(data["access_token"])
print(f"exchanged successfully; valid for about {days} days", file=sys.stderr)
')"

# The Instagram token is the time-critical part - it is already exchanged and safe
# above. The rest can be skipped now and added by re-running this script later.
echo
echo "--- Adzuna (free key; without it there is no Indian job coverage) ---"
prompt_optional ADZUNA_APP_ID  "Adzuna app ID"
prompt_optional ADZUNA_APP_KEY "Adzuna app key"

echo
echo "--- GitHub ---"
prompt_optional GH_PAT "Fine-grained PAT (Contents: write, Secrets: write)"

echo
printf '%s' "$IG_USER_ID" | gh secret set IG_USER_ID      --repo "$REPO"
printf '%s' "$LONG_TOKEN" | gh secret set IG_ACCESS_TOKEN --repo "$REPO"

skipped=()
set_optional() {  # set_optional NAME VALUE
  if [ -n "$2" ]; then
    printf '%s' "$2" | gh secret set "$1" --repo "$REPO"
  else
    skipped+=("$1")
  fi
}
set_optional ADZUNA_APP_ID  "$ADZUNA_APP_ID"
set_optional ADZUNA_APP_KEY "$ADZUNA_APP_KEY"
set_optional GH_PAT         "$GH_PAT"

if [ ${#skipped[@]} -gt 0 ]; then
  echo
  echo "Skipped (re-run this script once you have them): ${skipped[*]}"
fi

echo
echo "Done. Secrets now set:"
gh secret list --repo "$REPO"
echo
echo "Next, set your handle and start conservatively:"
echo "  gh variable set IG_HANDLE --body '@yourhandle' --repo $REPO"
echo "  gh variable set MAX_POSTS_PER_RUN --body '1' --repo $REPO"
