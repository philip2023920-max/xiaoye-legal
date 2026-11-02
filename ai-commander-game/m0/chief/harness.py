"""參謀長包（施工單 07）：harness/<名稱>/ 的匯出、匯入與載入。金鑰永遠不在包裡。

包內：manifest.json、doctrine.md、prompts/chief_system.md、evals/（戰例庫與成績）。
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from .board import BoardError

HARNESS_ROOT = Path("harness")
REQUIRED = ("manifest.json", "doctrine.md")
NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
EXPORT_SKIP_SUFFIXES = (".prev.md",)
EXPORT_SKIP_NAMES = ("prev.json", ".DS_Store", "Thumbs.db")
EXPORT_SKIP_DIRS = ("__pycache__",)
ZIP_MAX_ENTRIES = 200
ZIP_MAX_FILE = 5 * 1024 * 1024
ZIP_MAX_TOTAL = 50 * 1024 * 1024


def _inside(base: Path, rel: str) -> Path:
    """manifest 裡的相對路徑必須留在包內；絕對路徑或 .. 一律拒絕（防止把系統檔案當準則送進 LLM）。"""
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts or rel.startswith(("/", "\\")):
        raise BoardError(f"參謀長包的檔案路徑不合法：「{rel}」（只能是包內的相對路徑）")
    target = (base / rel).resolve()
    base_r = base.resolve()
    if target != base_r and base_r not in target.parents:
        raise BoardError(f"參謀長包的檔案路徑跳出包外：「{rel}」")
    return base / rel


class Manifest(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,40}$")
    version: int = Field(1, ge=1)
    author: str = ""
    language: str = "en"
    scale: str = "battle"
    files: dict[str, str] = Field(default_factory=dict)
    suggested_provider: dict = Field(default_factory=dict)


@dataclass
class Harness:
    name: str
    dir: Path
    manifest: Manifest

    @property
    def doctrine_path(self) -> Path:
        return _inside(self.dir, self.manifest.files.get("doctrine", "doctrine.md"))

    @property
    def prompt_path(self) -> Path | None:
        p = _inside(self.dir, self.manifest.files.get("system_prompt", "prompts/chief_system.md"))
        return p if p.exists() else None

    @property
    def evals_dir(self) -> Path:
        return _inside(self.dir, self.manifest.files.get("evals", "evals/"))


def load_harness(name: str, root: str | Path = HARNESS_ROOT) -> Harness:
    d = Path(root) / name
    mp = d / "manifest.json"
    if not mp.exists():
        raise BoardError(f"找不到參謀長包「{name}」（{mp}）。可用：{', '.join(p.name for p in Path(root).glob('*/') if (p / 'manifest.json').exists()) or '（無）'}")
    try:
        manifest = Manifest.model_validate(json.loads(mp.read_text(encoding="utf-8-sig")))
    except (json.JSONDecodeError, ValidationError) as err:
        raise BoardError(f"參謀長包「{name}」的 manifest.json 有問題：{str(err)[:200]}") from None
    h = Harness(name=name, dir=d, manifest=manifest)
    for key in ("doctrine", "system_prompt", "evals"):   # 三條路徑都先檢查一遍，壞的包在載入時就擋
        _inside(d, manifest.files.get(key, {"doctrine": "doctrine.md", "system_prompt": "prompts/chief_system.md", "evals": "evals/"}[key]))
    if not h.doctrine_path.exists():
        raise BoardError(f"參謀長包「{name}」缺少作戰準則檔")
    return h


def export_harness(name: str, out_zip: str | Path, root: str | Path = HARNESS_ROOT) -> Path:
    h = load_harness(name, root)
    out = Path(out_zip)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(h.dir.rglob("*")):
            rel = p.relative_to(h.dir)
            if not p.is_file() or p.is_symlink():
                continue
            if any(part in EXPORT_SKIP_DIRS for part in rel.parts) or p.name in EXPORT_SKIP_NAMES \
                    or p.name.endswith(EXPORT_SKIP_SUFFIXES) or ".env" in p.name:
                continue   # 不帶上一版、暫存、快取、金鑰
            z.write(p, rel.as_posix())
    return out


def import_harness(zip_path: str | Path, root: str | Path = HARNESS_ROOT, rename: str | None = None, overwrite: bool = False) -> Harness:
    zp = Path(zip_path)
    if not zp.exists():
        raise BoardError(f"找不到 zip：{zp}")
    if rename is not None and not NAME_RE.match(rename):
        raise BoardError(f"包名稱「{rename}」不合法（只能英數、底線、連字號，最長 40）")
    with zipfile.ZipFile(zp) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        for req in REQUIRED:
            if req not in names:
                raise BoardError(f"zip 裡缺少 {req}，不是合法的參謀長包")
        if len(infos) > ZIP_MAX_ENTRIES or sum(i.file_size for i in infos) > ZIP_MAX_TOTAL or any(i.file_size > ZIP_MAX_FILE for i in infos):
            raise BoardError("zip 太大或檔案太多，不像參謀長包（上限 200 個檔、單檔 5 MB、總共 50 MB）")
        for n in names:  # zip 路徑安全：不准跳出資料夾
            if n.startswith(("/", "\\")) or ".." in Path(n).parts or (len(n) > 1 and n[1] == ":"):
                raise BoardError(f"zip 內有不安全的路徑：{n}")
        try:
            manifest = Manifest.model_validate(json.loads(z.read("manifest.json").decode("utf-8-sig")))
        except (json.JSONDecodeError, ValidationError) as err:
            raise BoardError(f"zip 的 manifest.json 有問題：{str(err)[:200]}") from None
        name = rename or manifest.name
        root_p = Path(root)
        dest = root_p / name
        if dest.exists() and not overwrite:
            raise BoardError(f"參謀長包「{name}」已存在；加 --overwrite 覆蓋或 --rename 改名")
        # 先解到暫存夾並驗證 manifest 路徑，全部合格才搬進 root
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / name
            stage.mkdir(parents=True)
            z.extractall(stage)
            if rename:
                manifest.name = rename
                (stage / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            load_harness(name, Path(tmp))   # 會檢查 files.* 路徑與準則存在
            root_p.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(stage, dest)
    return load_harness(name, root)
