# install.ps1 - claude-code-hooks インストールスクリプト
# ~/.claude/hooks/ へhookファイルをコピーし、~/.claude/skills/ へテストスキルをコピーする

$ErrorActionPreference = "Stop"
$HooksDir = "$env:USERPROFILE\.claude\hooks"
$SkillsDir = "$env:USERPROFILE\.claude\skills"
$SettingsFile = "$env:USERPROFILE\.claude\settings.json"
$SourceDir = Join-Path $PSScriptRoot "hooks"

# --- 1. hookファイルをコピー ---
Write-Host "Copying hooks to $HooksDir ..."
if (-not (Test-Path $HooksDir)) {
    New-Item -ItemType Directory -Path $HooksDir | Out-Null
}

$hooks = @(
    "test-delegation-detector.py",
    "claude-md-auto-recorder.py",
    "completion-hook.py",
    "test-complete-hook.py",
    "project_classifier.py",
    "hook_utils.py",
    "document-update-detector.py",
    "global-claude-md-appender.py"
)

foreach ($hook in $hooks) {
    $src = Join-Path $SourceDir $hook
    if (Test-Path $src) {
        $dst = Join-Path $HooksDir $hook
        Copy-Item -Path $src -Destination $dst -Force
        Write-Host "  Copied: $hook"
    } else {
        Write-Host "  Skipped (not found): $hook"
    }
}

# --- 2. テストスキルをコピー ---
Write-Host ""
Write-Host "Copying test skills to $SkillsDir ..."

$skills = @(
    "tdd-guard",
    "agent-test",
    "e2e-auth-test",
    "backend-test"
)

foreach ($skill in $skills) {
    $skillDir = Join-Path $SkillsDir $skill
    if (-not (Test-Path $skillDir)) {
        New-Item -ItemType Directory -Path $skillDir | Out-Null
    }
    # スキルの SKILL.md が既に存在する場合はスキップ（上書き防止）
    $dst = Join-Path $skillDir "SKILL.md"
    if (Test-Path $dst) {
        Write-Host "  Already exists: $skill/SKILL.md"
    } else {
        Write-Host "  Created directory: $skill/ (SKILL.md must be placed manually)"
    }
}

# --- 3. settings.json の Stop hooks セクションを確認・追記 ---
Write-Host ""
Write-Host "Checking settings.json ..."

$stopHooks = @(
    "test-delegation-detector.py",
    "claude-md-auto-recorder.py",
    "completion-hook.py",
    "test-complete-hook.py"
)

if (-not (Test-Path $SettingsFile)) {
    Write-Host "  settings.json not found. Skipping auto-patch."
    Write-Host "  Manually add the following to your settings.json Stop hooks:"
    foreach ($hook in $stopHooks) {
        Write-Host "    python `"$HooksDir\$hook`""
    }
    exit 0
}

$settings = Get-Content $SettingsFile -Raw | ConvertFrom-Json

$alreadyRegistered = @()
$notRegistered = @()

foreach ($hook in $stopHooks) {
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

# --- 4. settings.json の UserPromptSubmit hooks セクションを確認 ---
Write-Host ""
Write-Host "Checking UserPromptSubmit hooks in settings.json ..."

$userPromptHooks = @(
    "document-update-detector.py",
    "global-claude-md-appender.py"
)

$upsAlreadyRegistered = @()
$upsNotRegistered = @()

foreach ($hook in $userPromptHooks) {
    # UserPromptSubmit 配下を厳密に確認する
    $registered = $false
    if ($settings.hooks -and $settings.hooks.UserPromptSubmit) {
        $upsText = $settings.hooks.UserPromptSubmit | ConvertTo-Json -Depth 20
        if ($upsText -match [regex]::Escape($hook)) {
            $registered = $true
        }
    }
    if ($registered) {
        $upsAlreadyRegistered += $hook
    } else {
        $upsNotRegistered += $hook
    }
}

if ($upsAlreadyRegistered.Count -gt 0) {
    Write-Host "  Already registered under hooks.UserPromptSubmit: $($upsAlreadyRegistered -join ', ')"
}

if ($upsNotRegistered.Count -gt 0) {
    Write-Host ""
    Write-Host "The following hooks are NOT yet in settings.json UserPromptSubmit hooks:"
    foreach ($hook in $upsNotRegistered) {
        Write-Host "  python `"$HooksDir\$hook`""
    }
    Write-Host ""
    Write-Host "Add them manually to the UserPromptSubmit hooks section in:"
    Write-Host "  $SettingsFile"
}

Write-Host ""
Write-Host "Install complete."
