#!/usr/bin/env bash
# fph PoC-0a — local SearXNG instance.
#
# Plain `docker run`, not docker-compose: this colima docker context has no
# `docker compose` plugin and no standalone `docker-compose` binary installed
# (`docker compose up -d` failed with "unknown shorthand flag: 'd'", i.e. it
# fell through to the base docker CLI). A `run` script needs nothing extra.
#
# Usage:
#   ./run.sh start   # bring the instance up on :8080
#   ./run.sh stop    # stop and remove the container
#   ./run.sh logs    # follow logs
set -euo pipefail
cd "$(dirname "$0")"

NAME="fph-searxng-poc0"
PORT="8080"

case "${1:-start}" in
  start)
    docker run -d \
      --name "$NAME" \
      -p "${PORT}:8080" \
      -v "$(pwd)/settings.yml:/etc/searxng/settings.yml:ro" \
      -e "SEARXNG_BASE_URL=http://localhost:${PORT}/" \
      -e "SEARXNG_SECRET=poc0-local-only-not-for-production" \
      --restart unless-stopped \
      searxng/searxng:latest
    echo "started: http://localhost:${PORT}"
    ;;
  stop)
    docker stop "$NAME" && docker rm "$NAME"
    ;;
  logs)
    docker logs -f "$NAME"
    ;;
  *)
    echo "usage: $0 {start|stop|logs}" >&2
    exit 1
    ;;
esac
