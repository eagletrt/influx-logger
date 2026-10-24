#!/usr/bin/env bash
set -euo pipefail

THRESHOLD=9.95

echo "Running ruff check..."
ruff check

echo "Running yapf..."
yapf --in-place --parallel --recursive $(find . -type f -name "*.py" ! -path "./.venv/*")

echo "Running pylint..."
set +e
PYLINT_OUTPUT=$(PYTHONPATH="$(pwd)${PYTHONPATH:+:$PYTHONPATH}" pylint \
    $(git -c safe.directory="$(pwd)" ls-files '*.py'))
set -e
echo "$PYLINT_OUTPUT"
# Extract score from output
SCORE=$(echo "$PYLINT_OUTPUT" | awk -F'rated at ' '/rated at/ {split($2, a, "/"); print a[1]}')
if [ -z "$SCORE" ]; then
    echo "Error: Could not determine pylint score."
    exit 1
fi
# Compare score against THRESHOLD using Python
PASSED=$(python3 -c "import sys; print(1 if float(sys.argv[1]) >= float(sys.argv[2]) else 0)" "$SCORE" "$THRESHOLD")
if [ "$PASSED" -ne 1 ]; then
    echo "Commit rejected: Pylint score ($SCORE) is below $THRESHOLD threshold."
    exit 1
fi
