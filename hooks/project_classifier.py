# -*- coding: utf-8 -*-
"""プロジェクト種別分類モジュール。
CWDのファイル構造・依存パッケージ・importパターンからプロジェクト種別を判定し、
適切なテストスキルのパス一覧を返す。
"""

from __future__ import annotations

import os
import re


PROJECT_TYPES = {
    "hook_plugin": {
        "name": "フック/プラグイン",
        "skill_path": "~/.claude/skills/tdd-guard/SKILL.md",
    },
    "ai_agent": {
        "name": "AIエージェント",
        "skill_path": "~/.claude/skills/agent-test/SKILL.md",
    },
    "web_app": {
        "name": "Webアプリ(ログイン込み)",
        "skill_path": "~/.claude/skills/e2e-auth-test/SKILL.md",
    },
    "backend_api": {
        "name": "バックエンドAPI",
        "skill_path": "~/.claude/skills/backend-test/SKILL.md",
    },
    "general": {
        "name": "汎用",
        "skill_path": "~/.claude/skills/tdd-guard/SKILL.md",
    },
}


def _read_text_if_exists(path: str) -> str:
    """ファイルが存在する場合のみUTF-8優先で読み込む。"""
    if not os.path.isfile(path):
        return ""
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            with open(path, "r", encoding=encoding) as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def _read_head_lines(path: str, max_lines: int = 30) -> str:
    """Pythonファイルの先頭数行だけを読み込む。"""
    if not os.path.isfile(path):
        return ""
    lines = []
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            with open(path, "r", encoding=encoding) as f:
                for index, line in enumerate(f):
                    if index >= max_lines:
                        break
                    lines.append(line)
            return "".join(lines)
        except (OSError, UnicodeDecodeError):
            lines = []
            continue
    return ""


def _has_any_pattern(text: str, patterns: list[str]) -> bool:
    """複数パターンのいずれかが含まれるかを判定する。"""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _collect_python_files(cwd: str) -> list[str]:
    """指定ルールに従ってスキャン対象のPythonファイル一覧を集める。"""
    collected = []
    hooks_dir = os.path.join(cwd, "hooks")

    if os.path.isdir(hooks_dir):
        for entry in sorted(os.listdir(hooks_dir)):
            path = os.path.join(hooks_dir, entry)
            if os.path.isfile(path) and entry.endswith(".py"):
                collected.append(path)

    for entry in sorted(os.listdir(cwd)):
        path = os.path.join(cwd, entry)
        if os.path.isfile(path) and entry.endswith(".py"):
            collected.append(path)

    return collected


def _collect_file_names(cwd: str) -> list[str]:
    """ルート直下とhooks配下のファイル名を集める。"""
    names = []

    for entry in os.listdir(cwd):
        names.append(entry)

    hooks_dir = os.path.join(cwd, "hooks")
    if os.path.isdir(hooks_dir):
        for entry in os.listdir(hooks_dir):
            names.append(entry)

    return names


def _expand_skill_path(path: str) -> str:
    """スキルパスのホームディレクトリを展開する。"""
    return os.path.expanduser(path)


def classify_project_type(cwd: str) -> list[tuple[str, str]]:
    """
    CWDを解析してプロジェクト種別を判定し、(種別名, スキルパス) のリストを返す。

    複数種別のシグナル数が同数の場合は全種別を返す（複数返し）。
    シグナルが何も検出されない場合はフォールバック（汎用TDD）を返す。
    毎回ステートレスにスキャンする（キャッシュなし）。

    Args:
        cwd: カレントワーキングディレクトリのパス

    Returns:
        [(種別名, スキルパス), ...] のリスト。最低1要素（フォールバック）を保証。
    """
    scores = {
        "hook_plugin": 0,
        "ai_agent": 0,
        "web_app": 0,
        "backend_api": 0,
    }

    if not cwd or not os.path.isdir(cwd):
        fallback = PROJECT_TYPES["general"]
        return [(fallback["name"], _expand_skill_path(fallback["skill_path"]))]

    requirements_text = _read_text_if_exists(os.path.join(cwd, "requirements.txt"))
    pyproject_text = _read_text_if_exists(os.path.join(cwd, "pyproject.toml"))
    package_json_text = _read_text_if_exists(os.path.join(cwd, "package.json"))
    dependency_text = "\n".join([requirements_text, pyproject_text, package_json_text])

    python_heads = [_read_head_lines(path, max_lines=30) for path in _collect_python_files(cwd)]
    python_head_text = "\n".join(python_heads)
    file_names = _collect_file_names(cwd)

    # ディレクトリ存在シグナル
    if os.path.isdir(os.path.join(cwd, "hooks")):
        scores["hook_plugin"] += 1
    if os.path.isdir(os.path.join(cwd, ".claude")):
        scores["ai_agent"] += 1

    # フック/プラグイン判定
    if re.search(r"\bhook_utils\b", python_head_text, re.IGNORECASE):
        scores["hook_plugin"] += 1
    if re.search(r"\bscore\s*=", python_head_text, re.IGNORECASE):
        scores["hook_plugin"] += 1
    if re.search(r"\bblock\s*=", python_head_text, re.IGNORECASE):
        scores["hook_plugin"] += 1
    if any(re.search(r".*_hook\.py$", name, re.IGNORECASE) for name in file_names):
        scores["hook_plugin"] += 1

    # AIエージェント判定
    if _has_any_pattern(
        python_head_text,
        [
            r"^\s*import\s+openai\b",
            r"^\s*import\s+anthropic\b",
            r"^\s*from\s+letta\b",
        ],
    ):
        scores["ai_agent"] += 1
    if any("agent" in name.lower() for name in file_names):
        scores["ai_agent"] += 1
    if re.search(r"\bMCP\b", python_head_text):
        scores["ai_agent"] += 1

    # Webアプリ判定
    if re.search(r"\bplaywright\b", dependency_text, re.IGNORECASE):
        scores["web_app"] += 1
    if re.search(r"\bcypress\b", dependency_text, re.IGNORECASE):
        scores["web_app"] += 1
    if re.search(r"^\s*from\s+playwright\b", python_head_text, re.IGNORECASE | re.MULTILINE):
        scores["web_app"] += 1
    if any(re.search(r"(auth|session|login)", name, re.IGNORECASE) for name in file_names):
        scores["web_app"] += 1
    if any(re.search(r"\.spec\.(ts|tsx|js|jsx)$", name, re.IGNORECASE) for name in file_names):
        scores["web_app"] += 1

    # バックエンドAPI判定
    if re.search(r"\bfastapi\b", dependency_text, re.IGNORECASE):
        scores["backend_api"] += 1
    if re.search(r"\bdjango\b", dependency_text, re.IGNORECASE):
        scores["backend_api"] += 1
    if re.search(r"\bflask\b", dependency_text, re.IGNORECASE):
        scores["backend_api"] += 1
    if re.search(r"\bAPIRouter\b", python_head_text):
        scores["backend_api"] += 1
    if re.search(r"@app\.route\b", python_head_text):
        scores["backend_api"] += 1
    if re.search(r"^\s*from\s+fastapi\b", python_head_text, re.IGNORECASE | re.MULTILINE):
        scores["backend_api"] += 1

    max_score = max(scores.values()) if scores else 0
    if max_score <= 0:
        fallback = PROJECT_TYPES["general"]
        return [(fallback["name"], _expand_skill_path(fallback["skill_path"]))]

    results = []
    for key in ("hook_plugin", "ai_agent", "web_app", "backend_api"):
        if scores[key] == max_score:
            project = PROJECT_TYPES[key]
            results.append((project["name"], _expand_skill_path(project["skill_path"])))

    if results:
        return results

    fallback = PROJECT_TYPES["general"]
    return [(fallback["name"], _expand_skill_path(fallback["skill_path"]))]
