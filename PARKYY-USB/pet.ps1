# PARKYY's desktop pet - USB edition (the original PARKYY, walking on your windows).
# Started by start.bat next to PARKYY. Needs nothing installed: Windows PowerShell 5.1 + WPF only.
# It talks to parkyy.ps1 through the small file pet-state.txt  ("mode<TAB>text<TAB>counter").
# Turn it off by setting PARKYY_PET=0 before start.bat, or right-click the pet -> Hide pet.
param([string]$Root = $PSScriptRoot, [int]$ParentPid = 0)

$ErrorActionPreference = 'Stop'
$LogFile = Join-Path $Root 'logs\pet.log'
function Log($m) { try { Add-Content -Path $LogFile -Value ((Get-Date -Format s) + ' ' + $m) } catch { } }
try { if (-not (Test-Path (Split-Path $LogFile))) { New-Item -ItemType Directory -Path (Split-Path $LogFile) | Out-Null } } catch { }

try {
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class PkWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct LII { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LII p);
  [DllImport("kernel32.dll")] public static extern uint GetTickCount();
  [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
  [DllImport("user32.dll")] public static extern int SetWindowLong(IntPtr h, int i, int v);
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECT r, int size);
  public static int[] Fg() {
    IntPtr h = GetForegroundWindow(); if (h == IntPtr.Zero) return null;
    RECT r; if (DwmGetWindowAttribute(h, 9, out r, Marshal.SizeOf(typeof(RECT))) != 0) { if (!GetWindowRect(h, out r)) return null; }
    return new int[] { (int)h, r.Left, r.Top, r.Right, r.Bottom, IsZoomed(h) ? 1 : 0, IsIconic(h) ? 1 : 0 };
  }
  public static string Title(IntPtr h) { StringBuilder sb = new StringBuilder(256); GetWindowText(h, sb, 256); return sb.ToString(); }
  public static double IdleSeconds() { LII l = new LII(); l.cbSize = (uint)Marshal.SizeOf(typeof(LII)); if (!GetLastInputInfo(ref l)) return 0; return (GetTickCount() - l.dwTime) / 1000.0; }
  public static void NoActivate(IntPtr h) { int e = GetWindowLong(h, -20); SetWindowLong(h, -20, e | 0x08000000 | 0x00000080); }
}
'@
[void][PkWin]::SetProcessDPIAware()

# ---- pictures (rendered from the original PARKYY) ----
$A = Join-Path $Root 'pet\assets'
$Img = @{}
foreach ($n in 'idle','blink','happy','walk1','walk2','talk','sleep','read','wave','fly1','fly2') {
    $p = Join-Path $A ($n + '.png')
    $b = New-Object System.Windows.Media.Imaging.BitmapImage
    $b.BeginInit(); $b.UriSource = New-Object System.Uri($p); $b.CacheOption = 'OnLoad'; $b.EndInit(); $b.Freeze()
    $Img[$n] = $b
}

# ---- window: pet picture + speech bubble, transparent, click-through where empty ----
$WW = 230; $WH = 190; $SZ = 112
[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        WindowStyle="None" AllowsTransparency="True" Background="{x:Null}" ShowInTaskbar="False"
        Topmost="True" ShowActivated="False" ResizeMode="NoResize" Title="PARKYY pet" SizeToContent="Manual">
  <Grid>
    <Border x:Name="Bub" Visibility="Collapsed" VerticalAlignment="Top" HorizontalAlignment="Center" Margin="4,2,4,0"
            Background="#F00E1B38" BorderBrush="#3D7BFF" BorderThickness="1.5" CornerRadius="12" Padding="10,6,10,6" MaxWidth="220">
      <TextBlock x:Name="BubT" Foreground="#EAF1FF" FontSize="13" TextWrapping="Wrap" FontFamily="Segoe UI"/>
    </Border>
    <Image x:Name="Pet" VerticalAlignment="Bottom" HorizontalAlignment="Center" Margin="0,0,0,4" RenderTransformOrigin="0.5,0.5"/>
  </Grid>
</Window>
'@
$win = [Windows.Markup.XamlReader]::Load((New-Object System.Xml.XmlNodeReader $xaml))
$bub = $win.FindName('Bub'); $bubT = $win.FindName('BubT'); $pic = $win.FindName('Pet')
$win.Width = $WW; $win.Height = $WH; $pic.Width = $SZ; $pic.Height = $SZ
$flip = New-Object System.Windows.Media.ScaleTransform(1, 1); $pic.RenderTransform = $flip
$win.Add_SourceInitialized({ try { [PkWin]::NoActivate((New-Object System.Windows.Interop.WindowInteropHelper($win)).Handle) } catch { Log "noactivate: $_" } })

# ---- state ----
$wa = [System.Windows.SystemParameters]::WorkArea
$S = @{
  x = $wa.Left + $wa.Width * 0.6; y = $wa.Bottom; fy = $wa.Bottom; x1 = $wa.Left + 20; x2 = $wa.Right - 20
  face = 1; mode = 'sit'; tx = 0; nextAct = 0; tick = 0
  sayUntil = 0; happyUntil = 0; waveUntil = 0; speakUntil = 0; think = $false
  fgId = 0; fid = ''; ty = 0; hold = 0; hoverUntil = 0; reading = $false; scale = 1.0; lastState = ''; hidden = $false
}
$rnd = New-Object System.Random
$readRx = 'pdf|epub|\.docx?|word|acrobat|reader|kindle|wikipedia|notion|docs|\.pptx?|readme'
$hello = @('Hi Saud!', 'Need something?', 'I''m here!', 'Want me to look something up?', 'Boop!', 'Ask me anything')
$chat  = @('Stretch your legs?', 'Water break?', 'I''m learning the Wi-Fi smell.', 'You''re doing great.', 'Psst. Try /web <question>')

function NowMs { [Environment]::TickCount }
function Say($t, $ms) {
    if (-not $t) { return }
    $t = [string]$t; if ($t.Length -gt 140) { $t = $t.Substring(0, 137) + '...' }
    $bubT.Text = $t; $bub.Visibility = 'Visible'; $S.sayUntil = (NowMs) + $ms
}
function Set-Floor {
    $f = $null
    try { $f = [PkWin]::Fg() } catch { }
    $wa2 = [System.Windows.SystemParameters]::WorkArea
    $S.fy = $wa2.Bottom; $S.x1 = $wa2.Left + 20; $S.x2 = $wa2.Right - 20; $S.reading = $false
    $newId = 'desk'
    if ($f -and $f[5] -eq 0 -and $f[6] -eq 0) {
        $sc = $S.scale
        $l = $f[1] * $sc; $t = $f[2] * $sc; $r = $f[3] * $sc
        if ((($r - $l) -gt 340) -and ($t -gt $wa2.Top + 60) -and ($t -lt $wa2.Bottom - 120)) {
            $newId = [string]$f[0]
            $S.fy = $t; $S.x1 = [Math]::Max($wa2.Left + 20, $l + 40); $S.x2 = [Math]::Min($wa2.Right - 20, $r - 40)
            if ($S.x2 - $S.x1 -lt 120) { $newId = 'desk'; $S.fy = $wa2.Bottom; $S.x1 = $wa2.Left + 20; $S.x2 = $wa2.Right - 20 }
            else { try { $S.reading = ([PkWin]::Title([IntPtr]$f[0]) -match $readRx) } catch { } }
        }
    }
    # you switched windows -> he flies over to the new floor
    if ($newId -ne $S.fid) {
        $S.fid = $newId
        if ($S.mode -ne 'fly' -or $S.hold -eq 0) { $S.mode = 'fly'; $S.hold = 0; $S.tx = [Math]::Max($S.x1, [Math]::Min($S.x2, $S.x)); $S.ty = $S.fy }
    }
}

function Read-Cmd {
    $p = Join-Path $Root 'pet-state.txt'
    if (-not (Test-Path $p)) { return }
    try { $raw = [IO.File]::ReadAllText($p) } catch { return }
    if ($raw -eq $S.lastState) { return }
    $S.lastState = $raw
    $parts = $raw.Trim() -split "`t", 3
    switch ($parts[0]) {
        'quit'     { $win.Close() }
        'thinking' { $S.think = $true; Say 'Thinking...' 60000 }
        'speak'    { $S.think = $false; $txt = ''; if ($parts.Count -gt 1) { $txt = $parts[1] }
                     $ms = [Math]::Min(9000, 2500 + $txt.Length * 60); Say $txt $ms; $S.speakUntil = (NowMs) + $ms; $S.mode = 'sit' }
        'listen'   { $S.think = $false; $S.waveUntil = (NowMs) + 1500 }
        default    { $S.think = $false }
    }
}

function Frame {
    $now = NowMs
    if ($S.sayUntil -gt 0 -and $now -gt $S.sayUntil) { $bub.Visibility = 'Collapsed'; $S.sayUntil = 0 }
    $idle = 0; try { $idle = [PkWin]::IdleSeconds() } catch { }
    $asleep = ($idle -gt 150) -and ($S.speakUntil -lt $now) -and (-not $S.think)
    $name = 'idle'
    if ($asleep) { $S.mode = 'sit'; $name = 'sleep' }
    elseif ($S.mode -eq 'fly' -or $S.mode -eq 'hover') {
        $name = 'fly1'; if ((([int][Math]::Floor($S.tick / 3)) -band 1) -eq 1) { $name = 'fly2' }
        if ($S.mode -eq 'fly') {
            $dx = $S.tx - $S.x; $dy = $S.ty - $S.y; $dist = [Math]::Sqrt($dx * $dx + $dy * $dy)
            $sp = [Math]::Min(9.0, 2.0 + $dist * 0.08)
            if ($dist -le $sp + 1) {
                $S.x = $S.tx; $S.y = $S.ty
                if ($S.hold -gt 0) { $S.mode = 'hover'; $S.hoverUntil = $now + $S.hold } else { $S.mode = 'sit'; $S.nextAct = $now + $rnd.Next(1500, 4000) }
            } else { $S.x += $dx / $dist * $sp; $S.y += $dy / $dist * $sp; if ($dx -gt 1) { $S.face = 1 } elseif ($dx -lt -1) { $S.face = -1 } }
        } else {
            $S.y += [Math]::Sin($S.tick / 8.0) * 0.6
            if ($now -gt $S.hoverUntil) { $S.mode = 'fly'; $S.hold = 0; $S.tx = $rnd.Next([int]$S.x1, [int]([Math]::Max($S.x1 + 1, $S.x2))); $S.ty = $S.fy }
        }
    }
    elseif ($S.mode -eq 'walk') {
        $S.x += $S.face * 3
        if ($S.x -lt $S.x1) { $S.x = $S.x1; $S.mode = 'sit' } elseif ($S.x -gt $S.x2) { $S.x = $S.x2; $S.mode = 'sit' }
        elseif ([Math]::Abs($S.tx - $S.x) -lt 4) { $S.mode = 'sit'; $S.nextAct = $now + $rnd.Next(2500, 7000) }
        if ((([int][Math]::Floor($S.tick / 5)) -band 1) -eq 0) { $name = 'walk1' } else { $name = 'walk2' }
    } else {
        if ($S.speakUntil -gt $now) { if ((([int][Math]::Floor($S.tick / 6)) -band 1) -eq 0) { $name = 'talk' } else { $name = 'idle' } }
        elseif ($S.happyUntil -gt $now) { $name = 'happy' }
        elseif ($S.waveUntil -gt $now) { $name = 'wave' }
        elseif ($S.reading) { $name = 'read' }
        elseif ((($S.tick % 130) -lt 3)) { $name = 'blink' }
        if ($now -gt $S.nextAct -and -not $S.think -and $S.speakUntil -lt $now -and -not $S.reading) {
            if ($rnd.NextDouble() -lt 0.6) {
                $S.tx = $rnd.Next([int]$S.x1, [int]([Math]::Max($S.x1 + 1, $S.x2)))
                if ([Math]::Abs($S.tx - $S.x) -gt 40) { $S.mode = 'walk'; if ($S.tx -gt $S.x) { $S.face = 1 } else { $S.face = -1 } }
            } elseif ($rnd.NextDouble() -lt 0.3) {
                $S.mode = 'fly'; $S.hold = $rnd.Next(2500, 6000)
                $S.tx = $rnd.Next([int]($wa.Left + 80), [int]($wa.Right - 80)); $S.ty = [Math]::Max($wa.Top + $WH, $S.fy - $rnd.Next(120, 320))
            } elseif ($rnd.NextDouble() -lt 0.15 -and $idle -lt 60) { Say $chat[$rnd.Next(0, $chat.Count)] 4500 }
            $S.nextAct = $now + $rnd.Next(3000, 8000)
        }
    }
    # smooth hop to the current floor (a window's top edge or the bottom of the screen)
    if ($S.mode -ne 'fly' -and $S.mode -ne 'hover') {
        $dy = $S.fy - $S.y
        if ([Math]::Abs($dy) -gt 0.5) { $S.y += $dy * 0.22 } else { $S.y = $S.fy }
    }
    if ($S.x -lt $S.x1) { $S.x += 4 } elseif ($S.x -gt $S.x2) { $S.x -= 4 }
    $pic.Source = $Img[$name]
    $flip.ScaleX = $S.face
    $win.Left = $S.x - $WW / 2
    $win.Top = $S.y - $WH + 14
    $S.tick++
}

# ---- interaction: click = happy, right-click = menu ----
$pic.Add_MouseLeftButtonDown({
    $S.happyUntil = (NowMs) + 2000; $S.mode = 'sit'
    Say $hello[$rnd.Next(0, $hello.Count)] 2500
})
$menu = New-Object System.Windows.Controls.ContextMenu
foreach ($it in @(@('Say hi', { $S.waveUntil = (NowMs) + 2500; Say 'Hi Saud!' 2500 }), @('Hide pet', { $win.Close() }))) {
    $mi = New-Object System.Windows.Controls.MenuItem; $mi.Header = $it[0]; $mi.Add_Click($it[1]); [void]$menu.Items.Add($mi)
}
$pic.ContextMenu = $menu

$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(40)
$slow = 0
$timer.Add_Tick({
    try {
        $script:slow++
        if (($script:slow % 5) -eq 0) { Set-Floor }
        if (($script:slow % 12) -eq 0) {
            Read-Cmd
        }
        # leave when PARKYY's window has been closed (checked every ~12 s, after a 30 s grace period)
        if (($script:slow % 300) -eq 0 -and $script:slow -gt 750) {
            $alive = $true
            try { $alive = [bool](Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction Stop | Where-Object { $_.CommandLine -match 'parkyy\.ps1' }) } catch { }
            if (-not $alive) { $win.Close() }
        }
        Frame
    } catch { Log "tick: $_" }
})
$win.Add_ContentRendered({
    try { $src = [System.Windows.PresentationSource]::FromVisual($win); $S.scale = $src.CompositionTarget.TransformFromDevice.M11 } catch { Log "dpi: $_" }
    $S.y = $S.fy; Say 'Hi Saud! I''m on your USB now.' 3500
    $timer.Start()
})
$win.Add_Closed({ $timer.Stop(); [System.Windows.Threading.Dispatcher]::ExitAllFrames() })
Log 'pet start'
[void]$win.ShowDialog()
Log 'pet end'
} catch { Log ("FATAL: " + $_ + " | " + $_.ScriptStackTrace) }
