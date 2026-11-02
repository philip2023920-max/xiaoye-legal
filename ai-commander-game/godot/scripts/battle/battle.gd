class_name Battle
extends Node3D
## 一場會戰的根節點：地圖、光、固定俯視攝影機、HUD（施工單 10），部隊樹與編制 AI（11）；戰鬥、戰情板寫入、導演在 12～14。

@export var board_path: String = "m0://samples/board_deployed_balanced.json"
@export var enemy_path: String = "m0://samples/enemy_script_v1.json"
@export var era: String = "ww2_1944"
@export var auto_advance: bool = true

var board := {}
var enemy_script := {}
var rules: Rules
var sector_map: SectorMap
var orbat: Orbat
var camera_rig: RTSCameraRig
var hud_label: Label
var nav: RTSNavGrid

func _ready() -> void:
	board = BoardIO.load_board(board_path)
	if board.is_empty():
		push_error("開局戰情板載入失敗，場景是空的")
		return
	rules = Rules.load_era(str(board.get("era", era)))
	if rules == null:
		return
	enemy_script = BoardIO.load_json(enemy_path) if enemy_path != "" else {}
	sector_map = SectorMap.new()
	sector_map.name = "SectorMap"
	add_child(sector_map)
	sector_map.build_from_board(board)
	_add_light_and_environment()
	_add_camera()
	orbat = Orbat.new()
	orbat.name = "Orbat"
	add_child(orbat)
	orbat.setup(sector_map, rules)
	orbat.build(board, enemy_script.get("units", []))
	_add_hud()
	# 掩體進物理世界後才能烘焙尋路格
	await get_tree().physics_frame
	nav = RTSNavGrid.new(sector_map.world_rect(), 2.0)
	nav.bake_from_physics(get_world_3d(), SectorMap.COVER_MASK, 1.0)
	orbat.nav = nav

func _physics_process(delta: float) -> void:
	if orbat != null and auto_advance:
		orbat.advance(delta)

func _add_light_and_environment() -> void:
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.rotation_degrees = Vector3(-55.0, 35.0, 0.0)
	sun.light_energy = 1.1
	add_child(sun)
	var env := WorldEnvironment.new()
	env.name = "Environment"
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.72, 0.80, 0.88)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.85, 0.85, 0.9)
	e.ambient_light_energy = 0.6
	env.environment = e
	add_child(env)

## 固定俯視：骨架的 RTSCameraRig，俯仰 60°，邊界＝地圖矩形，地面碰撞層 1。
func _add_camera() -> void:
	camera_rig = RTSCameraRig.new()
	camera_rig.name = "CameraRig"
	var rect := sector_map.world_rect()
	camera_rig.bounds = rect
	camera_rig.pitch_degrees = 60.0
	camera_rig.min_distance = 25.0
	camera_rig.max_distance = 140.0
	camera_rig.distance = 70.0
	camera_rig.ground_collision_mask = SectorMap.GROUND_MASK
	camera_rig.position = Vector3(rect.size.x * 0.5, 0.0, rect.size.y * 0.5 + 10.0)
	add_child(camera_rig)

func _add_hud() -> void:
	var hud := CanvasLayer.new()
	hud.name = "HUD"
	add_child(hud)
	hud_label = Label.new()
	hud_label.name = "Status"
	hud_label.position = Vector2(12, 10)
	hud_label.add_theme_color_override("font_outline_color", Color.BLACK)
	hud_label.add_theme_constant_override("outline_size", 4)
	hud_label.text = _status_text("")
	hud.add_child(hud_label)

func _status_text(mouse_desc: String) -> String:
	var us := orbat.total_strength("us") if orbat else 0.0
	var en := orbat.total_strength("enemy") if orbat else 0.0
	return "%s｜t=%ds｜我方戰力 %.2f：敵 %.2f｜滑鼠：%s｜WASD 平移、滾輪縮放、空白鍵＝A 連奪取 C3" % [board.get("battle_id", ""), int(orbat.t) if orbat else 0, us, en, mouse_desc]

func _process(_delta: float) -> void:
	if hud_label == null or camera_rig == null or DisplayServer.get_name() == "headless":
		return
	var under := sector_map.sector_at(camera_rig.ground_under_mouse())
	var desc := ""
	if under != "":
		desc = "%s %s%s" % [under, sector_map.terrain_of(under), ("／" + sector_map.owner_of(under)) if sector_map.owner_of(under) != "none" else ""]
	hud_label.text = _status_text(desc)

## 偵錯用：空白鍵＝「A 連 奪取 C3」（施工單 11 的 30 秒驗收）。
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_SPACE and orbat != null:
		var rejected := orbat.apply_orders("us", [Order.make("co-A", "seize", "C3", "player", "偵錯")])
		for r in rejected:
			push_warning(r)
