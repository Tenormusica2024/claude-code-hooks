# install.ps1 - claude-code-hooks インストールスクリプト
# ~/.claude/hooks/ へhookファイルをコピーし、未登録フックを案内する（settings.json は自動書き換えしない）

$ErrorActionPreference = "Stop"
$HooksDir = "$env:USERPROFILE\.claude\hooks"
$SettingsFile = "$env:USERPROFILE\.claude\settings.json"
$SourceDir = Join-Path $PSScriptRoot "hooks"

# --- 1. hookファイルをコピー ---
Write-Host "Copying hooks to $HooksDir ..."
if (-not (Test-Path $HooksDir)) {
    New-Item -ItemType Directory -Path $HooksDir | Out-Null
}

# Stop hooks
$stopHooks = @(
    "test-delegation-detector.py",
    "claude-md-auto-recorder.py",
    "completion-hook.py",
    "test-complete-hook.py"
)

# UserPromptSubmit hooks（hooks.Stop ではなく hooks.UserPromptSubmit に登録が必要）
$userPromptHooks = @(
    "document-update-detector.py",
    "global-claude-md-appender.py"
)

$hooks = $stopHooks + $userPromptHooks

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
    Write-Host "  Manually add Stop hooks to settings.json:"
    foreach ($hook in $stopHooks) {
        Write-Host "    python `"$HooksDir\$hook`""
    }
    Write-Host "  Manually add UserPromptSubmit hooks to settings.json:"
    foreach ($hook in $userPromptHooks) {
        Write-Host "    python `"$HooksDir\$hook`""
    }
    exit 0
}

$settings = Get-Content $SettingsFile -Raw | ConvertFrom-Json
$settingsText = $settings | ConvertTo-Json -Depth 20

$alreadyRegistered = @()
$notRegisteredStop = @()
$notRegisteredUserPrompt = @()

foreach ($hook in $stopHooks) {
    if ($settingsText -match [regex]::Escape($hook)) {
        $alreadyRegistered += $hook
    } else {
        $notRegisteredStop += $hook
    }
}

foreach ($hook in $userPromptHooks) {
    if ($settingsText -match [regex]::Escape($hook)) {
        $alreadyRegistered += $hook
    } else {
        $notRegisteredUserPrompt += $hook
    }
}

if ($alreadyRegistered.Count -gt 0) {
    Write-Host "  Already registered: $($alreadyRegistered -join ', ')"
}

if ($notRegisteredStop.Count -gt 0) {
    Write-Host ""
    Write-Host "Add to hooks.Stop in $SettingsFile :"
    foreach ($hook in $notRegisteredStop) {
        Write-Host "  python `"$HooksDir\$hook`""
    }
}

if ($notRegisteredUserPrompt.Count -gt 0) {
    Write-Host ""
    Write-Host "Add to hooks.UserPromptSubmit in $SettingsFile :"
    foreach ($hook in $notRegisteredUserPrompt) {
        Write-Host "  python `"$HooksDir\$hook`""
    }
}

Write-Host ""
Write-Host "Install complete."
