#!/usr/bin/env bash
#
# Start FinAlly. Idempotent: running it twice leaves one container.
#
# Builds only when the image is missing or --build is passed. A start script
# that rebuilt every time would turn a five-second launch into a two-minute one
# and hide the fact that nothing changed.
set -euo pipefail

# Image, container, volume and port are overridable so a verification run — or a
# second instance — can exist beside a user's running container instead of
# fighting it for the name. The defaults are the documented ones.
IMAGE="${IMAGE:-finally:latest}"
CONTAINER="${CONTAINER:-finally}"
VOLUME="${VOLUME:-finally-data}"
PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

build=false
[[ "${1:-}" == "--build" ]] && build=true

if [[ "$build" == true ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building $IMAGE ..."
  docker build -t "$IMAGE" "$ROOT"
fi

# Already up? Usually say so and stop — but not blindly, and this is the branch
# that used to lie.
#
# It fires *after* the build above, so `--build` against a running container
# rebuilt the image, printed "already running", exited 0, and went on serving the
# OLD container. A success message over a no-op. That is how a build predating
# the DNS-rebinding guard served this machine for four days, and it is the trap
# CP21 could only describe.
#
# `status=running` is load-bearing: `docker ps -q` also lists a container in
# `restarting`, so a crash-looping container — reachable in normal use, since
# docker-compose.yml ships `restart: unless-stopped` — would otherwise be
# reported as "already running" while it served nothing.
if [ -n "$(docker ps --quiet --filter status=running --filter "name=^/${CONTAINER}$")" ]; then
  # Compare IDENTITY, not timestamps. A rebuild that is a pure cache hit
  # legitimately produces the same image ID, and there is genuinely nothing to
  # do in that case; a "created at" comparison would restart the container on
  # every --build for no reason, which is how a correct guard becomes one people
  # route around.
  running_image="$(docker inspect --format '{{.Image}}' "$CONTAINER" 2>/dev/null || true)"
  target_image="$(docker image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null || true)"

  # `-n` first, and it is not belt-and-braces. Both substitutions end in
  # `|| true`, so if BOTH inspects fail they are both empty, empty equals empty,
  # and the script would print "it is the current image" over a state it never
  # managed to read — the exact defect class this checkpoint exists to close,
  # reintroduced inside the fix for it.
  if [ -n "$running_image" ] && [ "$running_image" = "$target_image" ]; then
    echo "FinAlly is already running at http://localhost:${PORT}"
    echo "  and it is the current image."
    exit 0
  fi

  # Different image. Without --build the user did not ask for the new one, so
  # keep the historic five-second no-op and say why it is worth knowing.
  if [ "$build" != true ]; then
    echo "FinAlly is already running at http://localhost:${PORT}"
    echo "  Note: it is not running the current ${IMAGE}."
    echo "  To serve the current build: ./scripts/start_mac.sh --build"
    exit 0
  fi

  # They passed --build and the running container is on something else. Serving
  # the old one is the defect. The named volume is not touched, so the portfolio
  # survives the restart — which is the only reason doing this without asking is
  # acceptable.
  echo "FinAlly is running a different image than the one just built."
  echo "  running: ${running_image}"
  echo "  built:   ${target_image}"
  echo "Restarting to serve the new build ..."
  docker rm --force "$CONTAINER" >/dev/null
fi

# Exited container of the same name: remove the corpse, keep the volume.
if [ -n "$(docker ps --all --quiet --filter "name=^/${CONTAINER}$")" ]; then
  docker rm "$CONTAINER" >/dev/null
fi

env_args=()
if [ -f "$ROOT/.env" ]; then
  env_args+=(--env-file "$ROOT/.env")
else
  echo "No .env found — starting with the market simulator; chat will answer 503."
fi

# Loopback, deliberately. Published as 0.0.0.0 this app — which has no login by
# design — is reachable from the whole LAN with no deliberate port-forward, and
# docker-compose.yml's `restart: unless-stopped` brings that back after every
# reboot. Nothing in the documented workflow changes: the browser, the health
# probe and `open` all use localhost.
#
# (The comment lives here rather than inside the command: a `#` line between
# backslash-continued arguments is not a comment, it is an argument, and
# `bash -n` accepts it happily. This shipped broken for exactly that long.)
docker run --detach \
  --name "$CONTAINER" \
  --volume "${VOLUME}:/app/db" \
  --publish "127.0.0.1:${PORT}:8000" \
  "${env_args[@]}" \
  "$IMAGE" >/dev/null

echo "FinAlly is starting at http://localhost:${PORT}"

# Wait for health before opening a browser, or the user meets a connection
# error and concludes it is broken.
for _ in $(seq 1 40); do
  if curl --silent --fail --output /dev/null "http://localhost:${PORT}/api/health"; then
    command -v open >/dev/null && open "http://localhost:${PORT}" || true
    exit 0
  fi
  sleep 0.5
done

echo "Started, but /api/health did not answer within 20s. Try: docker logs ${CONTAINER}" >&2
exit 1
