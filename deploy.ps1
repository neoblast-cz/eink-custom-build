# Push local commits to GitHub, then pull + restart on the Pi.
$ErrorActionPreference = "Stop"

$PiHost = if ($env:PI_HOST) { $env:PI_HOST } else { "192.168.1.52" }
$PiUser = if ($env:PI_USER) { $env:PI_USER } else { "neoblast" }

$branch = (git rev-parse --abbrev-ref HEAD).Trim()

$status = git status --porcelain
if ($status) {
    Write-Host "Uncommitted changes present -- commit or stash before deploying:"
    git status --short
    exit 1
}

Write-Host "=== Pushing $branch to GitHub ==="
git push origin $branch
if (-not $?) { exit 1 }

Write-Host "=== Deploying to $PiUser@$PiHost ==="
ssh -t "$PiUser@$PiHost" "cd ~/einkpi && git pull && sudo systemctl restart einkpi"
if (-not $?) { exit 1 }

Write-Host "=== Done. Web UI: http://$PiHost:8080/ ==="
