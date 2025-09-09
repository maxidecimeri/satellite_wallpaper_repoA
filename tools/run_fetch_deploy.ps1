# run_fetch_deploy.ps1
param(
  [switch]$VerboseTail   # when run manually, show live log tail
)

$ErrorActionPreference = "Stop"
$PSStyle.OutputRendering = "PlainText"

# --- Resolve repo and venv ---
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPy = Join-Path $Repo "satellite-wallpaper-env\Scripts\python.exe"
$Activate = Join-Path $Repo "satellite-wallpaper-env\Scripts\activate.ps1"  # exists on new venvs; fallback to .bat if needed

if (-not (Test-Path $VenvPy)) {
  Write-Error "[FATAL] Expected venv python at $VenvPy"
}

# --- Elevation check ---
$curr = [Security.Principal.WindowsIdentity]::GetCurrent()
$princ = New-Object Security.Principal.WindowsPrincipal($curr)
if (-not $princ.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
  # Relaunch elevated in PS7
  $args = @("-NoProfile","-ExecutionPolicy","Bypass","-File", $MyInvocation.MyCommand.Path)
  if ($VerboseTail) { $args += "-VerboseTail" }
  Start-Process pwsh -Verb RunAs -ArgumentList $args -WorkingDirectory $Repo
  exit
}

# --- Logging ---
$logs = Join-Path $Repo "logs"
if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }
$ts = (Get-Date).ToString("yyyyMMdd_HHmmss")
$log = Join-Path $logs "run-$ts.log"
"REPO=$Repo" | Out-File -FilePath $log -Encoding utf8
"PYEXE=$VenvPy" | Out-File -FilePath $log -Append -Encoding utf8

# --- Optional: activate venv for module resolution in child procs
if (Test-Path $Activate) {
  . $Activate 2>$null
} else {
  # older venvs only have activate.bat; modules still load via venv python path
}

# --- Helper: run a step and log/echo
function Invoke-Step([string]$Title, [string]$Script) {
  "$Title" | Tee-Object -FilePath $log -Append | Out-Host
  & $VenvPy $Script *>> $log
  if ($LASTEXITCODE -ne 0) {
    "[$Title] FAILED. See $log" | Tee-Object -FilePath $log -Append | Out-Host
    exit $LASTEXITCODE
  }
}

# --- HEADLESS default (opt-out by setting HEADLESS=0 in environment) ---
if (-not $env:HEADLESS) { $env:HEADLESS = "1" }

# --- Run steps ---
Set-Location $Repo
# sanity: required files
$required = @("working_fetcher.py","deploy-wallpaper.py","companion_selector.py","views_config.json","projects.json")
$missing = $required | Where-Object { -not (Test-Path (Join-Path $Repo $_)) }
if ($missing) {
  "Missing: $($missing -join ', ')." | Tee-Object -FilePath $log -Append | Out-Host
  exit 1
}

Invoke-Step "[1/3] Fetching..."  "working_fetcher.py"
Invoke-Step "[2/3] Deploying..." "deploy-wallpaper.py"
Invoke-Step "[3/3] Companions..." "companion_selector.py"

"[OK] Finished. Log: $log" | Tee-Object -FilePath $log -Append | Out-Host

# --- Interactive tail option ---
if ($VerboseTail) {
  "`n--- tail ---" | Out-Host
  Get-Content $log -Wait -Tail 50
}
