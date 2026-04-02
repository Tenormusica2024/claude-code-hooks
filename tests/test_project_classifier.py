# -*- coding: utf-8 -*-
"""project_classifier.py のユニットテスト"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT_DIR / "hooks"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from project_classifier import classify_project_type


def _assert_result_shape(result: list[tuple[str, str]]) -> None:
    """返り値の基本構造を検証する。"""
    assert isinstance(result, list)
    assert result
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], str)
        assert isinstance(item[1], str)


def test_hook_plugin_detection(tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "sample_hook.py").write_text(
        "# -*- coding: utf-8 -*-\n"
        "import hook_utils\n"
        "score = 10\n"
        "block = True\n",
        encoding="utf-8",
    )

    result = classify_project_type(str(tmp_path))

    _assert_result_shape(result)
    assert result == [
        (
            "フック/プラグイン",
            os.path.expanduser("~/.claude/skills/tdd-guard/SKILL.md"),
        )
    ]


def test_ai_agent_detection(tmp_path):
    (tmp_path / "assistant_agent.py").write_text(
        "import openai\n"
        "MCP = 'enabled'\n",
        encoding="utf-8",
    )

    result = classify_project_type(str(tmp_path))

    _assert_result_shape(result)
    assert result == [
        (
            "AIエージェント",
            os.path.expanduser("~/.claude/skills/agent-test/SKILL.md"),
        )
    ]


def test_web_app_detection(tmp_path):
    (tmp_path / "requirements.txt").write_text("playwright==1.0.0\n", encoding="utf-8")

    result = classify_project_type(str(tmp_path))

    _assert_result_shape(result)
    assert result == [
        (
            "Webアプリ(ログイン込み)",
            os.path.expanduser("~/.claude/skills/e2e-auth-test/SKILL.md"),
        )
    ]


def test_backend_api_detection(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi==0.110.0\n", encoding="utf-8")

    result = classify_project_type(str(tmp_path))

    _assert_result_shape(result)
    assert result == [
        (
            "バックエンドAPI",
            os.path.expanduser("~/.claude/skills/backend-test/SKILL.md"),
        )
    ]


def test_fallback_detection(tmp_path):
    (tmp_path / "README.md").write_text("no signals here\n", encoding="utf-8")

    result = classify_project_type(str(tmp_path))

    _assert_result_shape(result)
    assert result == [
        (
            "汎用",
            os.path.expanduser("~/.claude/skills/tdd-guard/SKILL.md"),
        )
    ]


def test_multiple_signals_returns_all(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "fastapi==0.110.0\nplaywright==1.0.0\n",
        encoding="utf-8",
    )

    result = classify_project_type(str(tmp_path))

    _assert_result_shape(result)
    assert result == [
        (
            "Webアプリ(ログイン込み)",
            os.path.expanduser("~/.claude/skills/e2e-auth-test/SKILL.md"),
        ),
        (
            "バックエンドAPI",
            os.path.expanduser("~/.claude/skills/backend-test/SKILL.md"),
        ),
    ]


def test_empty_cwd(tmp_path):
    result = classify_project_type(str(tmp_path))

    _assert_result_shape(result)
    assert result == [
        (
            "汎用",
            os.path.expanduser("~/.claude/skills/tdd-guard/SKILL.md"),
        )
    ]
