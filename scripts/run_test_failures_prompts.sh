#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROMPTS_FILE="${PROMPTS_FILE:-data/prompts/test_failures_prompts_100.txt}"

if [[ ! -f "${PROMPTS_FILE}" ]]; then
  echo "ERROR: prompts file not found: ${PROMPTS_FILE}"
  exit 1
fi

if ! python -c "import pytest" >/dev/null 2>&1; then
  echo "ERROR: pytest is not installed in current Python environment."
  exit 1
fi

mkdir -p runtime/logs/prompt_runs

run_no=0
while IFS= read -r prompt || [[ -n "$prompt" ]]; do
  prompt="${prompt#"${prompt%%[![:space:]]*}"}"
  prompt="${prompt%"${prompt##*[![:space:]]}"}"
  if [[ -z "${prompt}" || "${prompt}" == \#* ]]; then
    continue
  fi
  run_no=$((run_no + 1))
  echo "===== RUN ${run_no} ====="
  echo "PROMPT: ${prompt}"
  TEST_FAILURES_PROMPT="$prompt" python -m pytest -q tests/test_failures.py | tee "runtime/logs/prompt_runs/test_failures_prompt_${run_no}.log"
  echo
  echo "Combined log: runtime/logs/combined_test-failures.jsonl"
  echo
  sleep 1
done < "${PROMPTS_FILE}"
