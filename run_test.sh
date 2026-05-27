#!/bin/bash

finished=1
hard_killed=1

# if Ctrl+C (SIGINT) arrives, mark as hard killed so loop can exit
trap 'hard_killed=0' INT
while [ "$finished" -ne 0 ] && [ "$hard_killed" -ne 0 ]; do
    timeout -s KILL 30m python3 -m src.main config.json
    finished=$?
done
