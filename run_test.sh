#!/bin/bash

# Restart src.main every 30 minutes.
while true; do
    python3 -m src.main config.json &
    pid=$!
    sleep 1800
    kill "$pid"
    wait "$pid"
done

