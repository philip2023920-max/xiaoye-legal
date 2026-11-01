#!/usr/bin/env bash
# capture_keys.sh - run on your own machine. Keys never pass through chat.
# Usage: bash tools/capture_keys.sh [.env]
# - input is hidden while typing
# - same key is overwritten, not duplicated; press Enter to keep/skip
set -e
ENV_FILE="${1:-.env}"
touch "$ENV_FILE"
for KEY in ANTHROPIC_API_KEY OPENAI_API_KEY DEEPSEEK_API_KEY; do
  current=$(grep -E "^$KEY=." "$ENV_FILE" | cut -d= -f2- || true)
  if [ -n "$current" ]; then hint="already set, Enter to keep"; else hint="Enter to skip"; fi
  read -r -s -p "$KEY ($hint): " val; echo
  if [ -n "$val" ]; then
    grep -vE "^$KEY=" "$ENV_FILE" > "$ENV_FILE.tmp" || true
    mv "$ENV_FILE.tmp" "$ENV_FILE"
    printf '%s=%s\n' "$KEY" "$val" >> "$ENV_FILE"
    echo "  saved $KEY"
  fi
done
chmod 600 "$ENV_FILE"
echo "done: $ENV_FILE"
