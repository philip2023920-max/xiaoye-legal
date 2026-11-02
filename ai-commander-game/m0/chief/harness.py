"""參謀長包（施工單 07）：harness/<名稱>/ 的匯出、匯入與載入。金鑰永遠不在包裡。

包內：manifest.json、doctrine.md、prompts/chief_system.md、evals/（戰例庫與成績）。
"""
from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from .board import BoardError

HARNESS_ROOT = Path("harness")
REQUIRED = ("manifest.json", "doctrine.md")


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
        return self.dir / self.manifest.files.get("doctrine", "doctrine.md")

    @property
    def prompt_path(self) -> Path | None:
        p = self.dir / self.manifest.files.get("system_prompt", "prompts/chief_system.md")
        return p if p.exists() else None

    @property
    def evals_dir(self) -> Path:
        return self.dir / self.manifest.files.get("evals", "evals/")


def load_harness(name: str, root: str | Path = HARNESS_ROOT) -> Harness:
    d = Path(root) / name
    mp = d / "manifest.json"
    if not mp.exists():
        raise BoardError(f"找不到參謀長包「{name}」（{mp}）。可用：{', '.join(p.name for p in Path(root).glob('*/') if (p / 'manifest.json').exists()) or '（無）'}")
    try:
        manifest = Manifest.model_validate(json.loads(mp.read_text(encoding="utf-8-sig")))
    except (json.JSONDecodeError, ValidationError) as err:
        raise BoardError(f"參謀長包「{name}」的 manifest.json 有問題：{str(err)[:200]}") from None
    if not (d / manifest.files.get("doctrine", "doctrine.md")).exists():
        raise BoardError(f"參謀長包「{name}」缺少作戰準則檔")
    return Harness(name=name, dir=d, manifest=manifest)


def export_harness(name: str, out_zip: str | Path, root: str | Path = HARNESS_ROOT) -> Path:
    h = load_harness(name, root)
    out = Path(out_zip)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(h.dir.rglob("*")):
            if p.is_file() and p.suffix != ".prev" and not p.name.endswith(".prev.md") and ".env" not in p.name:
                z.write(p, p.relative_to(h.dir).as_posix())
    return out


def import_harness(zip_path: str | Path, root: str | Path = HARNESS_ROOT, rename: str | None = None, overwrite: bool = False) -> Harness:
    zp = Path(zip_path)
    if not zp.exists():
        raise BoardError(f"找不到 zip：{zp}")
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        for req in REQUIRED:
            if req not in names:
                raise BoardError(f"zip 裡缺少 {req}，不是合法的參謀長包")
        for n in names:  # zip 路徑安全：不准跳出資料夾
            if n.startswith("/") or ".." in Path(n).parts:
                raise BoardError(f"zip 內有不安全的路徑：{n}")
        try:
            manifest = Manifest.model_validate(json.loads(z.read("manifest.json").decode("utf-8-sig")))
        except (json.JSONDecodeError, ValidationError) as err:
            raise BoardError(f"zip 的 manifest.json 有問題：{str(err)[:200]}") from None
        name = rename or manifest.name
        dest = Path(root) / name
        if dest.exists() and not overwrite:
            raise BoardError(f"參謀長包「{name}」已存在；加 --overwrite 覆蓋或 --rename 改名")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        z.extractall(dest)
        if rename:
            manifest.name = rename
            (dest / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return load_harness(name, root)
