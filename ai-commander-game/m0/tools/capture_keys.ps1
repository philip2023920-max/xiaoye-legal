# capture_keys.ps1 - run on your own machine. Keys never pass through chat.
# Usage: powershell -ExecutionPolicy Bypass -File tools\capture_keys.ps1 [-EnvFile .env]
# - input is hidden while typing (SecureString)
# - same key is overwritten, not duplicated; press Enter to keep/skip
# - file is written as UTF-8 without BOM, ASCII content only
param([string]$EnvFile = ".env")
$keys = @("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")
if (-not (Test-Path $EnvFile)) { New-Item -ItemType File -Path $EnvFile | Out-Null }
$lines = @(Get-Content $EnvFile -Encoding utf8)
foreach ($k in $keys) {
  $exists = $lines | Where-Object { $_ -match "^$k=.+" }
  $hint = if ($exists) { "already set, Enter to keep" } else { "Enter to skip" }
  $secure = Read-Host -Prompt "$k ($hint)" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  if ($plain) {
    $lines = @($lines | Where-Object { $_ -notmatch "^$k=" }) + "$k=$plain"
    Write-Host "  saved $k"
  }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines((Resolve-Path $EnvFile).Path, $lines, $utf8)
Write-Host "done: $EnvFile"
