#!/usr/bin/env bash
# Approximate word count for Lancet submission (body text only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAIN="$ROOT/main.tex"

if command -v texcount >/dev/null 2>&1; then
  echo "=== texcount summary (main.tex) ==="
  texcount -inc -sum "$MAIN"
else
  echo "texcount not installed. Rough count from LaTeX source (includes commands):"
  # Strip comments and common commands; very approximate.
  words=$(grep -v '^%' "$MAIN" | sed 's/\\[a-zA-Z*]*{[^}]*}//g' | wc -w)
  echo "Approximate words in main.tex source: $words"
  echo "Install texcount for accurate counts: apt-get install texlive-extra-utils"
fi

echo ""
echo "Lancet Digital Health Article target: <=3500 words (main text)"
echo "Abstract target: <=300 words (structured, five headings)"
