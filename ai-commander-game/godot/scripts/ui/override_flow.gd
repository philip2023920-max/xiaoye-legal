class_name OverrideFlow
extends RefCounted
## 推翻／接管的狀態機（施工單 19，ADR-0015 D29）：純邏輯、不碰節點，面板與地圖點選都只改它。
##   idle ──select(unit)──▶ selected ──choose_task(task)──▶ picking_sector（support 則 picking_unit）
##   ──pick_sector／pick_unit──▶ ready（order() 可拿）；cancel() 回 selected；clear() 回 idle。
## 目標合法性（分區存在、support 是存活友軍）由 Orbat.order_problem 在下令時擋，這裡只管流程。

signal changed(state: String)

var state := "idle"      # idle / selected / picking_sector / picking_unit / ready
var unit_id := ""
var task := ""
var target := ""

func select(uid: String) -> void:
	if uid == "":
		clear()
		return
	unit_id = uid
	task = ""
	target = ""
	_go("selected")

func choose_task(t: String) -> bool:
	if unit_id == "" or not (t in Order.TASKS):
		return false
	task = t
	target = ""
	_go("picking_unit" if t == "support" else "picking_sector")
	return true

func pick_sector(sector_id: String) -> bool:
	if state != "picking_sector" or sector_id == "":
		return false
	target = sector_id
	_go("ready")
	return true

func pick_unit(uid: String) -> bool:
	if state != "picking_unit" or uid == "" or uid == unit_id:
		return false
	target = uid
	_go("ready")
	return true

## ready 時的命令；拿走後回到 selected（單位仍選著，可以再下一道）。
func take_order() -> Order:
	if state != "ready":
		return null
	var o := Order.make(unit_id, task, target, "player", "總司令")
	task = ""
	target = ""
	_go("selected")
	return o

func cancel() -> void:
	task = ""
	target = ""
	_go("selected" if unit_id != "" else "idle")

func clear() -> void:
	unit_id = ""
	task = ""
	target = ""
	_go("idle")

func is_picking() -> bool:
	return state == "picking_sector" or state == "picking_unit"

func _go(s: String) -> void:
	state = s
	changed.emit(s)
