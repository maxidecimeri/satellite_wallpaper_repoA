# select_sat_view.ps1 — choose which satellite project to display, without touching runtime_config.json

$ErrorActionPreference = "Stop"
$Repo     = Split-Path -Parent $MyInvocation.MyCommand.Path
$WeDir    = "C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine"
$Exe64    = Join-Path $WeDir "wallpaper64.exe"
$Launcher = Join-Path $WeDir "launcher.exe"
$Projects = Join-Path $Repo "projects.json"
$Runtime  = Join-Path $Repo "runtime_config.json"
$Selector = Join-Path $Repo "sat_selector.json"
$State    = Join-Path $Repo "last_active_view.txt"

if (!(Test-Path $Exe64))   { throw "Wallpaper Engine not found at: $Exe64" }
if (!(Test-Path $Projects)) { throw "Missing projects.json at: $Projects" }
if (!(Test-Path $Runtime))  { throw "Missing runtime_config.json at: $Runtime" }

# Ensure WE is running
if (-not (Get-Process -Name "wallpaper64" -ErrorAction SilentlyContinue)) {
  Start-Process $Launcher -ArgumentList "-run wallpaper64.exe -nobrowse" -WindowStyle Hidden
  Start-Sleep -Seconds 3
}

# Load configs
$projMap = Get-Content $Projects -Raw | ConvertFrom-Json
$rcfg    = Get-Content $Runtime  -Raw | ConvertFrom-Json

# Monitor index comes from runtime_config.json defaults.live_monitor_index
$monitor = 0
try {
  $monitor = [int]$rcfg.defaults.live_monitor_index
} catch { $monitor = 0 }

# Selector (optional)
if (Test-Path $Selector) {
  $scfg = Get-Content $Selector -Raw | ConvertFrom-Json
} else {
  # sensible default if sat_selector.json absent
  $scfg = [pscustomobject]@{
    mode        = "manual"
    active_view = "GOES-19_East_752W_Full_Disk_GeoColor_CIRA"
    rotate_order= @(
      "GOES-19_East_752W_Full_Disk_GeoColor_CIRA",
      "GOES-19_East_752W_Full_Disk_Band_13_103_mm_Clean_IR_Longwave_Window",
      "GOES-19_East_752W_Full_Disk_Airmass_EUMETSAT"
    )
    rules = [pscustomobject]@{
      day_view   = "GOES-19_East_752W_Full_Disk_GeoColor_CIRA"
      night_view = "GOES-19_East_752W_Full_Disk_Band_13_103_mm_Clean_IR_Longwave_Window"
      twilight_view = "GOES-19_East_752W_Full_Disk_Airmass_EUMETSAT"
      night_hours    = @(19,5)
      twilight_hours = @(5,7,17,19)
    }
  }
}

function Pick-Manual { $scfg.active_view }

function Pick-Rotate {
  $order = @($scfg.rotate_order)
  if (-not $order -or $order.Count -eq 0) { return $null }
  $last = (Test-Path $State) ? (Get-Content $State -Raw).Trim() : $null
  if (-not $last) { return $order[0] }
  $i = $order.IndexOf($last)
  if ($i -lt 0) { return $order[0] }
  return $order[($i+1) % $order.Count]
}

function Pick-Rules {
  $r = $scfg.rules
  if (-not $r) { return $null }
  $h = (Get-Date).Hour
  $nh0,$nh1 = $r.night_hours
  $tw = @($r.twilight_hours)
  if ($h -ge $nh0 -or $h -lt $nh1) { return $r.night_view }
  if (($h -ge $tw[0] -and $h -lt $tw[1]) -or ($h -ge $tw[2] -and $h -lt $tw[3])) { return $r.twilight_view }
  return $r.day_view
}

$mode = ($scfg.mode ?? "manual").ToLower()
$key = switch ($mode) {
  "rotate" { Pick-Rotate }
  "rules"  { Pick-Rules  }
  default  { Pick-Manual }
}
if (-not $key) { throw "No active view determined (mode=$mode)." }

# Map key -> project.json
$entry = $projMap.$key
if ($null -eq $entry) { throw "Key '$key' not found in projects.json." }
$projPath = $entry.project_path
if (-not (Test-Path $projPath)) { throw "project_path not found: $projPath" }
$pj = Join-Path $projPath "project.json"
if (-not (Test-Path $pj)) { throw "project.json missing under $projPath" }

# Open only this project on the satellite monitor (no global close, no reshuffle)
& $Exe64 -control openWallpaper -file $pj -monitor $monitor | Out-Null

# Persist selection for rotate mode
$key | Out-File $State -Encoding ascii -NoNewline

Write-Host "[OK] Active view on monitor $monitor:"
Write-Host "  $key => $pj"
