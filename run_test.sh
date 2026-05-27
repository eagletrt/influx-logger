#!/bin/bash

# Restart src.index every 30 minutes.
while true; do
    python3 -m src.index config.json &
    pid=$!
    sleep 1800
    kill "$pid"
    wait "$pid"
done

