$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$projectPython = $null
if (Test-Path -LiteralPath $bundledPython) { $projectPython = $bundledPython }
elseif (Get-Command py -ErrorAction SilentlyContinue) { $projectPython = 'py' }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $projectPython = 'python' }
else { throw 'Python 3.10+ is required. Install Python, then run this script again.' }
Write-Host 'Open http://127.0.0.1:8766 in your browser. Keep this window open.'
& $projectPython server.py

