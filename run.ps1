param([string]$Python = 'python', [switch]$Study, [string]$Output = 'results/latest')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& $Python -I -S run_validation.py --out $Output
if ($LASTEXITCODE -ne 0) { throw 'Voice validation failed' }
if ($Study) {
    & $Python -I -S study.py --out ('results/study_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    if ($LASTEXITCODE -ne 0) { throw 'Study failed' }
}
