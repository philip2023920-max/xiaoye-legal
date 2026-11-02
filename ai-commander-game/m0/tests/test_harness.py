"""施工單 07 驗收：參謀長包匯出／匯入。"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from chief.board import BoardError
from chief.harness import export_harness, import_harness, load_harness

ROOT = Path(__file__).resolve().parent.parent


def test_export_import_roundtrip(tmp_path):
    z = export_harness("default", tmp_path / "d.zip", root=ROOT / "harness")
    names = zipfile.ZipFile(z).namelist()
    assert "manifest.json" in names and "doctrine.md" in names and "prompts/chief_system.md" in names
    assert not any(".env" in n for n in names)
    h = import_harness(z, root=tmp_path / "h", rename="copy")
    assert h.name == "copy" and h.doctrine_path.exists() and h.prompt_path is not None
    assert json.loads((tmp_path / "h" / "copy" / "manifest.json").read_text(encoding="utf-8"))["name"] == "copy"
    with pytest.raises(BoardError):
        import_harness(z, root=tmp_path / "h", rename="copy")        # 已存在且沒 overwrite


def test_import_rejects_bad_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("readme.txt", "x")
    with pytest.raises(BoardError) as err:
        import_harness(bad, root=tmp_path / "h")
    assert "manifest.json" in str(err.value)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", json.dumps({"name": "x"})); z.writestr("doctrine.md", "# d"); z.writestr("../../escape.txt", "x")
    with pytest.raises(BoardError) as err:
        import_harness(evil, root=tmp_path / "h")
    assert "不安全" in str(err.value)


def test_missing_harness_lists_available():
    with pytest.raises(BoardError) as err:
        load_harness("nope", root=ROOT / "harness")
    assert "default" in str(err.value)
