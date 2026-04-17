#!/usr/bin/env bash
set -e

docker compose build --quiet
docker compose run --rm app pytest --cov=app --cov-report=term-missing -v "$@"
