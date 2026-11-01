"""環境體檢：不呼叫任何付費 API，只檢查本機設定是否齊全。

用法：uv run python -m chief.doctor
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


def mask(v: str) -> str:
    return v[:7] + "…" + v[-4:] if len(v) > 12 else "（已設定）"


def main() -> int:
    ok = True
    env_path = Path(".env")
    print(f"Python {sys.version.split()[0]}")
    if env_path.exists():
        load_dotenv(env_path)
        print("✅ .env 存在")
    else:
        print("⚠️ 找不到 .env（複製 .env.example 後跑 tools/capture_keys）")
        ok = False

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key.startswith("sk-ant-"):
        print(f"✅ ANTHROPIC_API_KEY {mask(key)}")
    elif key:
        print("⚠️ ANTHROPIC_API_KEY 格式不像 Anthropic 金鑰（應以 sk-ant- 開頭）")
        ok = False
    else:
        print("⚠️ ANTHROPIC_API_KEY 未設定")
        ok = False

    for opt in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        v = os.getenv(opt, "")
        print(f"{'✅' if v else '➖'} {opt} {'已設定' if v else '未設定（選用）'}")

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "")
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=3) as r:
            import json
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
        print(f"✅ Ollama 在 {host}，已下載模型：{', '.join(names) or '（無）'}")
        if model and not any(n.startswith(model) for n in names):
            print(f"⚠️ OLLAMA_MODEL={model} 尚未下載，請執行：ollama pull {model}")
            ok = False
    except (urllib.error.URLError, OSError, ValueError):
        print(f"⚠️ 連不到 Ollama（{host}）。請確認已安裝並啟動 Ollama")
        ok = False

    print("\n體檢結果：", "全部通過 ✅" if ok else "有項目要處理 ⚠️")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
