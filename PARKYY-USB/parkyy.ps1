<#
  PARKYY - portable edition (offline + online).
  Runs from a USB stick on any Windows PC.
    * No internet  -> the offline Hermes brain on the stick (llamafile), starts only when needed.
    * Internet + keys (keys.env) -> free cloud brains (Groq, then Gemini), fast, starts instantly.
    * Cloud down / rate-limited / Wi-Fi drops mid-chat -> falls back to the offline brain by itself.
  Memory lives in memory\ next to this file, so it travels with the stick, and
  syncs with laptop PARKYY.
#>
param([int]$Port = 8080, [switch]$SelfTest)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Api      = "http://127.0.0.1:$Port"
$MemDir   = Join-Path $Root 'memory'
$MemFile  = Join-Path $MemDir 'memory.txt'
$GoneFile = Join-Path $MemDir 'forgotten.txt'
# Laptop PARKYY's folder. Only exists on Saud's laptop; elsewhere sync/import is skipped.
$LaptopMemDir = 'D:\Downloads\parkyy\parkyy\memory'
$LaptopRoot   = Split-Path $LaptopMemDir -Parent
$LaptopEnv    = Join-Path $LaptopRoot '.env'
$LaptopModels = Join-Path $LaptopRoot 'data\models.json'
$KeysFile = Join-Path $Root 'keys.env'
$LogDir   = Join-Path $Root 'logs'
$MaxTurns = 12          # how many recent messages are sent each time
foreach ($d in @($LogDir, $MemDir)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null } }
$LogFile  = Join-Path $LogDir ("chat-" + (Get-Date -Format 'yyyy-MM-dd') + ".txt")
$PetFile  = Join-Path $Root 'pet-state.txt'
# tells the desktop pet (pet.ps1) what PARKYY is doing; harmless if the pet isn't running
function Set-Pet($mode, $text) {
    try { [IO.File]::WriteAllText($PetFile, ($mode + "`t" + ([string]$text -replace "[`r`n`t]+", ' ') + "`t" + [Environment]::TickCount)) } catch { }
}

# Only these (free-tier) keys are ever copied onto the stick. Claude / OpenAI / GitHub keys never are.
$ImportNames = @('GROQ_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'PARKYY_GROQ_MODEL', 'PARKYY_GEMINI_MODEL')

$script:Keys          = @{}
$script:ForceOffline  = $false
$script:CloudDownUntil = [DateTime]::MinValue
$script:LocalProc     = $null
$script:LastBrain     = ''

$SystemPromptBase = @"
You are PARKYY, Saud's own personal AI assistant, a cute little robot who is
growing up with him. You are not a copy of JARVIS. Playful, cutesy and warm, but
straight to the point. Always ask Saud to confirm before doing anything for him.
"@
$OfflineNote = @"
You are running fully offline from a USB drive, so you cannot send
emails, set calendar events, or browse the web right now - say so plainly
instead of pretending. You CAN help with writing, planning, explaining,
code, and drafting things Saud can send later.
"@
$OnlineNote = @"
You are online right now, thinking through a cloud brain. From this USB stick you
can chat, plan, explain, write code and research the web when Saud uses /web.
You still cannot send emails or change his calendar from the stick - draft them
and he sends them from his laptop. Never pretend you did something you did not.
"@

# ---------- memory ----------
function Read-Lines($path) {
    if (Test-Path $path) { return @(Get-Content -Path $path -Encoding UTF8 | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }) }
    return @()
}
function Write-Lines($path, $lines) {
    # UTF-8 with BOM: readable by both this script and laptop PARKYY (Python)
    $enc = New-Object System.Text.UTF8Encoding($true)
    $text = ''
    if (@($lines).Count -gt 0) { $text = (@($lines) -join "`r`n") + "`r`n" }
    [System.IO.File]::WriteAllText($path, $text, $enc)
}
function Get-UniqueLines($lines) {
    $seen = @{}; $out = New-Object System.Collections.ArrayList
    foreach ($l in @($lines)) { $k = $l.ToLowerInvariant(); if (-not $seen.ContainsKey($k)) { $seen[$k] = 1; [void]$out.Add($l) } }
    return @($out)
}
function Get-Memory { return @(Read-Lines $MemFile) }
function Save-Memory($items) { Write-Lines $MemFile (Get-UniqueLines $items) }

# Same rule as laptop PARKYY: union of facts, minus anything forgotten on either side.
function Sync-Memory {
    if (-not (Test-Path $LaptopMemDir)) { return $false }
    try {
        $lapMem  = Join-Path $LaptopMemDir 'memory.txt'
        $lapGone = Join-Path $LaptopMemDir 'forgotten.txt'
        $gone = Get-UniqueLines (@(Read-Lines $GoneFile) + @(Read-Lines $lapGone))
        $goneKeys = @{}; foreach ($g in $gone) { $goneKeys[$g.ToLowerInvariant()] = 1 }
        $merged = @(Get-UniqueLines (@(Read-Lines $MemFile) + @(Read-Lines $lapMem)) | Where-Object { -not $goneKeys.ContainsKey($_.ToLowerInvariant()) })
        foreach ($pair in @(@($MemFile, $GoneFile), @($lapMem, $lapGone))) {
            Write-Lines $pair[0] $merged
            Write-Lines $pair[1] $gone
        }
        $pU = Join-Path $Root 'about-saud.md'; $pL = Join-Path (Split-Path $LaptopMemDir -Parent) 'about-saud.md'
        if ((Test-Path $pL) -and (-not (Test-Path $pU) -or (Get-Item $pL).LastWriteTime -gt (Get-Item $pU).LastWriteTime.AddSeconds(2))) { Copy-Item $pL $pU -Force }
        elseif ((Test-Path $pU) -and (-not (Test-Path $pL) -or (Get-Item $pU).LastWriteTime -gt (Get-Item $pL).LastWriteTime.AddSeconds(2))) { Copy-Item $pU $pL -Force }
        return $true
    } catch { return $false }
}
function Add-Fact($fact) {
    $fact = $fact.Trim()
    Save-Memory (@(Get-Memory) + @($fact))
    Write-Lines $GoneFile @(Read-Lines $GoneFile | Where-Object { $_.ToLowerInvariant() -ne $fact.ToLowerInvariant() })
    [void](Sync-Memory)
}
function Remove-Fact($fact) {
    Save-Memory @(Get-Memory | Where-Object { $_ -ne $fact })
    Write-Lines $GoneFile (Get-UniqueLines (@(Read-Lines $GoneFile) + @($fact)))
    [void](Sync-Memory)
}

function Get-SystemMessage($online) {
    $ast = [DateTime]::UtcNow.AddHours(3).ToString('dddd dd MMMM yyyy, HH:mm')
    $note = $OfflineNote
    if ($online) { $note = $OnlineNote }
    $msg = "$SystemPromptBase`n$note`nRight now it is $ast AST (Saudi Arabia)."
    $profFile = Join-Path $Root 'about-saud.md'
    if (Test-Path $profFile) { $msg += "`n`nWhat you know about Saud (his own words):`n" + (Get-Content $profFile -Raw -Encoding UTF8) }
    $mem = @(Get-Memory)
    if ($mem.Count -gt 0) { $msg += "`n`nThings you remember about Saud:`n" + (($mem | ForEach-Object { "- $_" }) -join "`n") }
    return $msg
}

# ---------- voice (built into Windows, works offline) ----------
$Voice = $null
$VoiceOn = $false
try {
    Add-Type -AssemblyName System.Speech
    $Voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
} catch { $Voice = $null }

# ---------- keys (for the online brains) ----------
function Read-EnvFile($path) {
    $h = @{}
    if (Test-Path $path) {
        foreach ($line in (Get-Content -Path $path -Encoding UTF8)) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
                $v = $Matches[2].Trim([char]34, [char]39)
                if ($v -ne '') { $h[$Matches[1]] = $v }
            }
        }
    }
    return $h
}
function Load-Keys { $script:Keys = Read-EnvFile $KeysFile }

# Copy ONLY the free Groq / Gemini keys from laptop PARKYY onto the stick (asks first).
function Import-LaptopKeys {
    if (-not (Test-Path $LaptopEnv)) { return $false }
    $src = Read-EnvFile $LaptopEnv
    $lines = @()
    foreach ($n in $ImportNames) { if ($src.ContainsKey($n)) { $lines += ($n + '=' + $src[$n]) } }
    # the working model names laptop PARKYY found for each provider
    if (Test-Path $LaptopModels) {
        try {
            $m = (Get-Content $LaptopModels -Raw -Encoding UTF8) | ConvertFrom-Json
            if ($m.groq   -and -not $src.ContainsKey('PARKYY_GROQ_MODEL'))   { $lines += ('PARKYY_GROQ_MODEL='   + $m.groq) }
            if ($m.gemini -and -not $src.ContainsKey('PARKYY_GEMINI_MODEL')) { $lines += ('PARKYY_GEMINI_MODEL=' + $m.gemini) }
        } catch { }
    }
    if (@($lines | Where-Object { $_ -match '_API_KEY=' }).Count -eq 0) { return $false }
    Write-Lines $KeysFile $lines
    Load-Keys
    return $true
}

# Model names change over time (old ones start answering 404). Order of preference: keys.env, the models laptop
# PARKYY last found working (data\models.json), a model PARKYY found itself this session, then built-in defaults.
$script:FoundModel = @{}
function Get-LaptopModel($provider) {
    try { if (Test-Path $LaptopModels) { $m = (Get-Content $LaptopModels -Raw -Encoding UTF8) | ConvertFrom-Json; return [string]$m.$provider } } catch { }
    return ''
}
function Pick-Model($provider, $envName, $default) {
    $k = $script:Keys
    if ($k[$envName]) { return $k[$envName] }
    if ($script:FoundModel[$provider]) { return $script:FoundModel[$provider] }
    $lm = Get-LaptopModel $provider; if ($lm) { return $lm }
    return $default
}
# The provider said "model not found": ask it which models exist and pick a sensible one (like laptop PARKYY does).
function Find-WorkingModel($b) {
    try {
        $base = $b.url -replace '/chat/completions$', ''
        $r = Invoke-WebRequest -Uri ($base + '/models') -Headers @{ Authorization = ('Bearer ' + $b.key) } -UseBasicParsing -TimeoutSec 20
        $ids = @((([Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())) | ConvertFrom-Json).data | ForEach-Object { ([string]$_.id) -replace '^models/', '' })
        $prefs = if ($b.name -eq 'Groq') { @('gpt-oss-120b', 'llama-3.3-70b', 'gpt-oss', 'llama') } else { @('flash-lite', 'flash') }
        foreach ($p in $prefs) {
            $hit = $ids | Where-Object { $_ -like "*$p*" -and $_ -notmatch 'image|tts|audio|embed|vision|guard|whisper|preview-tts|live' } | Select-Object -First 1
            if ($hit) { return $hit }
        }
    } catch { }
    return ''
}
function Get-CloudBrains {
    $k = $script:Keys
    $list = @()
    if ($k['GROQ_API_KEY']) {
        $m = Pick-Model 'groq' 'PARKYY_GROQ_MODEL' 'openai/gpt-oss-120b'
        $list += , @{ name = 'Groq'; url = 'https://api.groq.com/openai/v1/chat/completions'; key = $k['GROQ_API_KEY']; model = $m }
    }
    $gk = $k['GEMINI_API_KEY']; if (-not $gk) { $gk = $k['GOOGLE_API_KEY'] }
    if ($gk) {
        $m = Pick-Model 'gemini' 'PARKYY_GEMINI_MODEL' 'gemini-flash-latest'
        $list += , @{ name = 'Gemini'; url = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'; key = $gk; model = $m }
    }
    return $list
}

# Any HTTP answer (even 401/404) proves there is internet; only "no answer" means offline.
function Test-Online {
    foreach ($u in @('https://api.groq.com', 'https://generativelanguage.googleapis.com', 'https://www.msftconnecttest.com/connecttest.txt')) {
        try { $null = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 4; return $true }
        catch { if ($_.Exception.Response) { return $true } }
    }
    return $false
}

# ---------- offline brain (llamafile on the stick) ----------
function Test-LocalBrain {
    foreach ($path in @('/health', '/v1/models')) {
        try { $r = Invoke-WebRequest -Uri ($Api + $path) -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { return $true } } catch { }
    }
    return $false
}

function Wait-ForBrain {
    Write-Host "Loading PARKYY's offline brain from the USB (first start on a PC can take 3-5 minutes, later starts are faster)" -ForegroundColor DarkCyan
    $started = Get-Date
    for ($i = 0; $i -lt 600; $i++) {
        if (Test-LocalBrain) { Write-Host ""; Write-Host "Offline brain ready." -ForegroundColor Green; return $true }
        # if the brain process died, stop waiting
        if ($i -gt 10 -and -not (Get-Process -Name 'llamafile*' -ErrorAction SilentlyContinue)) {
            Write-Host ""; Write-Host "The brain window closed or crashed." -ForegroundColor Red; return $false
        }
        if ($i % 5 -eq 0) {
            $secs = [int]((Get-Date) - $started).TotalSeconds
            Write-Host ("`r  still loading... {0}s " -f $secs) -NoNewline -ForegroundColor DarkCyan
        }
        Start-Sleep -Seconds 1
    }
    Write-Host ""
    return $false
}

function Start-LocalBrain {
    if (Test-LocalBrain) { return $true }
    $model = Get-ChildItem -Path (Join-Path $Root 'models') -Filter '*.gguf' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    $lf    = Get-ChildItem -Path $Root -Filter 'llamafile*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $lf)    { Write-Host "(offline brain unavailable: no llamafile .exe next to parkyy.ps1)" -ForegroundColor Red; return $false }
    if (-not $model) { Write-Host "(offline brain unavailable: no .gguf model inside the models folder)" -ForegroundColor Red; return $false }
    $argLine = '--server --model "' + $model.FullName + '" --host 127.0.0.1 --port ' + $Port + ' -c 4096'
    $script:LocalProc = Start-Process -FilePath $lf.FullName -ArgumentList $argLine -WindowStyle Minimized -PassThru
    return (Wait-ForBrain)
}

function Stop-LocalBrain {
    try { if ($script:LocalProc -and -not $script:LocalProc.HasExited) { Stop-Process -Id $script:LocalProc.Id -Force } } catch { }
}

function Invoke-Local($messages) {
    $body = @{
        model       = 'local'
        messages    = $messages
        temperature = 0.6
        max_tokens  = 800
    } | ConvertTo-Json -Depth 10
    $bytes = [Text.Encoding]::UTF8.GetBytes($body)
    $resp = Invoke-WebRequest -Uri "$Api/v1/chat/completions" -Method Post `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -UseBasicParsing -TimeoutSec 600
    # decode as UTF-8 explicitly (PowerShell 5.1 guesses wrong otherwise)
    $text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
    $json = $text | ConvertFrom-Json
    return ([string]$json.choices[0].message.content).Trim()
}

# ---------- online brains ----------
function Invoke-Cloud($b, $messages) {
    $body = @{
        model       = $b.model
        messages    = $messages
        temperature = 0.6
        max_tokens  = 900
    } | ConvertTo-Json -Depth 10
    $bytes = [Text.Encoding]::UTF8.GetBytes($body)
    $resp = Invoke-WebRequest -Uri $b.url -Method Post -ContentType 'application/json; charset=utf-8' `
        -Headers @{ Authorization = ('Bearer ' + $b.key) } -Body $bytes -UseBasicParsing -TimeoutSec 45
    $text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
    $json = $text | ConvertFrom-Json
    return ([string]$json.choices[0].message.content).Trim()
}

# One entry point: best available brain, automatic fallbacks. Returns @{ text; brain; online }.
function Invoke-Brain($history, $userOverride) {
    $recentStart = [Math]::Max(0, $history.Count - $MaxTurns)
    $recent = @($history[$recentStart..($history.Count - 1)])
    if ($userOverride) {   # same conversation, but the last user turn carries extra material (web results)
        $recent[$recent.Count - 1] = @{ role = 'user'; content = $userOverride }
    }

    if (-not $script:ForceOffline -and [DateTime]::Now -gt $script:CloudDownUntil) {
        $brains = @(Get-CloudBrains)
        if ($brains.Count -gt 0) {
            $messages = @(@{ role = 'system'; content = (Get-SystemMessage $true) }) + $recent
            foreach ($b in $brains) {
                try {
                    $t = Invoke-Cloud $b $messages
                    if ($t -ne '') { return @{ text = $t; brain = $b.name; online = $true } }
                } catch {
                    $err = $_.Exception.Message
                    if ($err -match '404|not found|does not exist|decommission') {
                        # that model name has been retired - find one that exists and try once more
                        $nm = Find-WorkingModel $b
                        if ($nm -and $nm -ne $b.model) {
                            Write-Host ("(" + $b.name + ": model " + $b.model + " is gone - switching to " + $nm + ")") -ForegroundColor DarkGray
                            $script:FoundModel[$b.name.ToLower()] = $nm; $b['model'] = $nm
                            try { $t = Invoke-Cloud $b $messages; if ($t -ne '') { return @{ text = $t; brain = $b.name; online = $true } } }
                            catch { $err = $_.Exception.Message }
                        }
                    }
                    Write-Host ("(" + $b.name + " didn't answer: " + $err + ")") -ForegroundColor DarkGray
                }
            }
            # every cloud brain failed: probably no Wi-Fi or free limits used up. Don't hammer them for a minute.
            $script:CloudDownUntil = [DateTime]::Now.AddSeconds(60)
            Write-Host "(cloud brains unavailable - switching to the offline brain)" -ForegroundColor Yellow
        }
    }

    if (-not (Test-LocalBrain)) {
        if (-not (Start-LocalBrain)) { throw "No brain is available: no internet/keys and the offline brain could not start." }
    }
    $messages = @(@{ role = 'system'; content = (Get-SystemMessage $false) }) + $recent
    return @{ text = (Invoke-Local $messages); brain = 'Offline Hermes'; online = $false }
}

# ---------- /web : look things up online (DuckDuckGo, falls back to Wikipedia) ----------
function Remove-Html($s) { return ([System.Net.WebUtility]::HtmlDecode(([regex]::Replace([string]$s, '<[^>]+>', ''))).Trim()) }

function Parse-DuckResults($html) {
    $out = @()
    $links = [regex]::Matches($html, 'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', 'Singleline')
    $snips = [regex]::Matches($html, 'class="result__snippet"[^>]*>(.*?)</a>', 'Singleline')
    for ($i = 0; $i -lt [Math]::Min(5, $links.Count); $i++) {
        $href = $links[$i].Groups[1].Value
        if ($href -match 'uddg=([^&"]+)') { $href = [uri]::UnescapeDataString($Matches[1]) }
        elseif ($href.StartsWith('//')) { $href = 'https:' + $href }
        $snip = ''; if ($i -lt $snips.Count) { $snip = Remove-Html $snips[$i].Groups[1].Value }
        $out += , @{ title = (Remove-Html $links[$i].Groups[2].Value); url = $href; snippet = $snip }
    }
    return $out
}

function Search-Web($q) {
    $enc = [uri]::EscapeDataString($q)
    $ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PARKYY-USB'
    try {
        $r = Invoke-WebRequest -Uri ("https://html.duckduckgo.com/html/?q=" + $enc) -UseBasicParsing -TimeoutSec 12 -UserAgent $ua
        $res = @(Parse-DuckResults $r.Content)
        if ($res.Count -gt 0) { return $res }
    } catch { }
    try {
        $r = Invoke-WebRequest -Uri ("https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=" + $enc + "&srlimit=5&format=json") -UseBasicParsing -TimeoutSec 12 -UserAgent $ua
        $j = ([Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())) | ConvertFrom-Json
        $out = @()
        foreach ($h in $j.query.search) {
            $out += , @{ title = [string]$h.title; url = ('https://en.wikipedia.org/wiki/' + ([string]$h.title -replace ' ', '_')); snippet = (Remove-Html $h.snippet) }
        }
        return $out
    } catch { return @() }
}

function Write-Log($who, $text) {
    Add-Content -Path $LogFile -Encoding UTF8 -Value ("[{0}] {1}: {2}" -f (Get-Date -Format 'HH:mm'), $who, $text)
}

function Show-Status {
    $on = Test-Online
    $cloud = @(Get-CloudBrains)
    $names = ($cloud | ForEach-Object { $_.name }) -join ', '
    if ($on)  { Write-Host "  Internet: yes" -ForegroundColor DarkGray } else { Write-Host "  Internet: no" -ForegroundColor DarkGray }
    if ($cloud.Count -gt 0) { Write-Host ("  Cloud brains on this stick: " + $names) -ForegroundColor DarkGray }
    else { Write-Host "  Cloud brains on this stick: none (type /setup-online on your laptop, or put keys in keys.env)" -ForegroundColor DarkGray }
    if ($script:ForceOffline) { Write-Host "  Mode: forced offline (type /online to switch back)" -ForegroundColor DarkGray }
    elseif ($on -and $cloud.Count -gt 0) { Write-Host "  Mode: online (offline brain is the backup)" -ForegroundColor DarkGray }
    else { Write-Host "  Mode: offline" -ForegroundColor DarkGray }
}

function Invoke-SetupOnline {
    if (-not (Test-Path $LaptopEnv)) {
        Write-Host "(I can only copy keys from Saud's laptop. Elsewhere, put GROQ_API_KEY=... and/or GEMINI_API_KEY=... into keys.env next to parkyy.ps1)" -ForegroundColor DarkGray
        return
    }
    Write-Host "This copies ONLY your free Groq and Gemini keys onto this stick (keys.env)." -ForegroundColor Yellow
    Write-Host "If the stick is ever lost, someone could use those keys - you can always revoke them on their websites." -ForegroundColor Yellow
    $a = Read-Host "Copy them now? (y/n)"
    if ($a -match '^(y|yes)$') {
        if (Import-LaptopKeys) { Write-Host ("Done. Online brains ready: " + ((@(Get-CloudBrains) | ForEach-Object { $_.name }) -join ', ')) -ForegroundColor Green }
        else { Write-Host "(no Groq/Gemini keys found in laptop PARKYY's .env)" -ForegroundColor DarkGray }
    } else { Write-Host "(ok, nothing copied)" -ForegroundColor DarkGray }
}

# ---------- main ----------
Clear-Host
Write-Host "==============================================" -ForegroundColor Cyan

# ======================= SELF-TEST (TEST-USB.bat) =======================
# Runs every part of the USB edition for real on this PC and writes logs\usb-selftest.txt.
# Nothing is copied onto the stick: if keys.env is missing, the free Groq/Gemini keys are read from laptop PARKYY
# into memory only for this test.
if ($SelfTest) {
    $Report = Join-Path $LogDir 'usb-selftest.txt'
    $lines = New-Object System.Collections.ArrayList
    function T($name, $ok, $detail) {
        $tag = if ($ok -eq $true) { 'PASS' } elseif ($ok -eq $false) { 'FAIL' } else { 'SKIP' }
        $line = ('{0,-4}  {1,-34} {2}' -f $tag, $name, $detail)
        [void]$lines.Add($line)
        $c = if ($tag -eq 'PASS') { 'Green' } elseif ($tag -eq 'FAIL') { 'Red' } else { 'Yellow' }
        Write-Host $line -ForegroundColor $c
    }
    Write-Host "PARKYY USB self-test - please wait (the offline brain can take a few minutes to load)" -ForegroundColor Cyan
    [void]$lines.Add("PARKYY USB self-test  " + (Get-Date -Format 'yyyy-MM-dd HH:mm') + "  PC: " + $env:COMPUTERNAME + "  stick: " + $Root)
    $os = $null; try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop } catch { }
    if ($os) { [void]$lines.Add(("Windows: {0}  RAM: {1:N1} GB" -f $os.Caption, ($os.TotalVisibleMemorySize / 1MB))) }
    [void]$lines.Add("PowerShell: " + $PSVersionTable.PSVersion)

    # 1. files
    $lf = Get-ChildItem -Path $Root -Filter 'llamafile*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    $gg = Get-ChildItem -Path (Join-Path $Root 'models') -Filter '*.gguf' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    T 'Offline engine (llamafile)' ([bool]$lf) ($(if ($lf) { $lf.Name } else { 'missing' }))
    T 'Offline model (.gguf)' ([bool]$gg) ($(if ($gg) { ('{0} ({1:N2} GB)' -f $gg.Name, ($gg.Length / 1GB)) } else { 'missing' }))
    $petOk = (Test-Path (Join-Path $Root 'pet.ps1')) -and ((Get-ChildItem (Join-Path $Root 'pet\assets') -Filter *.png -ErrorAction SilentlyContinue).Count -ge 11)
    T 'Pet files' $petOk 'pet.ps1 + 11 pictures'

    # 2. offline brain, for real
    $script:ForceOffline = $true
    $h = @(@{ role = 'user'; content = 'This is a quick test. Reply with one short friendly sentence that includes the word OFFLINE.' })
    $t0 = Get-Date
    try { $r = Invoke-Brain $h $null; $secs = [int]((Get-Date) - $t0).TotalSeconds
          T 'Offline brain answers' (($r.brain -eq 'Offline Hermes') -and ($r.text.Length -gt 0)) ("[" + $r.brain + "] in " + $secs + "s: " + ($r.text -replace '\s+', ' ').Substring(0, [Math]::Min(90, $r.text.Length))) }
    catch { T 'Offline brain answers' $false $_.Exception.Message }
    $script:ForceOffline = $false

    # 3. internet + cloud brains
    $net = Test-Online
    T 'Internet detected' $(if ($net) { $true } else { $null }) ($(if ($net) { 'online' } else { 'no internet on this PC right now' }))
    Load-Keys
    $keySrc = 'keys.env on the stick'
    if (@(Get-CloudBrains).Count -eq 0 -and (Test-Path $LaptopEnv)) {
        $src = Read-EnvFile $LaptopEnv; $tmp = @{}
        foreach ($n in $ImportNames) { if ($src.ContainsKey($n)) { $tmp[$n] = $src[$n] } }
        $script:Keys = $tmp; $keySrc = "laptop PARKYY's keys (memory only, nothing written to the stick)"
    }
    $cb = @(Get-CloudBrains)
    $names = (@($cb | ForEach-Object { $_.name }) -join ', ')
    T 'Cloud keys available' ($cb.Count -gt 0) ($names + "  from " + $keySrc)
    if ($net -and $cb.Count -gt 0) {
        $script:CloudDownUntil = [DateTime]::MinValue
        $h = @(@{ role = 'user'; content = 'This is a quick test. Reply with one short sentence that includes the word ONLINE.' })
        $t0 = Get-Date
        try { $r = Invoke-Brain $h $null; $secs = [int]((Get-Date) - $t0).TotalSeconds
              T 'Online brain answers' ($r.online -eq $true) ("[" + $r.brain + "] in " + $secs + "s: " + ($r.text -replace '\s+', ' ').Substring(0, [Math]::Min(90, $r.text.Length))) }
        catch { T 'Online brain answers' $false $_.Exception.Message }
        try { $w = @(Search-Web 'llamafile'); T '/web search' ($w.Count -gt 0) ("" + $w.Count + " results, first: " + $(if ($w.Count) { $w[0].title } else { '-' })) }
        catch { T '/web search' $false $_.Exception.Message }

        # 4. cloud fails mid-chat -> must fall back to the offline brain by itself
        $saved = $script:Keys; $bad = @{}; foreach ($k in $saved.Keys) { $bad[$k] = $saved[$k] }
        foreach ($k in @('GROQ_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY')) { if ($bad.ContainsKey($k)) { $bad[$k] = 'invalid-test-key' } }
        $script:Keys = $bad; $script:CloudDownUntil = [DateTime]::MinValue
        try { $r = Invoke-Brain @(@{ role = 'user'; content = 'Quick test: say hi in five words.' }) $null
              T 'Cloud fails -> falls back offline' ($r.brain -eq 'Offline Hermes') ("answered by [" + $r.brain + "] after the cloud brains were made to fail") }
        catch { T 'Cloud fails -> falls back offline' $false $_.Exception.Message }
        $script:Keys = $saved
    } else {
        T 'Online brain answers' $null 'needs internet + keys'
        T '/web search' $null 'needs internet'
        T 'Cloud fails -> falls back offline' $null 'needs internet + keys'
    }

    # 5. desktop pet
    $petLog = Join-Path $LogDir 'pet.log'
    $before = if (Test-Path $petLog) { (Get-Item $petLog).Length } else { 0 }
    try {
        Remove-Item (Join-Path $Root 'pet-state.txt') -ErrorAction SilentlyContinue
        $pp = Start-Process powershell -ArgumentList ('-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $Root 'pet.ps1') + '" -Root "' + $Root + '"') -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 10
        $alive = -not $pp.HasExited
        $newLog = ''
        if (Test-Path $petLog) { $all = [IO.File]::ReadAllText($petLog); if ($all.Length -gt $before) { $newLog = $all.Substring([int]$before) } }
        $fatal = $newLog -match 'FATAL'
        T 'Pet appears and runs' ($alive -and -not $fatal) ($(if ($fatal) { ($newLog -split "`n" | Where-Object { $_ -match 'FATAL' } | Select-Object -First 1) } elseif ($alive) { 'running for 10s, no errors' } else { 'pet process stopped' }))
        Set-Pet 'speak' 'USB self-test: hello from the stick!'
        Start-Sleep -Seconds 4
        Set-Pet 'quit' ''
        Start-Sleep -Seconds 3
        if (-not $pp.HasExited) { Stop-Process -Id $pp.Id -Force -ErrorAction SilentlyContinue }
    } catch { T 'Pet appears and runs' $false $_.Exception.Message }

    # 6. memory sync with the laptop
    try { $s = Sync-Memory; T 'Memory sync with laptop' $(if (Test-Path $LaptopMemDir) { [bool]$s } else { $null }) ($(if (Test-Path $LaptopMemDir) { 'synced' } else { 'not on the laptop - skipped' })) }
    catch { T 'Memory sync with laptop' $false $_.Exception.Message }

    Stop-LocalBrain
    $pass = @($lines | Where-Object { $_ -like 'PASS*' }).Count; $fail = @($lines | Where-Object { $_ -like 'FAIL*' }).Count
    [void]$lines.Add("RESULT: $pass passed, $fail failed")
    [IO.File]::WriteAllLines($Report, [string[]]$lines)
    Write-Host ""; Write-Host "RESULT: $pass passed, $fail failed  -  saved to $Report" -ForegroundColor Cyan
    exit 0
}

Write-Host "  PARKYY  -  portable edition (offline + online)" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

Load-Keys
$online = Test-Online
if ($online -and @(Get-CloudBrains).Count -eq 0 -and (Test-Path $LaptopEnv)) {
    Write-Host "You're online, but this stick has no cloud keys yet." -ForegroundColor Yellow
    Invoke-SetupOnline
}
$cloudNow = @(Get-CloudBrains)
if ($online -and $cloudNow.Count -gt 0) {
    Write-Host ("Online - using " + (($cloudNow | ForEach-Object { $_.name }) -join ' then ') + ". The offline brain stays asleep unless it's needed.") -ForegroundColor Green
} elseif ($online) {
    Write-Host "Online, but no cloud keys here - using the offline brain." -ForegroundColor Yellow
    if (-not (Start-LocalBrain)) { Write-Host "(no brain available yet - add keys.env, or put llamafile + a model on the stick)" -ForegroundColor Red }
} else {
    Write-Host "No internet - using the offline brain." -ForegroundColor Yellow
    if (-not (Start-LocalBrain)) {
        Write-Host "Brain didn't start. Check the minimized llamafile window for errors." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

if (Sync-Memory) { Write-Host "Memory synced with laptop PARKYY." -ForegroundColor DarkGray }
Write-Host ""
Write-Host "Commands: /remember <fact>  /memory  /forget <number>  /web <question>  /online  /offline  /setup-online  /sync  /voice  /clear  /exit" -ForegroundColor DarkGray
Write-Host ""

$history = New-Object System.Collections.ArrayList

try {
while ($true) {
    Write-Host "You: " -NoNewline -ForegroundColor Yellow
    $msg = Read-Host
    if ($null -eq $msg) { break }
    $msg = $msg.Trim()
    if ($msg -eq '') { continue }

    if ($msg -match '^/(exit|quit)$') { [void](Sync-Memory); Write-Host "Bye, Saud." -ForegroundColor Cyan; break }
    if ($msg -match '^/clear$') { $history.Clear(); Write-Host "(conversation cleared - memory kept)" -ForegroundColor DarkGray; continue }
    if ($msg -match '^/voice$') {
        if ($null -eq $Voice) { Write-Host "(voice isn't available on this PC)" -ForegroundColor DarkGray }
        else { $VoiceOn = -not $VoiceOn; Write-Host ("(voice " + $(if ($VoiceOn) {'on'} else {'off'}) + ")") -ForegroundColor DarkGray }
        continue
    }
    if ($msg -match '^/memory$') {
        $mem = @(Get-Memory)
        if ($mem.Count -eq 0) { Write-Host "(nothing saved yet)" -ForegroundColor DarkGray }
        for ($i = 0; $i -lt $mem.Count; $i++) { Write-Host ("  {0}. {1}" -f ($i + 1), $mem[$i]) -ForegroundColor DarkGray }
        continue
    }
    if ($msg -match '^/remember\s+(.+)$' -or $msg -match '^(?:please\s+)?remember(?:\s+that)?\s+(.+?)[.!]?$') {
        Add-Fact $Matches[1]
        Write-Host ("PARKYY: Got it - I'll remember: " + $Matches[1].Trim()) -ForegroundColor Cyan
        continue
    }
    if ($msg -match '^/forget\s+(\d+)$') {
        $mem = @(Get-Memory)
        $n = [int]$Matches[1] - 1
        if ($n -ge 0 -and $n -lt $mem.Count) { $f = $mem[$n]; Remove-Fact $f; Write-Host ("(forgotten: " + $f + ")") -ForegroundColor DarkGray }
        else { Write-Host "(no memory with that number - try /memory)" -ForegroundColor DarkGray }
        continue
    }
    if ($msg -match '^/sync$') {
        if (Sync-Memory) { Write-Host "(memory synced with laptop PARKYY)" -ForegroundColor DarkGray }
        else { Write-Host "(laptop PARKYY not found on this PC - nothing to sync)" -ForegroundColor DarkGray }
        continue
    }
    if ($msg -match '^/online$') {
        $script:ForceOffline = $false; $script:CloudDownUntil = [DateTime]::MinValue
        Load-Keys; Show-Status; continue
    }
    if ($msg -match '^/offline$') {
        $script:ForceOffline = $true
        Write-Host "(forced offline - loading the offline brain)" -ForegroundColor DarkGray
        [void](Start-LocalBrain); continue
    }
    if ($msg -match '^/setup-online$') { Invoke-SetupOnline; continue }
    if ($msg -match '^/status$') { Show-Status; continue }

    $webText = $null
    $isWeb = $false
    if ($msg -match '^/web\s+(.+)$') {
        $q = $Matches[1].Trim()
        $isWeb = $true
        Write-Host "(searching the web...)" -ForegroundColor DarkGray
        $results = @(Search-Web $q)
        if ($results.Count -eq 0) {
            Write-Host "(couldn't reach the web - no internet, or the search sites are blocked on this network)" -ForegroundColor DarkGray
            continue
        }
        $n = 0
        $block = foreach ($r in $results) { $n++; ("[{0}] {1}`n    {2}`n    {3}" -f $n, $r.title, $r.snippet, $r.url) }
        $webText = "Question: $q`n`nWeb search results:`n" + ($block -join "`n") + "`n`nAnswer the question using these results. Mention which result numbers you used, e.g. [1]. If they don't answer it, say so."
        $msg = $q
    }
    elseif ($msg.StartsWith('/')) { Write-Host "(unknown command)" -ForegroundColor DarkGray; continue }

    [void]$history.Add(@{ role = 'user'; content = $msg })
    Write-Log 'Saud' $msg

    Write-Host "PARKYY is thinking..." -ForegroundColor DarkGray
    Set-Pet 'thinking' ''
    try {
        $res = Invoke-Brain $history $webText
    } catch {
        Set-Pet 'idle' ''
        Write-Host ("(brain error: " + $_.Exception.Message + ")") -ForegroundColor Red
        $history.RemoveAt($history.Count - 1)
        continue
    }
    $reply = $res.text
    if ($reply -eq '') { $reply = '(no reply)' }

    [void]$history.Add(@{ role = 'assistant'; content = $reply })
    Write-Log 'PARKYY' $reply
    $script:LastBrain = $res.brain
    Set-Pet 'speak' $reply
    Write-Host "PARKYY: " -NoNewline -ForegroundColor Cyan
    Write-Host $reply
    Write-Host ("  [" + $res.brain + "]") -ForegroundColor DarkGray
    Write-Host ""
    if ($VoiceOn -and $Voice) { try { $Voice.Speak($reply) } catch { } }
}
} finally {
    Set-Pet 'quit' ''
    Stop-LocalBrain
}
