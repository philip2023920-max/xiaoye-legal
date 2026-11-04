class_name GameSettings
extends RefCounted
## 玩家設定（施工單 21，ADR-0015 D25／D27）：供應商、模型、戰後檢討模型、語言、預算、思考深度、參謀長包。
## 存 user://settings.json；金鑰不在這裡（服務端 .env）。純函式：讀、存、正規化、轉成服務的 /settings 與啟動引數。

const PATH := "user://settings.json"
const PROVIDERS := ["fake", "anthropic", "ollama", "openai", "deepseek", "openrouter"]
const LANGS := ["zh-TW", "zh-CN", "en"]
const EFFORTS := ["", "low", "medium", "high"]
const DEFAULTS := {"provider": "fake", "model": "", "aar_provider": "", "aar_model": "", "lang": "zh-TW", "budget_usd": -1.0, "effort": "", "harness": "default"}

## 補預設、擋壞值（非法供應商 → fake、非法語言 → zh-TW、預算非數字 → 不設、非法 effort → 預設）；多的鍵丟掉。
static func normalize(d: Dictionary) -> Dictionary:
	var out := DEFAULTS.duplicate()
	var provider := str(d.get("provider", out["provider"]))
	out["provider"] = provider if provider in PROVIDERS else "fake"
	out["model"] = str(d.get("model", "")).strip_edges()
	var aar_provider := str(d.get("aar_provider", ""))
	out["aar_provider"] = aar_provider if aar_provider in PROVIDERS else ""
	out["aar_model"] = str(d.get("aar_model", "")).strip_edges()
	var lang := str(d.get("lang", out["lang"]))
	out["lang"] = lang if lang in LANGS else "zh-TW"
	var b: Variant = d.get("budget_usd", -1.0)
	out["budget_usd"] = float(b) if (b is float or b is int) else -1.0
	if out["budget_usd"] < 0.0:
		out["budget_usd"] = -1.0
	var effort := str(d.get("effort", ""))
	out["effort"] = effort if effort in EFFORTS else ""
	var harness := str(d.get("harness", "default")).strip_edges()
	out["harness"] = harness if harness != "" else "default"
	return out

static func load(path: String = PATH) -> Dictionary:
	if not FileAccess.file_exists(path):
		return DEFAULTS.duplicate()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (parsed is Dictionary):
		push_warning("設定檔壞了，用預設：%s" % path)
		return DEFAULTS.duplicate()
	return normalize(parsed)

static func save(d: Dictionary, path: String = PATH) -> bool:
	var real := ProjectSettings.globalize_path(path)
	var dir := real.get_base_dir()
	if not DirAccess.dir_exists_absolute(dir):
		DirAccess.make_dir_recursive_absolute(dir)
	var f := FileAccess.open(real, FileAccess.WRITE)
	if f == null:
		push_error("存不了設定：%s（%s）" % [real, error_string(FileAccess.get_open_error())])
		return false
	f.store_string(JSON.stringify(normalize(d), "  "))
	f.close()
	return true

## POST /settings 的 body（§16）：空字串的欄位不送（服務會保留原設定）；預算 <0 送 -1＝取消預算。
static func service_body(d: Dictionary) -> Dictionary:
	var s := normalize(d)
	var body := {"provider": s["provider"], "lang": s["lang"], "budget_usd": s["budget_usd"]}
	if s["model"] != "":
		body["model"] = s["model"]
	if s["effort"] != "":
		body["effort"] = s["effort"]
	if s["aar_provider"] != "":
		body["aar_provider"] = s["aar_provider"]
	if s["aar_model"] != "":
		body["aar_model"] = s["aar_model"]
	return body

## 啟動服務的額外引數（供應商另外由 ChiefClient.launch 帶）。
static func launch_args(d: Dictionary) -> PackedStringArray:
	var s := normalize(d)
	var args := PackedStringArray(["--harness", s["harness"], "--lang", s["lang"]])
	if s["model"] != "":
		args.append_array(PackedStringArray(["--model", s["model"]]))
	if s["budget_usd"] >= 0.0:
		args.append_array(PackedStringArray(["--budget", str(s["budget_usd"])]))
	if s["effort"] != "":
		args.append_array(PackedStringArray(["--effort", s["effort"]]))
	if s["aar_provider"] != "":
		args.append_array(PackedStringArray(["--aar-provider", s["aar_provider"]]))
	if s["aar_model"] != "":
		args.append_array(PackedStringArray(["--aar-model", s["aar_model"]]))
	return args

## 金鑰狀態一句話（D25：只顯示已設定／未設定；flags 來自服務 /health 的 keys）。
static func key_status_text(provider: String, flags: Dictionary) -> String:
	match provider:
		"fake":
			return TranslationServer.translate("UI_KEY_NOT_NEEDED")
		"openrouter":
			return TranslationServer.translate("UI_KEY_UNCHECKED")
		"ollama":
			return TranslationServer.translate("UI_KEY_OLLAMA_SET") if bool(flags.get("ollama", false)) else TranslationServer.translate("UI_KEY_OLLAMA_UNSET")
		_:
			return TranslationServer.translate("UI_KEY_SET") if bool(flags.get(provider, false)) else TranslationServer.translate("UI_KEY_UNSET")

static func is_local_provider(provider: String) -> bool:
	return provider == "fake" or provider == "ollama"
