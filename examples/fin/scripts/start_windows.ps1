# Start FinAlly. Idempotent: running it twice leaves one container.
# Mirrors scripts/start_mac.sh command for command.
$ErrorActionPreference = 'Stop'

# Image, container, volume and port are overridable so a verification run - or a
# second instance - can exist beside a user's running container. Defaults are
# the documented ones.
$Image     = if ($env:IMAGE) { $env:IMAGE } else { 'finally:latest' }
$Container = if ($env:CONTAINER) { $env:CONTAINER } else { 'finally' }
$Volume    = if ($env:VOLUME) { $env:VOLUME } else { 'finally-data' }
$Port      = if ($env:PORT) { $env:PORT } else { '8000' }
$Root      = Split-Path -Parent $PSScriptRoot

$Build = $args -contains '--build'

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    Write-Host "Building $Image ..."
    docker build -t $Image $Root
}

# Already up? Usually say so and stop - but not blindly, and this is the branch
# that used to lie. It fires *after* the build above, so --build against a
# running container rebuilt the image, printed "already running", exited 0, and
# went on serving the OLD container: a success message over a no-op.
#
# `status=running` is load-bearing and was missing here while the header claimed
# this file mirrors start_mac.sh: `docker ps -q` also lists a container in
# `restarting`, and docker-compose.yml ships `restart: unless-stopped`, so a
# crash-looping container reported as "already running" while serving nothing.
$running = docker ps --quiet --filter status=running --filter "name=^/$Container$"
if ($running) {
    # Compare IDENTITY, not timestamps. A rebuild that is a pure cache hit
    # legitimately yields the same image id and there is nothing to do; a
    # "created at" comparison would restart on every --build for no reason.
    $runningImage = docker inspect --format '{{.Image}}' $Container 2>$null
    $targetImage  = docker image inspect --format '{{.Id}}' $Image 2>$null

    # Non-empty first: $null -eq $null is True, so two failed inspects would
    # report "it is the current image" over a state never read.
    if ($runningImage -and $runningImage -eq $targetImage) {
        Write-Host "FinAlly is already running at http://localhost:$Port"
        Write-Host '  and it is the current image.'
        exit 0
    }

    # Different image, and no --build: the user did not ask for the new one, so
    # keep the historic no-op and say why it is worth knowing.
    if (-not $Build) {
        Write-Host "FinAlly is already running at http://localhost:$Port"
        Write-Host "  Note: it is not running the current $Image."
        Write-Host '  To serve the current build: .\scripts\start_windows.ps1 --build'
        exit 0
    }

    # They passed --build and the running container is on something else.
    # Serving the old one is the defect. The named volume is untouched, so the
    # portfolio survives the restart.
    Write-Host 'FinAlly is running a different image than the one just built.'
    Write-Host "  running: $runningImage"
    Write-Host "  built:   $targetImage"
    Write-Host 'Restarting to serve the new build ...'
    docker rm --force $Container | Out-Null
}

# Exited container of the same name: remove the corpse, keep the volume.
$existing = docker ps --all --quiet --filter "name=^/$Container$"
if ($existing) { docker rm $Container | Out-Null }

$envArgs = @()
if (Test-Path (Join-Path $Root '.env')) {
    $envArgs = @('--env-file', (Join-Path $Root '.env'))
} else {
    Write-Host 'No .env found - starting with the market simulator; chat will answer 503.'
}

# Loopback, deliberately - see scripts/start_mac.sh for why.
docker run --detach --name $Container --volume "${Volume}:/app/db" --publish "127.0.0.1:${Port}:8000" @envArgs $Image | Out-Null
Write-Host "FinAlly is starting at http://localhost:$Port"

# Wait for health before opening a browser, or the user meets a connection error.
foreach ($attempt in 1..40) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$Port/api/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Start-Process "http://localhost:$Port"
            exit 0
        }
        # A non-200 answer is still "not ready" — sleep, or this spins 40 times
        # with no delay and gives up in milliseconds. The shell pair sleeps on
        # every miss; this branch did not.
        Start-Sleep -Milliseconds 500
    } catch { Start-Sleep -Milliseconds 500 }
}

Write-Error "Started, but /api/health did not answer within 20s. Try: docker logs $Container"
exit 1
