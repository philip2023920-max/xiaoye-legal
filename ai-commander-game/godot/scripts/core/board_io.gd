class_name BoardIO
extends RefCounted
## 讀戰情板 JSON（Board v0.2，合約在 docs/09-board-schema.md）。
##
## M1 開發期直接讀隔壁 m0/ 的樣板與規則表（同一份真相，ADR-0014）：
## 路徑寫成 "m0://samples/board_start.json"。匯出成遊戲時再改成 res://data。

const SCHEMA_VERSION := "0.2"

static func m0_dir() -> String:
	# res:// 的實體路徑是 ai-commander-game/godot/，m0 在旁邊
	return ProjectSettings.globalize_path("res://").path_join("../m0").simplify_path()

static func resolve(path: String) -> String:
	if path.begins_with("m0://"):
		return m0_dir().path_join(path.trim_prefix("m0://"))
	return path

static func load_json(path: String) -> Dictionary:
	var real := resolve(path)
	if not FileAccess.file_exists(real):
		push_error("找不到檔案：%s" % real)
		return {}
	var f := FileAccess.open(real, FileAccess.READ)
	if f == null:
		push_error("開不了檔案：%s（%s）" % [real, error_string(FileAccess.get_open_error())])
		return {}
	var text := f.get_as_text()   # get_as_text 已去掉 UTF-8 BOM
	f.close()
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("%s 不是合法的 JSON 物件" % real)
		return {}
	return parsed

## 讀戰情板並檢查版本；錯就回空字典並 push_error（人話）。
static func load_board(path: String) -> Dictionary:
	var board := load_json(path)
	if board.is_empty():
		return board
	var version := str(board.get("schema_version", ""))
	if version != SCHEMA_VERSION:
		push_error("戰情板版本「%s」不是 M1 支援的「%s」（%s）" % [version, SCHEMA_VERSION, path])
		return {}
	if not (board.has("map") and board["map"].has("sectors")):
		push_error("戰情板缺少 map.sectors（%s）" % path)
		return {}
	return board
