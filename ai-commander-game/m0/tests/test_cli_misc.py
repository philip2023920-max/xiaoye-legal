"""測試審查補：harness／doctrine 子命令走 cli.main；.env.example 與程式讀取名稱逐字一致（施工單 04 第 6 條）。"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from chief.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_env_example_matches_code():
    keys = {l.split("=")[0].strip() for l in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
    assert keys == {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_HOST", "OLLAMA_MODEL"}   # 施工單 04 列的五個
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "chief").rglob("*.py"))
    for k in keys:
        assert k in code, f"{k} 在 .env.example 但程式沒讀"
    for k in set(re.findall(r'os\.getenv\("([A-Z_]+)"', code)):
        assert k in keys or k == "LITELLM_LOCAL_MODEL_COST_MAP", f"程式讀 {k} 但 .env.example 沒列"


def test_harness_and_doctrine_cli(tmp_path, monkeypatch, capsys):
    (tmp_path / "harness").mkdir()
    shutil.copytree(ROOT / "harness" / "default", tmp_path / "harness" / "default")
    monkeypatch.chdir(tmp_path)
    assert main(["harness", "list"]) == 0 and "default" in capsys.readouterr().out
    assert main(["harness", "export", "default", "--out", "d.zip"]) == 0 and (tmp_path / "d.zip").exists()
    assert main(["harness", "import", "--file", "d.zip", "--rename", "copy2"]) == 0 and (tmp_path / "harness" / "copy2" / "doctrine.md").exists()
    assert main(["harness", "import", "--file", "d.zip", "--rename", "copy2"]) == 1          # 已存在
    assert main(["doctrine", "show"]) == 0 and "Doctrine" in capsys.readouterr().out
    assert main(["doctrine", "undo"]) == 1                                                   # 沒有上一版
    doc = tmp_path / "harness" / "default" / "doctrine.md"
    doc.with_suffix(".prev.md").write_text("# old\n", encoding="utf-8")
    assert main(["doctrine", "undo"]) == 0 and doc.read_text(encoding="utf-8") == "# old\n"
