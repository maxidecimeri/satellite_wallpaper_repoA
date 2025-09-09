# refresh_we.ps1 — refresh ONE WE project on ONE monitor (no reshuffle); supports array or dict projects.json
param(
  [string]$Key = "",          # e.g. "GOES-19_East_752W_Full_Disk_GeoColor_CIRA"
  [int]$Monitor = -2          # -2 => read from runtime_config.defaults.live_monitor_index
)

$ErrorActionPreference = "Stop"

$Repo     = Split-Path -Parent $MyInvocation.MyCommand.Path
$WeDir    = "C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine"
$Exe64    = Join-Path $WeDir "wallpaper64.exe"
$Launcher = Join-Path $WeDir "launcher.exe"
$Projects = Join-Path $Repo "projects.json"
$Runtime  = Join-Path $Repo "runtime_config.json"

if (!(Test-Path $Exe64))   { throw "Wallpaper Engine not found at: $Exe64" }
if (!(Test-Path $Projects)) { throw "Missing projects.json at: $Projects" }
if (!(Test-Path $Runtime))  { throw "Missing runtime_config.json at: $Runtime" }

if (-not (Get-Process -Name "wallpaper64" -ErrorAction SilentlyContinue)) {
  Start-Process $Launcher -ArgumentList "-run wallpaper64.exe -nobrowse" -WindowStyle Hidden
  Start-Sleep -Seconds 3
}

# Load configs
$raw = Get-Content $Projects -Raw | ConvertFrom-Json
$rc  = Get-Content $Runtime  -Raw | ConvertFrom-Json

# Normalize projects.json to a hashtable: name -> path
$projMap = @{}
if ($raw -is [System.Collections.IEnumerable] -and -not ($raw -is [hashtable])) {
  foreach ($e in $raw) {
    if ($e.view_name_base -and $e.project_path) { $projMap[$e.view_name_base] = $e.project_path }
  }
} else {
  # dict shape
  foreach ($p in $raw.PSObject.Properties) {
    $name = $p.Name
    $path = $raw.$name.project_path
    if ($name -and $path) { $projMap[$name] = $path }
  }
}
if ($projMap.Count -eq 0) { throw "projects.json has no usable entries (need view_name_base/project_path)." }

# Monitor index (from runtime_config.defaults.live_monitor_index unless explicitly provided)
if ($Monitor -eq -2) {
  try { $Monitor = [int]$rc.defaults.live_monitor_index } catch { $Monitor = 0 }
}

# Determine which key to refresh
if ([string]::IsNullOrWhiteSpace($Key)) {
  $geo = $projMap.Keys | Where-Object { $_ -match "GeoColor" } | Select-Object -First 1
  $Key = if ($geo) { $geo } else { $projMap.Keys | Select-Object -First 1 }
}

if (-not $projMap.ContainsKey($Key)) {
  $list = ($projMap.GetEnumerator() | ForEach-Object { "$($_.Key) => $($_.Value)" }) -join "`n"
  throw "Key '$Key' not found. Available:`n$list"
}

$projPath = $projMap[$Key]
if ([string]::IsNullOrWhiteSpace($projPath)) {
  throw "projects.json has no project_path for '$Key'."
}

$pj = Join-Path $projPath "project.json"
if (!(Test-Path $pj)) {
  throw "project.json not found under '$projPath'. Expected: $pj"
}

# Do NOT close globally. Just (re)open the selected project on the explicit monitor.
& $Exe64 -control openWallpaper -file $pj -monitor $Monitor | Out-Null

# Verify
$active = & $Exe64 -control getWallpaper -monitor $Monitor 2>$null
Write-Host ("[OK] Refreshed key '{0}' on monitor {1}:" -f $Key, $Monitor)
Write-Host ("  {0}" -f $pj)
Write-Host ("  Active now => {0}" -f $active)
