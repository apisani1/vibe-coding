# Stop FinAlly.
#
# It never removes the volume — the named volume is the user's entire
# portfolio. Mirrors scripts/stop_mac.sh.
$ErrorActionPreference = 'Stop'

# Image, container, volume and port are overridable so a verification run - or a
# second instance - can exist beside a user's running container. Defaults are
# the documented ones.
$Container = if ($env:CONTAINER) { $env:CONTAINER } else { 'finally' }
$Volume    = if ($env:VOLUME) { $env:VOLUME } else { 'finally-data' }

$existing = docker ps --all --quiet --filter "name=^/$Container$"
if (-not $existing) {
    Write-Host 'FinAlly is not running.'
    exit 0
}

docker stop $Container | Out-Null
docker rm $Container | Out-Null
Write-Host "FinAlly stopped. Your portfolio is kept in the '$Volume' volume."
Write-Host "To erase it deliberately: docker volume rm $Volume"
