#!/usr/bin/env bash
set -e

THRESHOLD=9.95

# 1. Run ruff linter
echo "🐶 Running ruff check..."
ruff check src/

# 2. Run yapf code formatting
echo "🧹 Running yapf auto-formatter..."
yapf --in-place --parallel --recursive src/*

# 3. Run pylint and verify score >= THRESHOLD
echo "🔍 Running pylint..."

set +e
PYLINT_OUTPUT=$(pylint -r y src)
set -e

echo "$PYLINT_OUTPUT"

# Extract score from output
SCORE=$(echo "$PYLINT_OUTPUT" | awk -F'rated at ' '/rated at/ {split($2, a, "/"); print a[1]}')

if [ -z "$SCORE" ]; then
    echo "❌ Error: Could not determine pylint score."
    exit 1
fi

# Compare score against THRESHOLD using Python
PASSED=$(python3 -c "import sys; print(1 if float(sys.argv[1]) >= float(sys.argv[2]) else 0)" "$SCORE" "$THRESHOLD")

if [ "$PASSED" -eq 1 ]; then
    echo "✅ Pylint score is $SCORE/10 (Threshold >= $THRESHOLD)."
    exit 0
else
    echo "❌ Commit rejected: Pylint score ($SCORE) is below $THRESHOLD threshold."
    exit 1
fi
