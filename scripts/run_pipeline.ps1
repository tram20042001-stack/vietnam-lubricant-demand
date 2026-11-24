# Runs the update pipeline: checks NSO for new releases and rebuilds outputs only if a source changed.
# Used by the Windows scheduled task (see register_scheduled_task.ps1) and safe to run by hand.
param([switch]$Force)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logDir = Join-Path $root "reports\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("pipeline_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))
$flag = if ($Force) { "--force" } else { "" }

# Python logs to stderr; run through cmd so PowerShell 5.1 does not treat log lines as errors.
cmd /c "`"$root\.venv\Scripts\python.exe`" -X utf8 -m vnlube.pipeline $flag >> `"$log`" 2>&1"
$code = $LASTEXITCODE
Get-Content $log -Tail 1
exit $code
