#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-$ROOT_DIR/knowledge}"
WORKER_API_URL="${WORKER_API_URL:-http://localhost:8010}"
UPLOAD_ENDPOINT="${UPLOAD_ENDPOINT:-$WORKER_API_URL/dummy/documents}"
CURL_BIN="${CURL_BIN:-curl}"

if [[ ! -d "$KNOWLEDGE_DIR" ]]; then
  echo "knowledge directory not found: $KNOWLEDGE_DIR" >&2
  exit 1
fi

if ! command -v "$CURL_BIN" >/dev/null 2>&1; then
  echo "curl binary not found: $CURL_BIN" >&2
  exit 1
fi

total=0
indexed=0
failed=0
skipped=0

is_supported_file() {
  local path="$1"
  local suffix="${path##*.}"
  if [[ "$path" != *.* ]]; then
    return 1
  fi

  suffix="$(printf '%s' "$suffix" | tr '[:upper:]' '[:lower:]')"

  case "$suffix" in
    md|txt|rst|html|htm|json|yaml|yml|toml|log|pdf|doc|docx|rtf|odt|pptx|xlsx|py|c|cc|cpp|cxx|h|hpp|js|ts|go|java|sql|sh|jpg|jpeg|png|webp|tif|tiff|svg|drawio|puml|plantuml|mmd)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

while IFS= read -r -d '' file_path; do
  relative_path="${file_path#$KNOWLEDGE_DIR/}"

  if ! is_supported_file "$file_path"; then
    skipped=$((skipped + 1))
    echo "skipping unsupported file: $relative_path"
    continue
  fi

  total=$((total + 1))

  echo "[$total] uploading $relative_path"
  if "$CURL_BIN" --silent --show-error --fail \
    -X POST "$UPLOAD_ENDPOINT" \
    -F "file=@$file_path" \
    -F "relative_path=$relative_path" \
    -F "force=true" >/dev/null; then
    indexed=$((indexed + 1))
  else
    failed=$((failed + 1))
    echo "failed: $relative_path" >&2
  fi
done < <(find "$KNOWLEDGE_DIR" -type f -print0)

echo "completed: total=$total indexed=$indexed failed=$failed skipped=$skipped"

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi
