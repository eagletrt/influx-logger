#!/usr/bin/env bash
set -e

# 1. Run yapf code formatting
echo "🧹 Running yapf auto-formatter..."
yapf --in-place --parallel --recursive src/*

# 2. Run pylint and verify score >= 9.8
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

# Compare score against 9.8 threshold using Python
PASSED=$(python3 -c "import sys; print(1 if float(sys.argv[1]) >= 9.8 else 0)" "$SCORE")

if [ "$PASSED" -eq 1 ]; then
    echo "✅ Pylint score is $SCORE/10 (Threshold >= 9.8)."
    exit 0
else
    echo "❌ Commit rejected: Pylint score ($SCORE) is below 9.8 threshold."
    exit 1
fi
