# install.ps1 - claude-code-hooks インストールスクリプト
# ~/.claude/hooks/ へhookファイルをコピーし、settings.jsonにエントリを追加する

$ErrorActionPreference = "Stop"
$HooksDir = "$env:USERPROFILE\.claude\hooks"
$SettingsFile = "$env:USERPROFILE\.claude\settings.json"
$SourceDir = Join-Path $PSScriptRoot "hooks"

# --- 1. hookファイルをコピー ---
Write-Host "Copying hooks to $HooksDir ..."
if (-not (Test-Path $HooksDir)) {
    New-Item -ItemType Directory -Path $HooksDir | Out-Null
}

$hooks = @(
    "test-delegation-detector.py",
    "claude-md-auto-recorder.py"
)

foreach ($hook in $hooks) {
    $src = Join-Path $SourceDir $hook
    $dst = Join-Path $HooksDir $hook
    Copy-Item -Path $src -Destination $dst -Force
    Write-Host "  Copied: $hook"
}

# --- 2. settings.json の Stop hooks セクションを確認・追記 ---
Write-Host "Checking settings.json ..."

if (-not (Test-Path $SettingsFile)) {
    Write-Host "  settings.json not found. Skipping auto-patch."
    Write-Host "  Manually add the following to your settings.json Stop hooks:"
    foreach ($hook in $hooks) {
        Write-Host "    python `"$HooksDir\$hook`""
    }
    exit 0
}

$settings = Get-Content $SettingsFile -Raw | ConvertFrom-Json

$alreadyRegistered = @()
$notRegistered = @()

foreach ($hook in $hooks) {
    $hookPath = "$HooksDir\$hook" -replace "\\", "\\\\"
    $settingsText = $settings | ConvertTo-Json -Depth 20
    if ($settingsText -match [regex]::Escape($hook)) {
        $alreadyRegistered += $hook
    } else {
        $notRegistered += $hook
    }
}

if ($alreadyRegistered.Count -gt 0) {
    Write-Host "  Already registered: $($alreadyRegistered -join ', ')"
}

if ($notRegistered.Count -gt 0) {
    Write-Host ""
    Write-Host "The following hooks are NOT yet in settings.json Stop hooks:"
    foreach ($hook in $notRegistered) {
        Write-Host "  python `"$HooksDir\$hook`""
    }
    Write-Host ""
    Write-Host "Add them manually to the Stop hooks section in:"
    Write-Host "  $SettingsFile"
}

Write-Host ""
Write-Host "Install complete."
