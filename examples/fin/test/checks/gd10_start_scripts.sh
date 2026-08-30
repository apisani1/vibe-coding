#!/usr/bin/env bash
#
# GD10 — the start scripts do not report success over a no-op.
#
# Committed as a script rather than described in prose, because the overseer had
# to reconstruct it from the verification plan in order to check CP22's work,
# and a check nobody can re-run is a check that silently stops being true. That
# is this project's own most-repeated failure, recorded eleven times.
#
#   ./test/checks/gd10_start_scripts.sh          # from the repo root
#
# It stubs `docker` on PATH and asserts on WHICH DOCKER VERBS RAN, not on the
# message — a script that printed the right sentence and restarted anyway must
# fail. No real container, no daemon, no network.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"

cat > "$WORK/bin/docker" <<'STUB'
#!/usr/bin/env bash
# Stateful on purpose. A stub where `rm` does not remove anything makes the
# script's later corpse-check fire a second `docker rm`, and the count then
# measures the stub rather than the script. First version of this file asserted
# rm=1 and observed rm=2 for exactly that reason — the stub was the thing under
# test without meaning to be.
echo "docker $*" >> "$STUB_LOG"
[ -f "$STUB_LOG.removed" ] && STUB_RUNNING=""
case "$1 $2" in
  "image inspect") [ "$3" = "--format" ] && echo "$STUB_IMG_ID"; exit 0 ;;
  "inspect --format") [ -n "$STUB_RUNNING" ] && echo "$STUB_RUN_IMAGE"; exit 0 ;;
esac
case "$1" in
  ps)  [ -n "$STUB_RUNNING" ] && echo "cid123"; exit 0 ;;
  rm)  : > "$STUB_LOG.removed"; exit 0 ;;
  build|run) exit 0 ;;
esac
exit 0
STUB
printf '#!/usr/bin/env bash\nexit 0\n' > "$WORK/bin/curl"
printf '#!/usr/bin/env bash\nexit 0\n' > "$WORK/bin/open"
chmod +x "$WORK/bin/"*

fails=0
check() {  # name expect_rm expect_run flag running run_image img_id
  local name="$1" want_rm="$2" want_run="$3" flag="$4"
  export STUB_LOG="$WORK/log" STUB_RUNNING="$5" STUB_RUN_IMAGE="$6" STUB_IMG_ID="$7"
  : > "$STUB_LOG"; rm -f "$STUB_LOG.removed"
  local out; out=$(PATH="$WORK/bin:$PATH" "$ROOT/scripts/start_mac.sh" $flag 2>&1)
  local got_rm got_run
  got_rm=$(grep -c 'docker rm' "$STUB_LOG"); got_run=$(grep -c 'docker run' "$STUB_LOG")
  if [ "$got_rm" = "$want_rm" ] && [ "$got_run" = "$want_run" ]; then
    printf 'PASS  %s\n' "$name"
  else
    printf 'FAIL  %s — expected rm=%s run=%s, got rm=%s run=%s\n' "$name" "$want_rm" "$want_run" "$got_rm" "$got_run"
    printf '%s\n' "$out" | sed 's/^/        /'
    fails=$((fails + 1))
  fi
}

echo "GD10 — scripts/start_mac.sh against a stubbed docker"
check "running + --build + different image -> recreates"  1 1 --build 1 sha256:OLD  sha256:NEW
check "running + --build + same image      -> no action"  0 0 --build 1 sha256:SAME sha256:SAME
check "running, no --build                 -> no action"  0 0 ""      1 sha256:OLD  sha256:NEW
check "not running                         -> starts"     0 1 --build ""  ""        sha256:NEW
# Both inspects fail: must NOT claim the image is current. With --build the only
# safe reading of "we could not tell" is to recreate.
check "both inspects fail + --build        -> recreates"  1 1 --build 1 ""          ""

if [ "$fails" -eq 0 ]; then echo "GD10: PASS"; else echo "GD10: $fails FAILED"; exit 1; fi
