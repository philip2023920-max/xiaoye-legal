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


def test_manifest_paths_must_stay_inside_pack(tmp_path):
    for bad in ("/etc/hostname", "../x.md"):
        z = tmp_path / "p.zip"
        with zipfile.ZipFile(z, "w") as zz:
            zz.writestr("manifest.json", json.dumps({"name": "evil", "files": {"doctrine": bad}})); zz.writestr("doctrine.md", "# d")
        with pytest.raises(BoardError) as err:
            import_harness(z, root=tmp_path / "h", overwrite=True)
        assert "路徑" in str(err.value) and not (tmp_path / "h" / "evil").exists()


def test_rename_must_be_safe_and_nothing_escapes(tmp_path):
    z = export_harness("default", tmp_path / "d.zip", root=ROOT / "harness")
    with pytest.raises(BoardError):
        import_harness(z, root=tmp_path / "h", rename="../escaped")
    assert not (tmp_path / "escaped").exists() and not (tmp_path / "h").exists()


def test_export_excludes_prev_and_caches(tmp_path):
    src = tmp_path / "src" / "p"; (src / "evals").mkdir(parents=True); (src / "__pycache__").mkdir()
    (src / "manifest.json").write_text(json.dumps({"name": "p"}), encoding="utf-8"); (src / "doctrine.md").write_text("# d", encoding="utf-8")
    (src / "doctrine.prev.md").write_text("old", encoding="utf-8"); (src / "evals" / "prev.json").write_text("{}", encoding="utf-8")
    (src / "evals" / "last.json").write_text("{}", encoding="utf-8"); (src / "__pycache__" / "x.pyc").write_bytes(b"x")
    names = zipfile.ZipFile(export_harness("p", tmp_path / "p.zip", root=tmp_path / "src")).namelist()
    assert set(names) == {"manifest.json", "doctrine.md", "evals/last.json"}


def test_missing_harness_lists_available():
    with pytest.raises(BoardError) as err:
        load_harness("nope", root=ROOT / "harness")
    assert "default" in str(err.value)
