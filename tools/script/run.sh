#!/bin/sh
mkdir -p ./cache
docker start influx-logger || docker run --mount=type=bind,src=$(pwd)/config.json,target=/app/config.json,readonly --mount=type=bind,src=./cache,target=/app/cache --name=influx-logger influx-logger:latest
