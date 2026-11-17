$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$targetRoot = Join-Path $projectRoot 'data/public-benchmarks'
New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
$sources = @{
    solomon = 'https://www.sintef.no/globalassets/project/top/vrptw/solomon/solomon-100.zip'
    gdb = 'https://www.uv.es/~belengue/carp/gdb.zip'
    bccm = 'https://www.uv.es/~belengue/carp/bccm.zip'
    kshs = 'https://www.uv.es/~belengue/carp/kshs.zip'
    eglese = 'https://www.uv.es/~belengue/carp/eglese.zip'
    tdcarp = 'https://codeload.github.com/vidalt/HGS-TDCARP/zip/9638127242a9ad36ecaf9335c8df540cad6575fc'
}
foreach ($name in $sources.Keys) {
    $archive = Join-Path $targetRoot "$name.zip"
    # Keep the archived experiment inputs immutable when rerunning acquisition.
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -UseBasicParsing -Uri $sources[$name] -OutFile $archive -TimeoutSec 300
    }
    if (-not (Test-Path -LiteralPath (Join-Path $targetRoot $name))) {
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $targetRoot $name)
    }
}
$sources | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $targetRoot 'sources.json')
$referencePage = Join-Path $targetRoot 'solomon-bks.html'
if (-not (Test-Path -LiteralPath $referencePage)) {
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.sintef.no/projectweb/top/vrptw/100-customers/' -OutFile $referencePage -TimeoutSec 60
}
$referenceFolder = Join-Path $targetRoot 'bks-solutions'
New-Item -ItemType Directory -Force -Path $referenceFolder | Out-Null
$html = Get-Content -LiteralPath $referencePage -Raw -Encoding UTF8
$matches = [regex]::Matches($html, 'href="([^"]+\.txt)"[^>]*>\s*((?:c|r|rc)\d{3}b?)\s*<', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
if ($matches.Count -ne 56) { throw 'Expected 56 official reference links; website format needs review.' }
foreach ($match in $matches) {
    $name = $match.Groups[2].Value.ToLower().TrimEnd('b')
    $relative = $match.Groups[1].Value
    if (-not $relative.StartsWith('/') -or $relative.StartsWith('//')) { throw 'Unexpected reference URL.' }
    $destination = Join-Path $referenceFolder "$name.txt"
    if (-not (Test-Path -LiteralPath $destination)) {
        Invoke-WebRequest -UseBasicParsing -Uri ('https://www.sintef.no' + $relative) -OutFile $destination -TimeoutSec 60
    }
}
Write-Output 'Run scripts/prepare_public_benchmarks.py to unpack TDSP and verify all 203 inputs.'
