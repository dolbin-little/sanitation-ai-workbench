param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath 'data/public-benchmarks/manifest.json')) {
        & (Join-Path $PSScriptRoot 'download-public-benchmarks.ps1')
        & $Python scripts/prepare_public_benchmarks.py
        if ($LASTEXITCODE -ne 0) { throw 'Dataset preparation failed.' }
    }
    $commands = @(
        @('-m','unittest','tests.test_public_benchmark','-v'),
        @('scripts/verify_public_references.py'),
        @('scripts/run_public_benchmarks.py','--seeds','30','--budget','2','--iterations','200','--workers','8'),
        @('scripts/public_budget_sensitivity.py'),
        @('scripts/public_capacity_diagnosis.py'),
        @('scripts/audit_public_results.py'),
        @('scripts/plot_public_benchmarks.py'),
        @('scripts/summarize_public_benchmarks.py')
    )
    foreach ($arguments in $commands) {
        & $Python @arguments
        if ($LASTEXITCODE -ne 0) { throw ('Experiment step failed: ' + ($arguments -join ' ')) }
    }
} finally {
    Pop-Location
}
