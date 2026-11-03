# Reports the window you're working in (position, size, title, app) as one JSON line, ~3 times a second.
# Used by the PARKYY desktop pet so it can walk along the top of your window. Reads only - changes nothing.
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class PkWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);
}
"@
[void][PkWin]::SetProcessDPIAware()          # real pixels; the desktop app converts them to screen units
$ErrorActionPreference = 'SilentlyContinue'
$last = ''
$sinceEmit = 0
while ($true) {
    $h = [PkWin]::GetForegroundWindow()
    $line = '{"none":true}'
    if ($h -ne [IntPtr]::Zero -and -not [PkWin]::IsIconic($h)) {
        $r = New-Object PkWin+RECT
        # DWM frame = what you actually see (GetWindowRect includes invisible shadow borders)
        if ([PkWin]::DwmGetWindowAttribute($h, 9, [ref]$r, 16) -ne 0) { [void][PkWin]::GetWindowRect($h, [ref]$r) }
        $sb = New-Object System.Text.StringBuilder 256
        [void][PkWin]::GetWindowText($h, $sb, 256)
        $title = $sb.ToString()
        $procId = [uint32]0
        [void][PkWin]::GetWindowThreadProcessId($h, [ref]$procId)
        $pn = ''
        try { $pn = (Get-Process -Id $procId).ProcessName } catch { }
        $reading = ($title -match '(?i)\.pdf|\.epub|\.docx?\b|acrobat|reader|kindle|wikipedia|medium|docs\.google|notion') -or ($pn -match '(?i)^(acro|acrord|winword|sumatra|foxit|kindle|calibre)')
        $o = [ordered]@{
            id = [int64]$h; x = $r.Left; y = $r.Top; w = ($r.Right - $r.Left); h = ($r.Bottom - $r.Top)
            max = [bool][PkWin]::IsZoomed($h); min = $false; reading = [bool]$reading
            title = $title; app = $pn
        }
        $line = ($o | ConvertTo-Json -Compress)
    }
    $sinceEmit += 1
    if ($line -ne $last -or $sinceEmit -ge 10) { [Console]::Out.WriteLine($line); [Console]::Out.Flush(); $last = $line; $sinceEmit = 0 }
    Start-Sleep -Milliseconds 300
}
