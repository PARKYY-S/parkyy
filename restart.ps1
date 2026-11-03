# Stop EVERY old PARKYY backend - including the hidden "server" copies uvicorn leaves behind,
# which kept answering with old code (that's why "my hearing needs a restart" never went away).
function Stop-ParkyyBackend {
  # 1) the uvicorn launcher(s) + whatever owns port 8000
  $all = Get-CimInstance Win32_Process -Filter "Name='python.exe'"
  $ids = @()
  try { $ids += (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess } catch {}
  $ids += ($all | Where-Object { $_.CommandLine -like '*uvicorn*main:app*' -or $_.CommandLine -like '*main:app*' }).ProcessId
  $alive = @{}; foreach ($p in $all) { $alive[[int]$p.ProcessId] = $true }
  # 2) the hidden worker copies uvicorn spawns ("multiprocessing spawn_main ... parent_pid=N"). They keep serving
  #    OLD code after their parent dies, so kill workers whose parent is ours OR whose parent is already gone.
  foreach ($p in $all) {
    if ($p.CommandLine -match 'spawn_main.*parent_pid=(\d+)') {
      $parent = [int]$Matches[1]
      if (($ids -contains $parent) -or -not $alive.ContainsKey($parent) -or $p.ExecutablePath -like '*\parkyy\*') { $ids += $p.ProcessId }
    }
  }
  foreach ($id in ($ids | Where-Object { $_ -and $_ -ne 0 } | Select-Object -Unique)) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if ($p -and $p.Name -eq 'python.exe') { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
  }
  Start-Sleep -Seconds 2
  # 3) still something on port 8000? kill that too (it's an old PARKYY that didn't die)
  try {
    foreach ($o in (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess) {
      $p = Get-CimInstance Win32_Process -Filter "ProcessId=$o" -ErrorAction SilentlyContinue
      if ($p -and $p.Name -eq 'python.exe') { Stop-Process -Id $o -Force -ErrorAction SilentlyContinue }
    }
  } catch {}
  Start-Sleep -Seconds 1
}

# Restart only PARKYY (never other apps like the Claude desktop app)
Get-CimInstance Win32_Process -Filter "Name='electron.exe'" | Where-Object { $_.ExecutablePath -like '*\parkyy\*' -or $_.CommandLine -like '*parkyy*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Stop-ParkyyBackend

# Saud's rule: nothing on C: - temp files + pip cache live in PARKYY's folder on D:
$env:TEMP = Join-Path $PSScriptRoot 'data\tmp'; $env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $env:TEMP 'pip-cache'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

# Make sure PARKYY's hearing + TV parts are installed (one time; skipped once they're there)
$py = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
foreach ($m in @(@('sounddevice','sounddevice'), @('vosk','vosk'), @('aiowebostv','aiowebostv'), @('psutil','psutil'), @('pypdf','pypdf'))) {
  & $py -c "import $($m[0])" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing $($m[1]) for PARKYY (one time)..."
    & $py -m pip install $m[1] --disable-pip-version-check -q --no-cache-dir
  }
}

# Free the memory used by the offline brain unless PARKYY is set to use it (it reloads by itself when needed)
try {
  $mode = (Get-Content (Join-Path $PSScriptRoot 'brains.json') -Raw | ConvertFrom-Json).mode
  $lms = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
  if ($mode -ne 'local' -and (Test-Path $lms)) { & $lms unload --all 2>$null | Out-Null }
} catch {}
Start-Sleep -Seconds 1
$env:PARKYY_LAN = '1'
Set-Location "$PSScriptRoot\desktop"
Start-Process 'node_modules\electron\dist\electron.exe' -ArgumentList '.'
