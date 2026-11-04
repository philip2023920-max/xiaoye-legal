class_name SettingsPage
extends PanelContainer
## 設定頁（施工單 21，D25）：Esc 開關。供應商、模型、戰後檢討供應商／模型、語言、預算、思考深度、參謀長包；
## 金鑰只顯示「已設定／未設定（在 m0/.env）」。「儲存」→ saved(settings)（Battle 存檔、送 /settings、切語言）；「關閉」→ closed。

signal saved(settings: Dictionary)
signal closed

var provider_opt: OptionButton
var model_edit: LineEdit
var aar_provider_opt: OptionButton
var aar_model_edit: LineEdit
var lang_opt: OptionButton
var budget_spin: SpinBox
var effort_opt: OptionButton
var harness_edit: LineEdit
var key_label: Label
var note_label: Label
var save_btn: Button
var close_btn: Button
var key_flags := {}

func _init() -> void:
	name = "SettingsPage"
	UiText.load_csv()
	anchor_left = 0.3
	anchor_right = 0.7
	anchor_top = 0.12
	anchor_bottom = 0.88
	offset_left = 0.0
	offset_right = 0.0
	offset_top = 0.0
	offset_bottom = 0.0
	visible = false
	var root := VBoxContainer.new()
	root.name = "Root"
	add_child(root)
	var title := Label.new()
	title.text = tr("UI_SETTINGS_TITLE")
	title.add_theme_font_size_override("font_size", 22)
	root.add_child(title)
	provider_opt = _option(root, "UI_SET_PROVIDER", GameSettings.PROVIDERS)
	provider_opt.item_selected.connect(func(_i: int) -> void: _refresh_key())
	model_edit = _line(root, "UI_SET_MODEL", "UI_SET_MODEL_HINT")
	aar_provider_opt = _option(root, "UI_SET_AAR_PROVIDER", [""] + GameSettings.PROVIDERS)
	aar_model_edit = _line(root, "UI_SET_AAR_MODEL", "UI_SET_AAR_MODEL_HINT")
	lang_opt = _option(root, "UI_SET_LANG", GameSettings.LANGS)
	var budget_row := _row(root, "UI_SET_BUDGET")
	budget_spin = SpinBox.new()
	budget_spin.name = "Budget"
	budget_spin.min_value = -1.0
	budget_spin.max_value = 100.0
	budget_spin.step = 0.01
	budget_spin.value = -1.0
	budget_spin.custom_minimum_size = Vector2(160.0, 0.0)
	budget_row.add_child(budget_spin)
	var budget_note := Label.new()
	budget_note.text = tr("UI_SET_BUDGET_HINT")
	budget_row.add_child(budget_note)
	effort_opt = _option(root, "UI_SET_EFFORT", GameSettings.EFFORTS)
	harness_edit = _line(root, "UI_SET_HARNESS", "")
	key_label = Label.new()
	key_label.name = "Key"
	key_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(key_label)
	note_label = Label.new()
	note_label.name = "Note"
	note_label.text = tr("UI_SET_NOTE")
	note_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note_label.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
	root.add_child(note_label)
	var actions := HBoxContainer.new()
	root.add_child(actions)
	save_btn = Button.new()
	save_btn.name = "Save"
	save_btn.text = tr("UI_SET_SAVE")
	save_btn.focus_mode = Control.FOCUS_NONE
	save_btn.pressed.connect(func() -> void: saved.emit(collect()))
	actions.add_child(save_btn)
	close_btn = Button.new()
	close_btn.name = "Close"
	close_btn.text = tr("UI_SET_CLOSE")
	close_btn.focus_mode = Control.FOCUS_NONE
	close_btn.pressed.connect(func() -> void: visible = false; closed.emit())
	actions.add_child(close_btn)

func _row(parent: Control, key: String) -> HBoxContainer:
	var row := HBoxContainer.new()
	var l := Label.new()
	l.text = tr(key)
	l.custom_minimum_size = Vector2(150.0, 0.0)
	row.add_child(l)
	parent.add_child(row)
	return row

func _option(parent: Control, key: String, items: Array) -> OptionButton:
	var row := _row(parent, key)
	var o := OptionButton.new()
	o.name = key
	o.focus_mode = Control.FOCUS_NONE
	for it in items:
		o.add_item(str(it) if str(it) != "" else tr("UI_SET_DEFAULT_OPTION"))
	row.add_child(o)
	return o

func _line(parent: Control, key: String, hint_key: String) -> LineEdit:
	var row := _row(parent, key)
	var e := LineEdit.new()
	e.name = key
	e.custom_minimum_size = Vector2(260.0, 0.0)
	if hint_key != "":
		e.placeholder_text = tr(hint_key)
	row.add_child(e)
	return e

static func _index_of(items: Array, value: String) -> int:
	var i := items.find(value)
	return i if i >= 0 else 0

func open(s: Dictionary, flags: Dictionary = {}) -> void:
	var n := GameSettings.normalize(s)
	key_flags = flags
	provider_opt.select(_index_of(GameSettings.PROVIDERS, n["provider"]))
	model_edit.text = n["model"]
	aar_provider_opt.select(_index_of([""] + GameSettings.PROVIDERS, n["aar_provider"]))
	aar_model_edit.text = n["aar_model"]
	lang_opt.select(_index_of(GameSettings.LANGS, n["lang"]))
	budget_spin.value = n["budget_usd"]
	effort_opt.select(_index_of(GameSettings.EFFORTS, n["effort"]))
	harness_edit.text = n["harness"]
	_refresh_key()
	visible = true

func set_key_flags(flags: Dictionary) -> void:
	key_flags = flags
	_refresh_key()

func _refresh_key() -> void:
	var provider := str(GameSettings.PROVIDERS[provider_opt.selected])
	key_label.text = tr("UI_SET_KEY") % GameSettings.key_status_text(provider, key_flags)

## 讀控制項 → 正規化後的設定。
func collect() -> Dictionary:
	var aar_items := [""] + GameSettings.PROVIDERS
	return GameSettings.normalize({"provider": GameSettings.PROVIDERS[provider_opt.selected], "model": model_edit.text,
		"aar_provider": aar_items[aar_provider_opt.selected], "aar_model": aar_model_edit.text,
		"lang": GameSettings.LANGS[lang_opt.selected], "budget_usd": budget_spin.value,
		"effort": GameSettings.EFFORTS[effort_opt.selected], "harness": harness_edit.text})
