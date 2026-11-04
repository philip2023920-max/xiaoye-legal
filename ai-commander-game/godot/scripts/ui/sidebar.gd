class_name Sidebar
extends PanelContainer
## 戰情板側欄（施工單 18，ADR-0015 D26／D27）：右側可收合；部隊樹、事件流、參謀長區、據點與分數、天氣時段、本場費用。
## 資料只有一個來源：`BoardWriter.to_dict()` 那份字典（＋Battle 給的參謀長狀態），每 0.5 秒 refresh 一次，不另造資料。
## 點樹上的排或連 → unit_selected(unit_id)（Battle 把攝影機移過去；施工單 19 的接管面板也從這裡選）。
## 建樹／上色／文字都是靜態純函式，無頭測試直接驗。

signal unit_selected(unit_id: String)

const MAX_EVENTS := 12
const WIDTH := 340.0
const COLOR_GOOD := Color(0.55, 0.95, 0.55)
const COLOR_BAD := Color(1.0, 0.45, 0.45)
const COLOR_NEUTRAL := Color(0.85, 0.85, 0.85)
const COLOR_ORDER := Color(1.0, 0.93, 0.6)
const COLOR_SEIZED := Color(0.6, 0.85, 1.0)
const COLOR_WEATHER := Color(0.75, 0.75, 1.0)
const COLOR_INFO := Color(0.8, 0.8, 0.8)
const COLOR_PLAYER := Color(1.0, 0.8, 0.3)

var collapsed := false
var selected_unit := ""
var toggle_btn: Button
var body: VBoxContainer
var tree: Tree
var events_label: RichTextLabel
var chief_label: Label
var objectives_label: Label
var conditions_label: Label
var cost_label: Label
var _items := {}          # unit_id -> TreeItem
var refreshes := 0

func _init() -> void:
	name = "Sidebar"
	UiText.load_csv()
	anchor_left = 1.0
	anchor_right = 1.0
	anchor_top = 0.0
	anchor_bottom = 1.0
	offset_left = -WIDTH
	offset_right = 0.0
	offset_top = 0.0
	offset_bottom = 0.0
	var root := VBoxContainer.new()
	root.name = "Root"
	add_child(root)
	toggle_btn = Button.new()
	toggle_btn.name = "Toggle"
	toggle_btn.text = tr("UI_SIDEBAR_COLLAPSE")
	toggle_btn.pressed.connect(toggle)
	root.add_child(toggle_btn)
	body = VBoxContainer.new()
	body.name = "Body"
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(body)
	_section(tr("UI_SECTION_UNITS"))
	tree = Tree.new()
	tree.name = "Units"
	tree.columns = 4
	tree.column_titles_visible = true
	tree.set_column_title(0, tr("UI_COL_UNIT"))
	tree.set_column_title(1, tr("UI_COL_STRENGTH"))
	tree.set_column_title(2, tr("UI_COL_STATE"))
	tree.set_column_title(3, tr("UI_COL_TASK"))
	tree.set_column_expand(0, true)
	tree.set_column_custom_minimum_width(1, 70)
	tree.set_column_custom_minimum_width(2, 48)
	tree.set_column_custom_minimum_width(3, 80)
	tree.hide_root = true
	tree.custom_minimum_size = Vector2(WIDTH - 16.0, 200.0)
	tree.item_selected.connect(_on_item_selected)
	body.add_child(tree)
	_section(tr("UI_SECTION_EVENTS"))
	events_label = RichTextLabel.new()
	events_label.name = "Events"
	events_label.bbcode_enabled = true
	events_label.scroll_following = true
	events_label.fit_content = false
	events_label.custom_minimum_size = Vector2(WIDTH - 16.0, 180.0)
	events_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(events_label)
	_section(tr("UI_SECTION_CHIEF"))
	chief_label = _label("Chief")
	_section(tr("UI_SECTION_OBJECTIVES"))
	objectives_label = _label("Objectives")
	_section(tr("UI_SECTION_CONDITIONS"))
	conditions_label = _label("Conditions")
	_section(tr("UI_SECTION_COST"))
	cost_label = _label("Cost")

func _section(title: String) -> void:
	var l := Label.new()
	l.text = "— %s —" % title
	l.add_theme_color_override("font_color", Color(0.7, 0.85, 1.0))
	body.add_child(l)

func _label(n: String) -> Label:
	var l := Label.new()
	l.name = n
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(WIDTH - 16.0, 0.0)
	body.add_child(l)
	return l

func toggle() -> void:
	collapsed = not collapsed
	body.visible = not collapsed
	toggle_btn.text = tr("UI_SIDEBAR_EXPAND") if collapsed else tr("UI_SIDEBAR_COLLAPSE")
	offset_left = -toggle_btn.get_combined_minimum_size().x - 16.0 if collapsed else -WIDTH

# ---- 純函式（測試直接驗）----

## 部隊樹的列：連在前、排掛在連底下；每列 {id, parent, name, strength, state, task, player, echelon}。
static func tree_rows(board: Dictionary) -> Array:
	var rows: Array = []
	for u in board.get("orbat", []):
		var task: Variant = u.get("task")
		rows.append({"id": str(u.get("id", "")), "parent": str(u.get("parent", "")) if u.get("parent") != null else "", "name": str(u.get("name", u.get("id", ""))),
			"strength": float(u.get("strength", 0.0)), "state": str(u.get("state", "idle")), "echelon": str(u.get("echelon", "platoon")),
			"task": task if task is Dictionary else {}, "player": str(u.get("controlled_by", "ai")) == "player"})
	return rows

## 戰力條：5 格 + 數字（0.80 → ████░ 0.80）。
static func strength_bar(x: float) -> String:
	var filled := clampi(int(round(x * 5.0)), 0, 5)
	return "█".repeat(filled) + "░".repeat(5 - filled) + " %.2f" % x

static func task_text(task: Dictionary) -> String:
	if task.is_empty():
		return TranslationServer.translate("UI_TASK_none")
	return "%s %s" % [TranslationServer.translate("UI_TASK_" + str(task.get("type", ""))), str(task.get("target", ""))]

static func state_text(state: String) -> String:
	var key := "UI_STATE_" + state
	var t := TranslationServer.translate(key)
	return state if t == key else t

## 事件上色：推翻後果 👍 綠／👎 紅／➖ 灰；參謀長令黃；易手藍；天氣紫；其他灰。
static func event_color(ev: Dictionary) -> Color:
	var text := str(ev.get("text", ""))
	var kind := str(ev.get("kind", ""))
	if text.contains("👍"):
		return COLOR_GOOD
	if text.contains("👎") or kind == "routed" or kind == "destroyed":
		return COLOR_BAD
	if text.contains("➖"):
		return COLOR_NEUTRAL
	if kind == "order" or kind == "override":
		return COLOR_ORDER
	if kind == "seized" or kind == "contact":
		return COLOR_SEIZED
	if kind == "weather":
		return COLOR_WEATHER
	return COLOR_INFO

## 最近 N 筆事件（舊→新），已組好 bbcode。
static func events_bbcode(events: Array, max_n: int = MAX_EVENTS) -> String:
	if events.is_empty():
		return TranslationServer.translate("UI_EVENTS_EMPTY")
	var start := maxi(0, events.size() - max_n)
	var lines: Array[String] = []
	for i in range(start, events.size()):
		var ev: Dictionary = events[i]
		lines.append("[color=#%s]%ds %s[/color]" % [event_color(ev).to_html(false), int(ev.get("t", 0)), str(ev.get("text", "")).replace("[", "［").replace("]", "］")])
	return "\n".join(lines)

static func objectives_text(board: Dictionary) -> String:
	var su := 0
	var se := 0
	var lines: Array[String] = []
	for o in board.get("objectives", []):
		var owner := str(o.get("owner", "none"))
		var v := int(o.get("value", 0))
		if owner == "us":
			su += v
		elif owner == "enemy":
			se += v
		var mark := "✔" if owner == "us" else ("✘" if owner == "enemy" else "")
		lines.append(TranslationServer.translate("UI_OBJECTIVE_LINE") % [str(o.get("id", "")), v, str(o.get("sector", "")), mark])
	return (TranslationServer.translate("UI_SCORE") % [su, se]) + "\n" + "\n".join(lines)

static func conditions_text(board: Dictionary, battle_seconds: int = 300) -> String:
	var wx := TranslationServer.translate("UI_WEATHER_" + str(board.get("weather", "clear")))
	var tod := TranslationServer.translate("UI_TOD_" + str(board.get("time_of_day", "day")))
	var t := int(board.get("t", 0))
	return "%s｜%s｜%s" % [wx, tod, TranslationServer.translate("UI_TIME_LEFT") % [t, maxi(0, battle_seconds - t)]]

## 參謀長區：狀態 / 最近評估 / 思考中 / 最近命令（chief 字典由 Battle 組：state, line, busy_s, orders[], ended）。
static func chief_text(chief: Dictionary) -> String:
	var state := str(chief.get("state", "off"))
	var lines: Array[String] = []
	if state == "off" or state == "offline":
		lines.append(TranslationServer.translate("UI_CHIEF_OFFLINE") if state == "off" else str(chief.get("line", "")))
	elif state == "starting":
		lines.append(TranslationServer.translate("UI_CHIEF_STARTING"))
	else:
		lines.append(str(chief.get("line", "")))
		if float(chief.get("busy_s", 0.0)) > 0.0:
			lines.append(TranslationServer.translate("UI_CHIEF_THINKING") % int(chief.get("busy_s", 0.0)))
		if str(chief.get("override_rate", "")) != "":
			lines.append(TranslationServer.translate("UI_OVERRIDE_RATE") % str(chief["override_rate"]))
		var orders: Array = chief.get("orders", [])
		lines.append(TranslationServer.translate("UI_CHIEF_LAST_ORDERS"))
		if orders.is_empty():
			lines.append(TranslationServer.translate("UI_CHIEF_NO_ORDERS"))
		for o in orders:
			lines.append("  %s" % str(o))
	return "\n".join(lines)

# ---- 更新 ----

## board＝BoardWriter.to_dict()；chief＝Battle.chief_sidebar_info()。
func refresh(board: Dictionary, chief: Dictionary = {}) -> void:
	refreshes += 1
	_rebuild_tree(board)
	events_label.text = events_bbcode(board.get("events", []))
	chief_label.text = chief_text(chief)
	objectives_label.text = objectives_text(board)
	conditions_label.text = conditions_text(board)
	cost_label.text = TranslationServer.translate("UI_COST_LINE") % [float(chief.get("cost", 0.0)), int(chief.get("ticks", 0))]
	if bool(chief.get("ended", false)):
		conditions_label.text += "｜" + TranslationServer.translate("UI_ENDED")

func _rebuild_tree(board: Dictionary) -> void:
	var rows := tree_rows(board)
	var ids := {}
	for r in rows:
		ids[r["id"]] = true
	for uid in _items.keys():          # 不在板上的（殲滅後被拿掉）移除
		if not ids.has(uid):
			var it: TreeItem = _items[uid]
			it.free()
			_items.erase(uid)
	var root := tree.get_root()
	if root == null:
		root = tree.create_item()
	for r in rows:                     # 先確保每列都有 item（連先於排，照板的順序）
		if not _items.has(r["id"]):
			var parent_item: TreeItem = _items.get(r["parent"], root) if r["parent"] != "" else root
			var it := tree.create_item(parent_item)
			it.set_metadata(0, r["id"])
			_items[r["id"]] = it
	for r in rows:
		var it: TreeItem = _items[r["id"]]
		var label: String = r["name"] + (" " + tr("UI_PLAYER_MARK") if r["player"] else "")
		it.set_text(0, label)
		it.set_text(1, strength_bar(r["strength"]))
		it.set_text(2, state_text(r["state"]))
		it.set_text(3, task_text(r["task"]))
		var col := COLOR_PLAYER if r["player"] else (COLOR_BAD if r["state"] in ["routed", "destroyed"] else Color.WHITE)
		for c in 4:
			it.set_custom_color(c, col)
		if r["echelon"] != "platoon":
			it.set_collapsed(false)

func unit_count() -> int:
	return _items.size()

func _on_item_selected() -> void:
	var it := tree.get_selected()
	if it == null:
		return
	selected_unit = str(it.get_metadata(0))
	unit_selected.emit(selected_unit)

## 測試或程式選取（等同點樹）。
func select_unit(unit_id: String) -> bool:
	if not _items.has(unit_id):
		return false
	var it: TreeItem = _items[unit_id]
	it.select(0)
	return true
