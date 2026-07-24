param([int]$x, [int]$y, [int]$double = 0)
$sig = @'
[DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
[DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, System.UIntPtr dwExtraInfo);
'@
$w = Add-Type -MemberDefinition $sig -Name M -Namespace U -PassThru
$w::SetCursorPos($x, $y) | Out-Null
Start-Sleep -Milliseconds 120
$w::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); $w::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
if ($double -eq 1) { Start-Sleep -Milliseconds 80; $w::mouse_event(2,0,0,0,[UIntPtr]::Zero); $w::mouse_event(4,0,0,0,[UIntPtr]::Zero) }
"clicked $x,$y"
