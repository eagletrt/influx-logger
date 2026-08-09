#!/bin/sh
docker run --mount=type=bind,src=$(pwd)/config.json,target=/app/config.json,readonly --mount=type=bind,src=./cache,target=/app/cache influx-logger:latest
