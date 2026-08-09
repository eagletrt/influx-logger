#!/bin/sh
docker build --secret id=logger-config,src=$(pwd)/config.json -f Dockerfile.influx-logger.yml -t influx-logger:latest .
