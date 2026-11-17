$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$projectPython = if (Test-Path -LiteralPath $bundledPython) { $bundledPython } else { 'python' }
& $projectPython -m pip install --target .vendor -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
