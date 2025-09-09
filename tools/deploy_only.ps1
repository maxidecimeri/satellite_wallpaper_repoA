# deploy_only.ps1 (PS7)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$py   = Join-Path $repo "satellite-wallpaper-env\Scripts\python.exe"
$logs = Join-Path $repo "logs"
if (!(Test-Path $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }
$ts   = (Get-Date).ToString("yyyyMMdd_HHmmss")
$log  = Join-Path $logs "deploy-$ts.log"

Set-Location $repo
"REPO=$repo`nPYEXE=$py" | Out-File -FilePath $log -Encoding utf8

# Deploy frames
& $py -V                    *>> $log
& $py ".\deploy-wallpaper.py"        *>> $log

# Companions (static wallpapers)
& $py ".\companion_selector.py"      *>> $log

# Select which satellite view to display on the fixed monitor
$selector = Join-Path $repo 'select_sat_view.ps1'
if (Test-Path $selector) {
  & pwsh -NoProfile -ExecutionPolicy Bypass -File $selector *>> $log
} else {
  "[WARN] select_sat_view.ps1 not found; skipping view selection." | Out-File -FilePath $log -Append -Encoding utf8
}

"[OK] Done. $log"
