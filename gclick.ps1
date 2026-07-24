param([int]$x, [int]$y)
$p = Get-Process | Where-Object { $_.ProcessName -like "CivilizationVI*" -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { "no game window"; exit 1 }
$sig = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, System.UIntPtr e);
'@
$w = Add-Type -MemberDefinition $sig -Name M2 -Namespace U2 -PassThru
$w::ShowWindow($p.MainWindowHandle, 9) | Out-Null
(New-Object -ComObject WScript.Shell).AppActivate($p.Id) | Out-Null
Start-Sleep -Milliseconds 500
$w::SetCursorPos($x, $y) | Out-Null
Start-Sleep -Milliseconds 200
$w::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); $w::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
"focused pid $($p.Id), clicked $x,$y"
