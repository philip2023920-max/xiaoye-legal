class_name Battle
extends Node3D
## 一場會戰的根節點：地圖、光、固定俯視攝影機、HUD（施工單 10），部隊樹與編制 AI（11）；戰鬥、戰情板寫入、導演在 12～14。

@export var board_path: String = "m0://samples/board_deployed_balanced.json"
@export var enemy_path: String = ""           # 空＝依 difficulty 選劇本
@export var friendly_path: String = ""        # 我方劇本（空＝靠空白鍵／M2 的參謀長）；命令列 -- friendly=... 可覆寫
@export var difficulty: String = "normal"     # easy / normal / hard；命令列 -- difficulty=hard 可覆寫
@export var era: String = "ww2_1944"
@export var auto_advance: bool = true
@export var snapshot_dir: String = "user://battles"   # 每 30 秒一份快照到 <snapshot_dir>/<battle_id>-<難度>/t<n>.json；"" 不寫
@export var board_out: String = "user://board.json"   # 施工單 13：每 WRITE_INTERVAL 秒原子寫一次
const WRITE_INTERVAL := 0.1

var board := {}
var enemy_script := {}
var rules: Rules
var sector_map: SectorMap
var orbat: Orbat
var camera_rig: RTSCameraRig
var hud_label: Label
var nav: RTSNavGrid
var writer: BoardWriter
var director: Director
var friendly_script := {}
var result_label: Label
var _write_acc := 0.0
var _tracer_mesh: ImmediateMesh
var _tracer_second := -1

func _ready() -> void:
	board = BoardIO.load_board(board_path)
	if board.is_empty():
		push_error("開局戰情板載入失敗，場景是空的")
		return
	rules = Rules.load_era(str(board.get("era", era)))
	if rules == null:
		return
	for a in OS.get_cmdline_user_args():
		if a.begins_with("difficulty="):
			difficulty = a.trim_prefix("difficulty=")
		elif a.begins_with("friendly="):
			friendly_path = a.trim_prefix("friendly=")
	if enemy_path == "":
		enemy_path = Director.enemy_path_for(difficulty)
	enemy_script = BoardIO.load_json(enemy_path)
	friendly_script = BoardIO.load_json(friendly_path) if friendly_path != "" else {}
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
	writer = BoardWriter.new(orbat, str(board.get("battle_id", "battle")), str(board.get("era", era)))
	orbat.second_hooks.append(writer.update)
	writer.update(0)
	var out := snapshot_dir.path_join("%s-%s" % [board.get("battle_id", "battle"), difficulty]) if snapshot_dir != "" else ""
	director = Director.new(orbat, writer, friendly_script, enemy_script, difficulty, out)
	if board_out != "":
		print("戰情板輸出：", ProjectSettings.globalize_path(board_out), "（每 %.1f 秒）" % WRITE_INTERVAL)
	_add_tracers()
	_add_hud()
	# 掩體進物理世界後才能烘焙尋路格
	await get_tree().physics_frame
	nav = RTSNavGrid.new(sector_map.world_rect(), 2.0)
	nav.bake_from_physics(get_world_3d(), SectorMap.COVER_MASK, 1.0)
	orbat.nav = nav

func _physics_process(delta: float) -> void:
	if orbat == null or not auto_advance or director == null:
		return
	if director.finished:
		return
	director.tick(delta)
	if director.finished:
		show_result()
	_write_acc += delta
	if _write_acc >= WRITE_INTERVAL - 1e-6 and writer != null and board_out != "":
		_write_acc -= WRITE_INTERVAL
		writer.write(board_out)

## 射線：這一秒的交火畫成細線（無貼圖、不發光）。
func _add_tracers() -> void:
	var mi := MeshInstance3D.new()
	mi.name = "Tracers"
	_tracer_mesh = ImmediateMesh.new()
	mi.mesh = _tracer_mesh
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(1.0, 0.9, 0.4)
	mi.material_override = mat
	add_child(mi)

func _draw_tracers() -> void:
	if _tracer_mesh == null or orbat == null or orbat.resolver == null or orbat.resolver.last_second == _tracer_second:
		return
	_tracer_second = orbat.resolver.last_second
	_tracer_mesh.clear_surfaces()
	if orbat.resolver.tracers.is_empty():
		return
	_tracer_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for tr in orbat.resolver.tracers:
		_tracer_mesh.surface_add_vertex(tr["from"])
		_tracer_mesh.surface_add_vertex(tr["to"])
	_tracer_mesh.surface_end()

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
	var wx: String = str({"clear": "晴", "rain": "雨", "snow": "雪", "fog": "霧"}.get(orbat.weather, orbat.weather)) if orbat else ""
	var tod: String = str({"day": "日", "night": "夜"}.get(orbat.time_of_day, orbat.time_of_day)) if orbat else ""
	var left: int = maxi(0, int(Director.TURN_SECONDS) * Director.MAX_TURNS - (orbat.second() if orbat else 0))
	return "%s｜%s｜t=%ds（剩 %d 秒）%s/%s｜我方戰力 %.2f：敵 %.2f｜據點 %s｜滑鼠：%s｜空白鍵＝A 連奪取 C3｜R 重開" % [board.get("battle_id", ""), difficulty, orbat.second() if orbat else 0, left, wx, tod, us, en, _score_text(), mouse_desc]

func _score_text() -> String:
	var su := 0
	var se := 0
	for oid in sector_map.objectives.keys():
		var o: Dictionary = sector_map.objectives[oid]
		if o["owner"] == "us":
			su += int(o["value"])
		elif o["owner"] == "enemy":
			se += int(o["value"])
	return "%d:%d" % [su, se]

func _process(_delta: float) -> void:
	if hud_label == null or camera_rig == null or DisplayServer.get_name() == "headless":
		return
	_draw_tracers()
	var under := sector_map.sector_at(camera_rig.ground_under_mouse())
	var desc := ""
	if under != "":
		desc = "%s %s%s" % [under, sector_map.terrain_of(under), ("／" + sector_map.owner_of(under)) if sector_map.owner_of(under) != "none" else ""]
	hud_label.text = _status_text(desc)

## 偵錯用：空白鍵＝「A 連 奪取 C3」（施工單 11 的 30 秒驗收）。
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and orbat != null:
		if event.keycode == KEY_SPACE:
			var rejected := orbat.apply_orders("us", [Order.make("co-A", "seize", "C3", "player", "偵錯")])
			for r in rejected:
				push_warning(r)
		elif event.keycode == KEY_R:
			get_tree().reload_current_scene()

## 結果畫面：一塊面板寫勝負、據點、戰力、用時（M0 BattleResult 同欄位，另存 result.json）。
func show_result() -> void:
	if director == null or not director.finished or result_label != null:
		return
	var hud := get_node_or_null("HUD")
	if hud == null:
		return
	result_label = Label.new()
	result_label.name = "Result"
	result_label.text = director.summary() + "\n按 R 重開"
	result_label.position = Vector2(40, 120)
	result_label.add_theme_font_size_override("font_size", 28)
	result_label.add_theme_color_override("font_outline_color", Color.BLACK)
	result_label.add_theme_constant_override("outline_size", 6)
	hud.add_child(result_label)
