$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$specPath = Join-Path $projectRoot "MegidoOCR2Excel.spec"
$executablePath = Join-Path $projectRoot "dist\MegidoOCR2Excel\MegidoOCR2Excel.exe"
$smokeReportPath = Join-Path $projectRoot "build\packaging-smoke.json"

Push-Location $projectRoot
try {
    uv sync --group dev
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE."
    }

    uv run pyinstaller --noconfirm --clean $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
        throw "onedir executable was not created: $executablePath"
    }

    Remove-Item -LiteralPath $smokeReportPath -Force -ErrorAction SilentlyContinue
    $smokeProcess = Start-Process `
        -FilePath $executablePath `
        -ArgumentList @(
            "--packaging-smoke-test",
            ('"{0}"' -f $smokeReportPath)
        ) `
        -Wait `
        -PassThru
    if ($smokeProcess.ExitCode -ne 0) {
        throw "Packaged dependency smoke test failed with exit code $($smokeProcess.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $smokeReportPath -PathType Leaf)) {
        throw "Packaged dependency smoke report was not created."
    }
    $smokeReport = Get-Content -LiteralPath $smokeReportPath -Raw | ConvertFrom-Json
    if (-not $smokeReport.ok -or -not $smokeReport.frozen) {
        throw "Packaged dependency smoke test did not run from the frozen executable."
    }

    $bundle = Get-ChildItem -LiteralPath (Split-Path $executablePath) -Recurse -File
    $bundleSize = ($bundle | Measure-Object -Property Length -Sum).Sum
    $hash = Get-FileHash -LiteralPath $executablePath -Algorithm SHA256

    [pscustomobject]@{
        Executable = $executablePath
        Files = $bundle.Count
        SizeMiB = [math]::Round($bundleSize / 1MB, 1)
        SHA256 = $hash.Hash
        Paddle = $smokeReport.paddle
        PaddleOCR = $smokeReport.paddleocr
        Frozen = $smokeReport.frozen
    } | Format-List
}
finally {
    Pop-Location
}
