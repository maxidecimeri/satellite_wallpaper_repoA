# fetch_only.ps1
param([int]$MinFreshMinutes = 60)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$py   = Join-Path $repo "satellite-wallpaper-env\Scripts\python.exe"
$logs = Join-Path $repo "logs"
if (!(Test-Path $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }
$ts   = (Get-Date).ToString("yyyyMMdd_HHmmss")
$log  = Join-Path $logs "fetch-$ts.log"

Set-Location $repo
"REPO=$repo`nPYEXE=$py`nSTART=$(Get-Date -Format o)" | Out-File -FilePath $log -Encoding utf8

# Freshness guard (ignore 'staging'; only timestamped dirs)
$proc = Join-Path $repo 'processed-images'
$tsPattern = '^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$'
$latestRunDir = Get-ChildItem $proc -Directory -EA SilentlyContinue |
  ForEach-Object {
    Get-ChildItem $_.FullName -Directory -EA SilentlyContinue |
      Where-Object { $_.Name -match $tsPattern } |
      Sort-Object LastWriteTime -Desc | Select-Object -First 1
  } | Sort-Object LastWriteTime -Desc | Select-Object -First 1

if ($latestRunDir) {
  $age = (Get-Date) - $latestRunDir.LastWriteTime
  "[INFO] Newest timestamped run: $($latestRunDir.FullName) ($([int]$age.TotalMinutes) min old)" | Out-File -FilePath $log -Append -Encoding utf8
  if ($age -lt (New-TimeSpan -Minutes $MinFreshMinutes)) {
    "[INFO] Processed images fresh (< $MinFreshMinutes min); skipping fetch." | Out-File -FilePath $log -Append -Encoding utf8
    "[OK] Done. $log"
    exit 0
  }
} else {
  "[INFO] No timestamped runs found; proceeding to fetch." | Out-File -FilePath $log -Append -Encoding utf8
}

$env:HEADLESS = "1"
& $py -V *>> $log
& $py ".\working_fetcher.py" *>> $log
"END=$(Get-Date -Format o)" | Out-File -FilePath $log -Append -Encoding utf8
"[OK] Done. $log"
