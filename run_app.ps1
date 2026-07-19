$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectRoot
try {
    uv run --no-project --python 3.12 -- python launcher.py
    if ($LASTEXITCODE -ne 0) {
        throw "Launcher failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
