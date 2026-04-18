# install.ps1 - claude-code-hooks インストールスクリプト
# ~/.claude/hooks/ へhookファイルをコピーし、~/.claude/skills/ へテストスキルをコピーする
#
# 参照先は %USERPROFILE%\.claude\ に統一する。
# Python 側の hook (global-claude-md-appender.py) は Path.home() を使うため、
# Windows では %USERPROFILE% と Path.home() は同じパスを返す前提で一致する。

$ErrorActionPreference = "Stop"
$HooksDir = "$env:USERPROFILE\.claude\hooks"
$SkillsDir = "$env:USERPROFILE\.claude\skills"
$SettingsFile = "$env:USERPROFILE\.claude\settings.json"
$SourceDir = Join-Path $PSScriptRoot "hooks"

# インストール結果サマリ用（全行実行後にまとめて出力する）
$copyErrors = @()
$skillErrors = @()
$settingsError = $null

# 指定 hook が hooks.UserPromptSubmit / hooks.Stop 配下に
# 実際のコマンドとして登録されているかを構造的に判定する共通 helper。
# 従来は ConvertTo-Json した文字列に対する部分一致だけだったため、
# 別の hook のメモ・コメント文字列に hook 名が混ざっているだけで
# 誤って「登録済み」と判定されていた。ここでは hook 配列の中で
# type == "command" かつ command 文字列が対象 hook ファイルを含むか
# という厳密な条件で判定する。
function Test-HookRegistered {
    param(
        [Parameter(Mandatory = $true)]
        $HookSection,
        [Parameter(Mandatory = $true)]
        [string]$HookFile
    )
    if ($null -eq $HookSection) { return $false }
    $escapedHook = [regex]::Escape($HookFile)
    foreach ($entry in @($HookSection)) {
        if ($null -eq $entry) { continue }
        $inner = $null
        $hooksProp = $entry.PSObject.Properties.Match('hooks')
        if ($hooksProp.Count -gt 0) {
            $inner = $entry.hooks
        } else {
            $inner = $entry
        }
        foreach ($cmd in @($inner)) {
            if ($null -eq $cmd) { continue }
            $typeProp = $cmd.PSObject.Properties.Match('type')
            $cmdProp = $cmd.PSObject.Properties.Match('command')
            if ($typeProp.Count -eq 0 -or $cmdProp.Count -eq 0) { continue }
            if ($cmd.type -ne 'command') { continue }
            $cmdText = [string]$cmd.command
            if ($cmdText -and ($cmdText -match $escapedHook)) {
                return $true
            }
        }
    }
    return $false
}

# --- 1. hookファイルをコピー ---
Write-Host "Copying hooks to $HooksDir ..."
if (-not (Test-Path $HooksDir)) {
    try {
        New-Item -ItemType Directory -Path $HooksDir -ErrorAction Stop | Out-Null
    } catch {
        Write-Host "  ERROR: Failed to create hooks directory: $($_.Exception.Message)"
        Write-Host "  Aborting install. Check permissions for $HooksDir"
        exit 1
    }
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
        try {
            Copy-Item -Path $src -Destination $dst -Force -ErrorAction Stop
            Write-Host "  Copied: $hook"
        } catch {
            Write-Host "  ERROR copying $hook : $($_.Exception.Message)"
            $copyErrors += $hook
        }
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
        try {
            New-Item -ItemType Directory -Path $skillDir -ErrorAction Stop | Out-Null
        } catch {
            Write-Host "  ERROR creating $skill/: $($_.Exception.Message)"
            $skillErrors += $skill
            continue
        }
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
    Write-Host ""
    Write-Host "Install complete (hooks copied; settings.json check skipped)."
    exit 0
}

# settings.json が壊れた JSON でも全体を落とさない:
# 読み込み / パース失敗時は登録確認だけスキップして手動追加を案内する。
$settings = $null
try {
    $settings = Get-Content $SettingsFile -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
} catch {
    $settingsError = $_.Exception.Message
    Write-Host "  ERROR reading settings.json: $settingsError"
    Write-Host "  Skipping registration check. Fix settings.json and re-run if needed."
    Write-Host ""
    Write-Host "  Expected hooks (Stop):"
    foreach ($hook in $stopHooks) {
        Write-Host "    python `"$HooksDir\$hook`""
    }
    Write-Host "  Expected hooks (UserPromptSubmit):"
    Write-Host "    python `"$HooksDir\document-update-detector.py`""
    Write-Host "    python `"$HooksDir\global-claude-md-appender.py`""
    Write-Host ""
    Write-Host "Install complete (with warnings — see above)."
    if ($copyErrors.Count -gt 0) {
        Write-Host "  Copy errors: $($copyErrors -join ', ')"
    }
    if ($skillErrors.Count -gt 0) {
        Write-Host "  Skill setup errors: $($skillErrors -join ', ')"
    }
    exit 0
}

$stopSection = $null
if ($settings.hooks -and $settings.hooks.Stop) {
    $stopSection = $settings.hooks.Stop
}

$alreadyRegistered = @()
$notRegistered = @()

foreach ($hook in $stopHooks) {
    if (Test-HookRegistered -HookSection $stopSection -HookFile $hook) {
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

$upsSection = $null
if ($settings.hooks -and $settings.hooks.UserPromptSubmit) {
    $upsSection = $settings.hooks.UserPromptSubmit
}

$upsAlreadyRegistered = @()
$upsNotRegistered = @()

foreach ($hook in $userPromptHooks) {
    if (Test-HookRegistered -HookSection $upsSection -HookFile $hook) {
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
Write-Host "  Hook resolution target (Python side): $([Environment]::GetFolderPath('UserProfile'))\.claude\CLAUDE.md"
Write-Host "  Installer target:                    $env:USERPROFILE\.claude\CLAUDE.md"
if ($copyErrors.Count -gt 0) {
    Write-Host "  Copy errors: $($copyErrors -join ', ')"
}
if ($skillErrors.Count -gt 0) {
    Write-Host "  Skill setup errors: $($skillErrors -join ', ')"
}
