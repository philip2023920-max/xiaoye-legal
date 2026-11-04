class_name OverridePanel
extends PanelContainer
## 推翻／接管面板（施工單 19）：左下角；選到排或連才出現。單位名與目前任務、六種任務按鈕、提示（點地圖選目標／點友軍）、
## 「接管」（照目前任務直轄）「放手」「取消」。按鈕只發訊號，真正下令在 Battle（它才有 Orbat 與參謀長客戶端）。

signal task_pressed(task: String)
signal takeover_pressed
signal release_pressed
signal cancel_pressed

const WIDTH := 420.0

var title_label: Label
var task_label: Label
var hint_label: Label
var task_buttons := {}      # task -> Button
var takeover_btn: Button
var release_btn: Button
var cancel_btn: Button
var shown_unit := ""

func _init() -> void:
	name = "OverridePanel"
	UiText.load_csv()
	anchor_left = 0.0
	anchor_right = 0.0
	anchor_top = 1.0
	anchor_bottom = 1.0
	offset_left = 12.0
	offset_right = 12.0 + WIDTH
	offset_top = -170.0
	offset_bottom = -12.0
	var root := VBoxContainer.new()
	add_child(root)
	title_label = Label.new()
	title_label.name = "Title"
	root.add_child(title_label)
	task_label = Label.new()
	task_label.name = "Task"
	root.add_child(task_label)
	var row := HBoxContainer.new()
	row.name = "Tasks"
	root.add_child(row)
	for t in Order.TASKS:
		var b := Button.new()
		b.name = t
		b.text = tr("UI_TASK_" + t)
		b.pressed.connect(func() -> void: task_pressed.emit(t))
		row.add_child(b)
		task_buttons[t] = b
	hint_label = Label.new()
	hint_label.name = "Hint"
	hint_label.add_theme_color_override("font_color", Color(1.0, 0.93, 0.6))
	root.add_child(hint_label)
	var row2 := HBoxContainer.new()
	row2.name = "Actions"
	root.add_child(row2)
	takeover_btn = Button.new()
	takeover_btn.name = "Takeover"
	takeover_btn.text = tr("UI_PANEL_TAKEOVER")
	takeover_btn.pressed.connect(func() -> void: takeover_pressed.emit())
	row2.add_child(takeover_btn)
	release_btn = Button.new()
	release_btn.name = "Release"
	release_btn.text = tr("UI_PANEL_RELEASE")
	release_btn.pressed.connect(func() -> void: release_pressed.emit())
	row2.add_child(release_btn)
	cancel_btn = Button.new()
	cancel_btn.name = "Cancel"
	cancel_btn.text = tr("UI_PANEL_CANCEL")
	cancel_btn.pressed.connect(func() -> void: cancel_pressed.emit())
	row2.add_child(cancel_btn)
	visible = false

## info：{id, name, echelon, task{type,target}|{}, controlled_by, state}；flow_state：OverrideFlow.state；picking_task：正在選目標的任務。
func show_unit(info: Dictionary, flow_state: String, picking_task: String = "") -> void:
	if info.is_empty():
		hide_panel()
		return
	shown_unit = str(info.get("id", ""))
	visible = true
	var player: bool = str(info.get("controlled_by", "ai")) == "player"
	title_label.text = "%s（%s）" % [str(info.get("name", shown_unit)), tr("UI_PANEL_PLAYER") if player else tr("UI_PANEL_AI")]
	task_label.text = tr("UI_PANEL_CURRENT_TASK") % Sidebar.task_text(info.get("task", {}) if info.get("task") is Dictionary else {})
	match flow_state:
		"picking_sector":
			hint_label.text = tr("UI_PANEL_PICK_SECTOR") % tr("UI_TASK_" + picking_task)
		"picking_unit":
			hint_label.text = tr("UI_PANEL_PICK_UNIT")
		_:
			hint_label.text = tr("UI_PANEL_HINT")
	takeover_btn.disabled = player
	release_btn.disabled = not player
	cancel_btn.visible = flow_state == "picking_sector" or flow_state == "picking_unit"
	for t in task_buttons.keys():
		task_buttons[t].disabled = str(info.get("state", "")) == "destroyed"

func hide_panel() -> void:
	shown_unit = ""
	visible = false
