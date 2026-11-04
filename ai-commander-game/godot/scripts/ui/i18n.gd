class_name UiText
extends RefCounted
## UI 字串表（施工單 18，ADR-0015 D27）：`i18n/ui.csv` 三欄（zh_TW／zh_CN／en）一次寫齊，執行期載入成 TranslationServer 的翻譯。
## 不走 Godot 的 CSV 匯入器：不產生二進位 .translation、無頭測試不用先 --import，字串表也能直接 diff。
## 用法：UiText.load_csv() 一次；UiText.set_lang("zh-TW")；之後任何節點 tr("UI_SECTION_UNITS")。

const CSV_PATH := "res://i18n/ui.csv"
const LANGS := {"zh-TW": "zh_TW", "zh-CN": "zh_CN", "en": "en"}   # 服務／設定頁用 zh-TW，Godot 用 zh_TW
static var _loaded := false
static var keys: Array[String] = []

static func load_csv(path: String = CSV_PATH) -> int:
	if _loaded:
		return keys.size()
	var text := FileAccess.get_file_as_string(path)
	if text == "":
		push_error("讀不到 UI 字串表：%s" % path)
		return 0
	var lines := text.split("\n", false)
	var header := _split_csv(lines[0])
	var trs: Array[Translation] = []
	for i in range(1, header.size()):
		var t := Translation.new()
		t.locale = header[i].strip_edges()
		trs.append(t)
	keys = []
	for li in range(1, lines.size()):
		var row := _split_csv(lines[li])
		if row.is_empty() or row[0].strip_edges() == "":
			continue
		var key := row[0].strip_edges()
		keys.append(key)
		for i in range(1, mini(row.size(), header.size())):
			trs[i - 1].add_message(key, row[i])
	for t in trs:
		TranslationServer.add_translation(t)
	_loaded = true
	return keys.size()

## 接受 zh-TW／zh-CN／en（服務的寫法）或 Godot 的 zh_TW 等。
static func set_lang(lang: String) -> void:
	TranslationServer.set_locale(str(LANGS.get(lang, lang)))

## 簡單 CSV：逗號分欄，雙引號包起來的欄位內可有逗號，"" 代表一個引號。
static func _split_csv(line: String) -> PackedStringArray:
	var out := PackedStringArray()
	var cur := ""
	var quoted := false
	var i := 0
	while i < line.length():
		var ch := line[i]
		if quoted:
			if ch == '"':
				if i + 1 < line.length() and line[i + 1] == '"':
					cur += '"'
					i += 1
				else:
					quoted = false
			else:
				cur += ch
		elif ch == '"':
			quoted = true
		elif ch == ",":
			out.append(cur)
			cur = ""
		elif ch != "\r":
			cur += ch
		i += 1
	out.append(cur)
	return out
