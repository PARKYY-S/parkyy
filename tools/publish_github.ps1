# Publishes PARKYY's code to GitHub - safely.
#  - uploads ONLY an allow-list of code files (never .env, tokens, memory, chats, notes, logs, models)
#  - blanks out personal names in the uploaded copy (your files on this laptop are not changed)
#  - scans every file for API keys / tokens (including the real values in your .env) and STOPS if it finds one
#  - creates the repo PRIVATE first, shows you the link, then asks before making it public
# Uses your GitHub login saved by CONNECT-GITHUB.bat (data\github-token.txt). Needs no git install.
param([string]$Name = 'parkyy', [switch]$Yes, [switch]$DryRun)

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Api  = if ($env:PARKYY_GH_API) { $env:PARKYY_GH_API } else { 'https://api.github.com' }

function Ask($q) { if ($Yes) { Write-Host "$q y (auto)"; return $true }; $a = Read-Host "$q (y/n)"; return ($a -match '^\s*y') }
function Say($t, $c = 'Gray') { Write-Host $t -ForegroundColor $c }

# ---------- 1. which files go up (allow-list) ----------
$include = @(
  '*.py', 'README.md', 'PARKYY-HISTORY.md', 'LICENSE', 'requirements.txt', '.gitignore', 'brains.json',
  'START-PARKYY.bat', 'RESTART-PARKYY.bat', 'SETUP-PARKYY.bat', 'START-BACKEND.bat', 'RELOAD-BACKEND.bat',
  'INSTALL-*.bat', 'CONNECT-*.bat', 'PUBLISH-TO-GITHUB.bat', 'reload.ps1', 'restart.ps1', 'PARKYY-preview.html',
  'tools/*.py', 'tools/publish_github.ps1',
  'desktop/*.js', 'desktop/*.html', 'desktop/*.ps1', 'desktop/package.json', 'desktop/package-lock.json',
  'PARKYY-USB/parkyy.ps1', 'PARKYY-USB/pet.ps1', 'PARKYY-USB/start.bat', 'PARKYY-USB/README.txt',
  'PARKYY-USB/models/PUT-MODEL-HERE.txt', 'PARKYY-USB/pet/assets/*.png',
  'docs/*.md', 'data/bench_history.json'
)
$never = '(^|[\\/])(\.env|voice\.env|about-saud\.md|google-credentials\.json|google-token\.json|github-token\.txt|keys\.env|settings\.json|PARKYY-OUTREACH-BRIEF\.md|seed-reminders\.json)$|(^|[\\/])(memory|notes|knowledge|projects|venv|node_modules|voices|voice-model|__pycache__|_backup[^\\/]*)[\\/]|\.(log|wav|gguf)$'

$files = New-Object System.Collections.Generic.List[string]
foreach ($pat in $include) {
    $dir = Join-Path $Root (Split-Path $pat)
    $leaf = Split-Path $pat -Leaf
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -Path $dir -Filter $leaf -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $rel = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
        if ($rel -notmatch $never -and -not $files.Contains($rel)) { [void]$files.Add($rel) }
    }
}
$extra = @{}
$ex = Join-Path $Root '.env - Copy.example'
if (-not (Test-Path (Join-Path $Root '.env.example')) -and (Test-Path $ex)) { $extra['.env.example'] = $ex }
elseif (Test-Path (Join-Path $Root '.env.example')) { [void]$files.Add('.env.example') }

# ---------- 2. personal names out of the PUBLIC copy only ----------
# private words -> public replacement, stored encoded so the list itself never shows up in the public copy
$scrub = [ordered]@{}
foreach ($e in 'RHJpdGl8QWxleA==;RHJpaXxBbGV4;VXNlcnNcc2F1ZHB8VXNlcnNceW91;VXNlcnMvc2F1ZHB8VXNlcnMveW91'.Split(';')) { $kv = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($e)).Split('|'); $scrub[$kv[0]] = $kv[1] }
function Get-Bytes($rel, $full) {
    $b = [IO.File]::ReadAllBytes($full)
    if ($rel -match '\.(png|jpg|gif|ico)$') { return ,$b }
    $t = [Text.Encoding]::UTF8.GetString($b)
    foreach ($k in $scrub.Keys) { $t = $t -replace [regex]::Escape($k), $scrub[$k] }
    return ,([Text.Encoding]::UTF8.GetBytes($t))
}

# ---------- 3. secret scan ----------
$secretRx = 'gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|sk-(ant-|or-|proj-)?[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|nvapi-[A-Za-z0-9_\-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY'
$realValues = @()
foreach ($f in @('.env', 'voice.env', 'data/github-token.txt')) {
    $p = Join-Path $Root $f
    if (Test-Path $p) {
        foreach ($line in [IO.File]::ReadAllLines($p)) {
            $v = ''
            if ($f -like '*github-token.txt') { $v = $line }
            elseif ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
                $key = $Matches[1]; $val = $Matches[2]
                if ($key -match 'KEY|TOKEN|SECRET|PASSWORD|PIN|PASS') { $v = [string]$val }
            }
            $v = $v.Trim().Trim('"', "'")
            if ($v.Length -ge 12) { $realValues += $v }
        }
    }
}
$all = @($files | ForEach-Object { @{ rel = $_; full = (Join-Path $Root $_) } })
foreach ($k in $extra.Keys) { $all += @{ rel = $k; full = $extra[$k] } }
$bad = @()
foreach ($f in $all) {
    if ($f.rel -match '\.(png|jpg|gif|ico)$') { continue }
    $t = [Text.Encoding]::UTF8.GetString((Get-Bytes $f.rel $f.full))
    if ($t -match $secretRx) { $bad += "$($f.rel)  (looks like an API key)"; continue }
    foreach ($v in $realValues) { if ($t.Contains($v)) { $bad += "$($f.rel)  (contains a value from your .env / token file)"; break } }
}
Say ""
Say "PARKYY -> GitHub" Cyan
Say ("Files to upload: " + $all.Count + "   (code, docs, USB edition, benchmark history)")
Say "NOT uploaded: .env, tokens, Google login, memory, chats, notes, logs, models, voice recordings." DarkGray
if ($bad.Count) {
    Say "`nSTOPPED - these files look like they contain a secret:" Red
    $bad | ForEach-Object { Say "  $_" Red }
    Say "Nothing was uploaded. Remove the secret from those files (or tell Claude) and run this again." Yellow
    exit 2
}
Say "Secret scan: clean (checked for API keys and for every real value in your .env and token file)." Green
if ($DryRun) { $all | ForEach-Object { Say ("  " + $_.rel) DarkGray }; exit 0 }

# ---------- 4. GitHub ----------
$tokFile = Join-Path $Root 'data/github-token.txt'
if (-not (Test-Path $tokFile)) { Say "No GitHub login found. Run CONNECT-GITHUB.bat first." Red; exit 3 }
$tok = ([IO.File]::ReadAllText($tokFile)).Trim()
$H = @{ Authorization = "Bearer $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'PARKYY' }
function GH($method, $path, $body) {
    $args2 = @{ Method = $method; Uri = "$Api$path"; Headers = $H; UseBasicParsing = $true }
    if ($null -ne $body) { $args2.Body = ($body | ConvertTo-Json -Depth 20 -Compress); $args2.ContentType = 'application/json' }
    return Invoke-RestMethod @args2
}
try { $me = GH GET '/user' $null } catch { Say "GitHub didn't accept the saved login: $($_.Exception.Message)`nRun CONNECT-GITHUB.bat again, then this." Red; exit 3 }
$owner = $me.login
Say "Signed in to GitHub as: $owner" Green
if (-not (Ask "Upload these files to a PRIVATE repo github.com/$owner/$Name ?")) { Say "OK - nothing uploaded."; exit 0 }

$repo = $null
try { $repo = GH GET "/repos/$owner/$Name" $null } catch { }
if ($repo) {
    if (-not (Ask "The repo $owner/$Name already exists. Add a new commit with these files to it?")) { exit 0 }
} else {
    try {
        $repo = GH POST '/user/repos' @{ name = $Name; private = $true; auto_init = $true
            description = "PARKYY - a personal AI assistant that can't act without your Yes and checks its own work. Free, offline-capable." }
        Start-Sleep -Seconds 2
    } catch {
        Say "GitHub refused to create the repo: $($_.Exception.Message)" Red
        Say "Fix: on github.com click New repository, name it '$Name', tick 'Add a README', Create. Then run this again." Yellow
        exit 4
    }
}
$branch = $repo.default_branch; if (-not $branch) { $branch = 'main' }
$ref = GH GET "/repos/$owner/$Name/git/ref/heads/$branch" $null
$base = $ref.object.sha

Say "Uploading $($all.Count) files..." Cyan
$tree = @(); $n = 0
foreach ($f in $all) {
    $b64 = [Convert]::ToBase64String((Get-Bytes $f.rel $f.full))
    $blob = GH POST "/repos/$owner/$Name/git/blobs" @{ content = $b64; encoding = 'base64' }
    $tree += @{ path = ($f.rel -replace '\\', '/'); mode = '100644'; type = 'blob'; sha = $blob.sha }
    $n++; if ($n % 10 -eq 0) { Write-Host "  $n / $($all.Count)" }
}
$t = GH POST "/repos/$owner/$Name/git/trees" @{ tree = $tree }
$c = GH POST "/repos/$owner/$Name/git/commits" @{ message = "PARKYY: code, docs, USB edition, benchmark history"; tree = $t.sha; parents = @($base) }
[void](GH PATCH "/repos/$owner/$Name/git/refs/heads/$branch" @{ sha = $c.sha; force = $false })
try { [void](GH PUT "/repos/$owner/$Name/topics" @{ names = @('ai-assistant', 'llm', 'agents', 'ai-safety', 'electron', 'fastapi', 'offline-first', 'groq', 'gemini') }) } catch { }

$url = "https://github.com/$owner/$Name"
Say "`nDone - uploaded privately: $url" Green
Say "Open it and look at it like a stranger would (README, no secrets)." Gray
if (Ask "Make it PUBLIC now so companies can see it?") {
    [void](GH PATCH "/repos/$owner/$Name" @{ private = $false })
    Say "It's public: $url" Green
} else { Say "Left private. Run this again any time and answer y to make it public." Gray }
[IO.File]::WriteAllText((Join-Path $Root 'data/github-repo-url.txt'), $url)
