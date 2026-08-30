#!/usr/bin/env bash
#
# Stop FinAlly.
#
# **It never removes the volume.** That is the single most destructive thing
# this repo could do: the named volume is the user's entire portfolio, and a
# stop script that tidied it away would be indistinguishable from data loss.
# Check GD2 asserts the volume survives.
set -euo pipefail

# Image, container, volume and port are overridable so a verification run — or a
# second instance — can exist beside a user's running container instead of
# fighting it for the name. The defaults are the documented ones.
CONTAINER="${CONTAINER:-finally}"
VOLUME="${VOLUME:-finally-data}"

if [ -z "$(docker ps --all --quiet --filter "name=^/${CONTAINER}$")" ]; then
  echo "FinAlly is not running."
  exit 0
fi

docker stop "$CONTAINER" >/dev/null
docker rm "$CONTAINER" >/dev/null
echo "FinAlly stopped. Your portfolio is kept in the '${VOLUME}' volume."
echo "To erase it deliberately: docker volume rm ${VOLUME}"
