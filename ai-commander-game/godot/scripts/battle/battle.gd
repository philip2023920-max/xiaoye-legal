class_name Battle
extends Node3D
## 一場會戰的根節點：地圖、光、固定俯視攝影機、HUD（施工單 10），部隊樹與編制 AI（11）；戰鬥、戰情板寫入、導演在 12～14；
## 參謀長客戶端與節拍在 17（服務在 m0 的 chief serve；遊戲不暫停，回覆到了才套用命令）；右側戰情板側欄在 18；
## 推翻與接管（點排／點側欄 → 面板 → 點地圖選目標 → 直轄、/override）在 19；戰後 AAR 畫面（卡 → 討論 → 提案 → 採納）在 20。

@export var board_path: String = "m0://samples/board_deployed_balanced.json"
@export var enemy_path: String = ""           # 空＝依 difficulty 選劇本
@export var friendly_path: String = ""        # 我方劇本（空＝靠空白鍵／M2 的參謀長）；命令列 -- friendly=... 可覆寫
@export var difficulty: String = "normal"     # easy / normal / hard；命令列 -- difficulty=hard 可覆寫
@export var era: String = "ww2_1944"
@export var auto_advance: bool = true
@export var use_cmdline_args: bool = true     # 工具與測試自己設定屬性時關掉，避免命令列引數污染
@export var stress: int = 0                     # 施工單 15：額外擺 stress×126 個不動的方塊人（＝每倍一整個會戰的人數；純畫面負載），命令列 -- stress=10
@export var snapshot_dir: String = "user://battles"   # 每 30 秒一份快照到 <snapshot_dir>/<battle_id>-<難度>/t<n>.json；"" 不寫
@export var board_out: String = "user://board.json"   # 施工單 13：每 WRITE_INTERVAL 秒原子寫一次
@export_group("參謀長（施工單 17）")
@export var chief_provider: String = "fake"   # fake／ollama／anthropic…；"off" 或 "" ＝離線（M1 的劇本／空白鍵）；命令列 -- chief=anthropic
@export var chief_model: String = ""          # 空＝供應商預設（anthropic＝Haiku）
@export var chief_harness: String = "default"
@export var chief_lang: String = "zh-TW"
@export var chief_budget: float = -1.0        # 本場預算（美元）；<0 不設
@export var chief_url: String = ""            # 連到已在跑的服務（空＝自己 uv run chief serve）
@export var chief_token: String = ""          # 配合 chief_url
@export var chief_uv: String = "uv"           # uv 執行檔（不在 PATH 時填完整路徑）
@export var chief_extra: PackedStringArray = PackedStringArray()   # 服務的額外命令列（測試：--out-root … --ledger none）
@export var chief_autostart: bool = true      # _ready 時自動啟動；測試關掉自己 await start_chief()
@export_group("側欄（施工單 18）")
@export var sidebar_enabled: bool = true
const WRITE_INTERVAL := 0.1
const SIDEBAR_INTERVAL := 0.5
const CHIEF_BOOT_TIMEOUT_S := 10.0

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
var chief: ChiefClient = null
var scheduler: TickScheduler = null
var chief_state := "off"          # off / starting / online / offline / ended
var chief_line := ""              # HUD 第二行：開局引用句 → 每拍的研判 → 戰報摘要
var chief_cost := 0.0             # 本場費用（服務回的 cost_total_usd）
var chief_ticks := 0              # 成功回覆的拍數
var chief_session := {}           # /session/start 的回應
var chief_end_response := {}      # /battle/end 的回應（施工單 20 的 AAR 畫面用）
var chief_label: Label
var _chief_ending := false
var chief_last_orders: Array[String] = []   # 側欄「最近命令」（最近一拍放行的）
var sidebar: Sidebar = null
var _sidebar_acc := 0.0
var flow := OverrideFlow.new()        # 施工單 19：推翻／接管狀態機
var panel: OverridePanel = null
var override_rate := ""               # 服務回的「推翻數／參謀長放行命令數」
var last_override := {}               # 最近一次 /override 的回應（測試看）
var overrides_sent := 0
var edge_scroll_setting := true       # 玩家層級的邊緣捲動開關（設定頁 21 可關）；滑鼠在 UI 上時另外暫停
var aar: AarScreen = null             # 施工單 20：戰後畫面
var aar_model := {}                   # AarScreen.render 的資料（服務回的東西 + 流程狀態）
var _aar_started_msec := 0
const PICK_RADIUS_PX := 28.0

func _ready() -> void:
	board = BoardIO.load_board(board_path)
	if board.is_empty():
		push_error("開局戰情板載入失敗，場景是空的")
		return
	rules = Rules.load_era(str(board.get("era", era)))
	if rules == null:
		return
	if use_cmdline_args:
		for a in OS.get_cmdline_user_args():
			if a.begins_with("difficulty="):
				difficulty = a.trim_prefix("difficulty=")
			elif a.begins_with("friendly="):
				friendly_path = a.trim_prefix("friendly=")
			elif a.begins_with("stress="):
				stress = int(a.trim_prefix("stress="))
			elif a.begins_with("chief="):
				chief_provider = a.trim_prefix("chief=")
			elif a.begins_with("chief_model="):
				chief_model = a.trim_prefix("chief_model=")
			elif a.begins_with("lang="):
				chief_lang = a.trim_prefix("lang=")
	difficulty = Director.normalize_difficulty(difficulty)
	UiText.load_csv()
	UiText.set_lang(chief_lang)              # UI 與參謀長同一種語言（D27）
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
	if stress > 0:
		_add_stress_men()
	_add_hud()
	# 掩體進物理世界後才能烘焙尋路格
	await get_tree().physics_frame
	nav = RTSNavGrid.new(sector_map.world_rect(), 2.0)
	nav.bake_from_physics(get_world_3d(), SectorMap.COVER_MASK, 1.0)
	orbat.nav = nav
	if chief_autostart and auto_advance and chief_enabled():   # 工具與測試（auto_advance=false）自己決定要不要 start_chief()
		get_tree().auto_accept_quit = false   # 關窗先讓服務收 /shutdown（_notification）
		start_chief()

func _physics_process(delta: float) -> void:
	if orbat == null or not auto_advance or director == null:
		return
	if director.finished:
		chief_update()                # 結束後只剩 /battle/end 要送
		return
	director.tick(delta)
	if director.finished:
		show_result()
		if writer != null and board_out != "":
			writer.write(board_out)   # 結束那秒的板也要寫出去（之後不再寫）
		chief_update()
		return
	chief_update()
	_write_acc += delta
	if _write_acc >= WRITE_INTERVAL - 1e-6 and writer != null and board_out != "":
		_write_acc -= WRITE_INTERVAL
		writer.write(board_out)

## 壓力模式：在地圖上均勻撒 stress×126 個不動的方塊人，只量畫面負載（不進 Orbat、不耗邏輯）。
## 壓力模式下關掉 V-Sync，HUD 的 FPS 才不會被螢幕更新率封頂。
func _add_stress_men() -> void:
	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var holder := Node3D.new()
	holder.name = "StressMen"
	add_child(holder)
	var rect := sector_map.world_rect()
	var total := stress * 126
	var cols := ceili(sqrt(float(total)))
	var rows := ceili(float(total) / float(cols))
	for i in total:
		var man := Soldier.new()
		var x := rect.position.x + 2.0 + (i % cols) * (rect.size.x - 4.0) / maxf(1.0, float(cols - 1))
		var z := rect.position.y + 2.0 + floori(i / float(cols)) * (rect.size.y - 4.0) / maxf(1.0, float(rows - 1))
		man.setup("infantry" if i % 7 != 0 else "tank", "us" if i % 2 == 0 else "enemy", Vector3(x, 0.0, z))
		holder.add_child(man)

## 畫面上的方塊人總數（部隊＋壓力模式）。
func soldier_count() -> int:
	var n := 0
	if orbat != null:
		n += orbat.total_soldiers("us") + orbat.total_soldiers("enemy")
	var holder := get_node_or_null("StressMen")
	if holder != null:
		n += holder.get_child_count()
	return n

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
	hud_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART        # 側欄佔右側 440 px：兩行 HUD 在左邊換行，不被蓋住
	hud_label.custom_minimum_size = Vector2(hud_text_width(), 0.0)
	hud_label.size = Vector2(hud_text_width(), 0.0)
	hud_label.text = _status_text("")
	hud.add_child(hud_label)
	chief_label = Label.new()
	chief_label.name = "Chief"
	chief_label.position = Vector2(12, 34)
	chief_label.add_theme_color_override("font_outline_color", Color.BLACK)
	chief_label.add_theme_constant_override("outline_size", 4)
	chief_label.add_theme_color_override("font_color", Color(1.0, 0.93, 0.6))
	chief_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	chief_label.custom_minimum_size = Vector2(hud_text_width(), 0.0)
	chief_label.size = Vector2(hud_text_width(), 0.0)
	chief_label.position = Vector2(12, 58)                           # 狀態行可能兩行，第二行往下讓位（_process 再依實際高度調）
	chief_label.text = chief_hud_text()
	hud.add_child(chief_label)
	get_viewport().size_changed.connect(_relayout_hud)              # 視窗縮放：兩行寬度重算，不然又蓋到側欄
	if sidebar_enabled:
		sidebar = Sidebar.new()
		sidebar.unit_selected.connect(_on_sidebar_unit_selected)
		hud.add_child(sidebar)
		sidebar.refresh(writer.to_dict(), chief_sidebar_info(), battle_seconds())
	panel = OverridePanel.new()
	panel.task_pressed.connect(_on_panel_task)
	panel.takeover_pressed.connect(func() -> void: commander_takeover(flow.unit_id))
	panel.release_pressed.connect(func() -> void: commander_release(flow.unit_id))
	panel.cancel_pressed.connect(func() -> void: flow.cancel())
	flow.changed.connect(func(_st: String) -> void: refresh_panel())
	hud.add_child(panel)
	aar = AarScreen.new()
	aar.quick_reply.connect(func(i: int) -> void: aar_discuss("", i))
	aar.text_sent.connect(func(t: String) -> void: aar_discuss(t, -1))
	aar.propose_pressed.connect(aar_propose)
	aar.adopt_pressed.connect(aar_adopt)
	aar.skip_pressed.connect(aar_skip)
	aar.undo_pressed.connect(aar_undo)
	aar.again_pressed.connect(restart)
	hud.add_child(aar)

func _status_text(mouse_desc: String) -> String:
	var us := orbat.total_strength("us") if orbat else 0.0
	var en := orbat.total_strength("enemy") if orbat else 0.0
	var wx: String = str({"clear": "晴", "rain": "雨", "snow": "雪", "fog": "霧"}.get(orbat.weather, orbat.weather)) if orbat else ""
	var tod: String = str({"day": "日", "night": "夜"}.get(orbat.time_of_day, orbat.time_of_day)) if orbat else ""
	var left: int = maxi(0, battle_seconds() - (orbat.second() if orbat else 0))
	var left_text := "已結束" if (director != null and director.finished) else "剩 %d 秒" % left
	var fps := Engine.get_frames_per_second()
	var frame_ms := Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0 + Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
	return "%d FPS（%.1f ms）｜%d 個方塊人｜%s｜%s｜t=%ds（%s）%s/%s｜我方戰力 %.2f：敵 %.2f｜據點 %s｜滑鼠：%s｜空白鍵＝A 連奪取 C3｜R 重開" % [fps, frame_ms, soldier_count(), board.get("battle_id", ""), difficulty, orbat.second() if orbat else 0, left_text, wx, tod, us, en, _score_text(), mouse_desc]

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
	if chief_label != null:
		chief_label.text = chief_hud_text()
	_sidebar_acc += _delta
	if sidebar != null and _sidebar_acc >= SIDEBAR_INTERVAL:
		_sidebar_acc = 0.0
		sidebar.refresh(writer.to_dict(), chief_sidebar_info(), battle_seconds())
		refresh_panel()                                                 # 選中的排被殲滅／任務被參謀長改了，面板跟著變
	if aar != null and aar.visible and _sidebar_acc == 0.0:
		aar.set_duration(aar_duration(), float(aar_model.get("service_duration_s", -1.0)))
	camera_rig.edge_scroll_enabled = edge_scroll_setting and not mouse_over_ui()
	if chief_label != null and hud_label != null:
		chief_label.position.y = hud_label.position.y + maxf(hud_label.size.y, 20.0) + 4.0   # 狀態行幾行就往下推幾行
	camera_rig.edge_scroll_enabled = camera_rig.edge_scroll_enabled                # 滑鼠在側欄／面板上（含捲軸）時不要邊緣捲動地圖

## 滑鼠：左鍵點排＝選取（開面板）；選目標中左鍵＝點分區／點友軍；右鍵＝取消選目標。鍵盤：空白鍵＝「A 連 奪取 C3」（施工單 11）；R 重開。
func _unhandled_input(event: InputEvent) -> void:
	if orbat == null:
		return
	if event is InputEventMouseButton and event.pressed and camera_rig != null:
		if event.button_index == MOUSE_BUTTON_LEFT:
			_left_click(event.position)
		elif event.button_index == MOUSE_BUTTON_RIGHT and flow.is_picking():
			flow.cancel()
		return
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			var rejected := orbat.apply_orders("us", [Order.make("co-A", "seize", "C3", "player", "偵錯")])
			for r in rejected:
				push_warning(r)
		elif event.keycode == KEY_R:
			restart()
		elif event.keycode == KEY_ESCAPE:
			if flow.is_picking():
				flow.cancel()
			else:
				select_unit("")

func _left_click(screen: Vector2) -> void:
	if flow.state == "picking_unit":
		var friend := platoon_at_screen(screen)
		if friend != "" and not (friend in _subtree(flow.unit_id)):   # 連不能支援自己的子排
			flow.pick_unit(friend)
			_execute_flow()
		return
	if flow.state == "picking_sector":
		var sid := sector_map.sector_at(camera_rig.ground_at(screen))
		if sid != "":
			flow.pick_sector(sid)
			_execute_flow()
		return
	var hit := platoon_at_screen(screen)
	if hit != "":
		select_unit(hit)

## 挑排半徑（像素）：至少 PICK_RADIUS_PX，放大時放寬到排的實際範圍（4.5 公尺）的投影，點到士兵也選得到。
func pick_radius_px(anchor: Vector3) -> float:
	var a := camera_rig.screen_position(anchor)
	var b := camera_rig.screen_position(anchor + Vector3(4.5, 0.0, 0.0))
	return maxf(PICK_RADIUS_PX, a.distance_to(b))

## 螢幕上最近的我方排（錨點投影距離 < 挑排半徑）；沒有＝""。
func platoon_at_screen(screen: Vector2) -> String:
	var best := ""
	var best_d := INF
	for p in orbat.leaves("us"):
		if p.state == "destroyed" or not camera_rig.is_on_screen(p.anchor):
			continue
		var d := camera_rig.screen_position(p.anchor).distance_to(screen)
		if d >= pick_radius_px(p.anchor):
			continue
		if d < best_d:
			best_d = d
			best = p.id
	return best

# ---- 推翻與接管（施工單 19）----
## 選取排或連（""＝取消選取）：環變白、面板出現；側欄點樹也走這裡。戰後畫面開著時不選（面板會被蓋住）。
func select_unit(unit_id: String) -> void:
	if unit_id != "" and aar != null and aar.visible:
		return
	if flow.unit_id != "" and orbat.platoons.has(flow.unit_id):
		orbat.platoons[flow.unit_id].rts_set_selected(false)
	for cid in _subtree(flow.unit_id):
		if orbat.platoons.has(cid):
			orbat.platoons[cid].rts_set_selected(false)
	flow.select(unit_id)
	for cid in _subtree(unit_id):
		if orbat.platoons.has(cid):
			orbat.platoons[cid].rts_set_selected(true)
	refresh_panel()

func _on_panel_task(task: String) -> void:
	if flow.unit_id != "":
		flow.choose_task(task)

## 流程到 ready 就下令（點完目標立刻生效，不再多一個確認鍵）。
func _execute_flow() -> void:
	var o := flow.take_order()
	if o != null:
		commander_override(o.unit_id, o.task, o.target)

## 單位資訊給面板（排或連）。
func unit_info(unit_id: String) -> Dictionary:
	if orbat.platoons.has(unit_id):
		var p: Platoon = orbat.platoons[unit_id]
		return {"id": p.id, "name": p.display_name, "echelon": "platoon", "task": p.task, "controlled_by": p.controlled_by, "state": p.state}
	if orbat.companies.has(unit_id):
		var c: Dictionary = orbat.companies[unit_id]
		return {"id": c["id"], "name": c["name"], "echelon": "company", "task": c["task"], "controlled_by": c["controlled_by"], "state": c["state"]}
	return {}

func refresh_panel() -> void:
	if panel == null:
		return
	if flow.unit_id == "" or unit_info(flow.unit_id).is_empty():
		panel.hide_panel()
		return
	panel.show_unit(unit_info(flow.unit_id), flow.state, flow.task)

## unit 本身＋所有下級排（連＝連同子排一起直轄／放手，§9）。
func _subtree(unit_id: String) -> Array[String]:
	var out: Array[String] = []
	if unit_id == "":
		return out
	out.append(unit_id)
	if orbat.companies.has(unit_id):
		for p in orbat.children_of(unit_id):
			out.append(p.id)
	return out

func _set_controlled(unit_id: String, who: String) -> void:
	for uid in _subtree(unit_id):
		if orbat.platoons.has(uid):
			orbat.platoons[uid].controlled_by = who
			orbat.platoons[uid].update_ring()
		elif orbat.companies.has(uid):
			orbat.companies[uid]["controlled_by"] = who

## 總司令下令（含接管）：先過引擎檢查（含 V6 潰散只能撤退），再直轄整棵子樹、套用命令、記事件、通知服務（/override）。
func commander_override(unit_id: String, task: String, target: String) -> bool:
	if director != null and director.finished:
		return false                                                     # 戰後不再接管（/battle/end 已送或在飛）
	var o := Order.make(unit_id, task, target, "player", "總司令")
	var problem := orbat.order_problem("us", o)
	if problem != "":
		orbat.log_event(orbat.second(), "info", tr("UI_EVT_ORDER_REJECTED") % problem)
		refresh_panel()
		return false
	_set_controlled(unit_id, "player")
	orbat.apply_orders("us", [o])
	var who := str(unit_info(unit_id).get("name", unit_id))
	orbat.log_event(orbat.second(), "override", tr("UI_EVT_TAKEOVER") % [who, tr("UI_TASK_" + task), target], unit_id, target if sector_map.sectors.has(target) else "")
	refresh_panel()
	if chief_state == "online":
		_send_override(unit_id, {"task": task, "target": target})
	return true

## 「接管」：照目前任務直轄（沒任務就固守所在分區）。
func commander_takeover(unit_id: String) -> bool:
	var info := unit_info(unit_id)
	if info.is_empty():
		return false
	var task: Dictionary = info["task"] if info["task"] is Dictionary else {}
	if task.is_empty():
		var sec := orbat.unit_sector("us", unit_id)
		if sec == "":
			return false                                                 # 沒任務也不在任何分區（已殲滅）：不捏造目標
		task = {"type": "hold", "target": sec}
	return commander_override(unit_id, str(task.get("type", "hold")), str(task.get("target", "")))

## 「放手」：整棵子樹交回參謀長；通知服務（/release），下一拍參謀長就會重新下令。
func commander_release(unit_id: String) -> bool:
	if unit_info(unit_id).is_empty() or not _subtree(unit_id).any(func(uid: String) -> bool: return _is_player_controlled(uid)):
		return false
	var ids := _subtree(unit_id)
	_set_controlled(unit_id, "ai")
	if orbat.platoons.has(unit_id):                                      # 放手一個排：上級連不再「整個直轄」（連 player ⇔ 全部子排 player，§9）
		var parent: String = orbat.platoons[unit_id].parent_id
		if parent != "" and orbat.companies.has(parent) and str(orbat.companies[parent].get("controlled_by", "ai")) == "player":
			orbat.companies[parent]["controlled_by"] = "ai"
			ids.append(parent)
	orbat.log_event(orbat.second(), "info", tr("UI_EVT_RELEASE") % str(unit_info(unit_id).get("name", unit_id)), unit_id)
	refresh_panel()
	if chief_state == "online":
		_send_release(ids)
	return true

func _send_override(unit_id: String, player_order: Dictionary) -> void:
	overrides_sent += 1
	var r: Dictionary = await chief.override(unit_id, player_order, writer.to_dict(), float(orbat.second()))
	last_override = r
	if orbat == null:
		return
	if r["code"] != 200:
		if r["code"] >= 400 and r["code"] < 500 and r["code"] != 409:    # 服務說這道命令不合法：直轄名單兩邊要一致，收回
			_set_controlled(unit_id, "ai")
			refresh_panel()
		orbat.log_event(orbat.second(), "info", tr("UI_EVT_OVERRIDE_FAILED") % r["error"], unit_id)
		return
	var body: Dictionary = r["body"]
	override_rate = str(body.get("override_rate", override_rate))
	if bool(body.get("counted", false)):
		orbat.overrides_this_battle += 1
		orbat.log_event(orbat.second(), "info", tr("UI_EVT_OVERRIDE_RECORDED") % [int(body.get("recorded", 0)), override_rate], unit_id)
	else:
		orbat.log_event(orbat.second(), "info", tr("UI_EVT_OVERRIDE_NOT_COUNTED"), unit_id)

func _send_release(ids: Array[String]) -> void:
	var r: Dictionary = await chief.call_api("POST", "/release", {"unit_ids": Array(ids)}, 10.0)
	if r["code"] == 200:
		override_rate = str(r["body"].get("override_rate", override_rate))

## R 重開：先關參謀長服務（下一場會重新啟動），再重載場景。
func restart() -> void:
	if chief != null:
		chief_state = "off"
		await chief.stop()
	get_tree().reload_current_scene()

## 關窗：先讓服務收 /shutdown（它會補寫戰例），再真的退出。
func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		if chief != null and chief_state != "off":
			chief_state = "off"
			await chief.stop()
		get_tree().quit()

# ---- 參謀長（施工單 17）----
func chief_enabled() -> bool:
	return chief_provider != "" and chief_provider != "off"

## 啟動（或連上）參謀長服務並開局。回傳是否上線；失敗＝離線模式（M1 的劇本／空白鍵照常）。
func start_chief() -> bool:
	if orbat == null or writer == null:
		return false
	chief = ChiefClient.new()
	chief.name = "Chief"
	add_child(chief)
	scheduler = TickScheduler.new()
	chief_state = "starting"
	chief_line = "參謀長服務啟動中…"
	if chief_url != "":
		chief.connect_to(chief_url, chief_token)
	else:
		var extra := PackedStringArray(["--harness", chief_harness, "--lang", chief_lang])   # --parent-pid／--idle-exit 由 ChiefClient.launch 加
		if chief_model != "":
			extra.append_array(PackedStringArray(["--model", chief_model]))
		if chief_budget >= 0.0:
			extra.append_array(PackedStringArray(["--budget", str(chief_budget)]))
		extra.append_array(chief_extra)
		if chief.launch(chief_provider, extra, chief_uv) <= 0:
			return _chief_offline(chief.last_error)
	if not await chief.wait_online(CHIEF_BOOT_TIMEOUT_S):
		return _chief_offline(chief.last_error)
	if orbat == null:
		return false
	var r: Dictionary = await chief.start_session(writer.to_dict(), {"lang": chief_lang})
	if r["code"] != 200:
		return _chief_offline("開局失敗：" + str(r["error"]))
	chief_session = r["body"]
	chief_state = "online"
	var line := str(chief_session.get("opening_line", ""))
	chief_line = ("參謀長：" + line) if line != "" else "參謀長就位（%s／%s）" % [chief_session.get("provider", "?"), chief_session.get("model", "?")]
	orbat.log_event(orbat.second(), "info", chief_line)
	return true

func _chief_offline(why: String) -> bool:
	chief_state = "offline"
	chief_line = "參謀長服務沒起來：%s → 離線模式（劇本／空白鍵）" % why
	push_warning(chief_line)
	if orbat != null:
		orbat.log_event(orbat.second(), "info", chief_line)
	return false

## 每個物理 tick（或測試每步）呼叫：到期就送 /tick；會戰結束就送 /battle/end。遊戲不等回覆。
func chief_update() -> void:
	if chief_state != "online" or director == null or orbat == null:
		return
	if director.finished:
		if not _chief_ending:
			_chief_ending = true
			_chief_end()
		return
	if scheduler.due(orbat.t, orbat.events):
		_chief_tick()

func _chief_tick() -> void:
	var sec := orbat.second()
	scheduler.mark_sent(orbat.t)
	var r: Dictionary = await chief.tick(float(sec), writer.to_dict())
	scheduler.mark_done()
	if chief_state != "online" or orbat == null:
		return
	if r["code"] != 200:
		orbat.log_event(orbat.second(), "info", "參謀長無回應（%s）" % r["error"])
		if r["code"] == 409:
			chief_state = "ended"
		return
	var body: Dictionary = r["body"]
	chief_ticks += 1
	chief_cost = float(body.get("cost_total_usd", chief_cost))
	for oc in body.get("outcomes", []):
		orbat.log_event(orbat.second(), "override", str(oc.get("text", "")), str(oc.get("unit_id", "")))   # 與 M0 的推翻事件同 kind
	var orders: Array = []
	var skipped := 0
	for d in body.get("orders", []):
		var o := Order.from_dict(d, "ai")
		if _is_player_controlled(o.unit_id):      # 直轄：參謀長不得下令（服務端 V2 也會擋；這裡是保險）
			skipped += 1
			continue
		orders.append(o)
	var engine_rejected := orbat.apply_orders("us", orders)
	var service_rejected: Array = body.get("rejected", [])
	chief_last_orders.clear()
	for o in orders:
		chief_last_orders.append("%s %s %s" % [o.unit_id, Order.TASK_ZH.get(o.task, o.task), o.target])
	var latency: float = r["latency_s"]
	orbat.log_event(orbat.second(), "info", "參謀長回覆：%d 條命令、%d 條退回（延遲 %.1f 秒）" % [orders.size() - engine_rejected.size(), service_rejected.size() + engine_rejected.size() + skipped, latency])
	var assessment := str(body.get("assessment", "")) if body.get("assessment") != null else ""
	if assessment != "":
		chief_line = "參謀長：" + assessment
	if body.get("error") != null and str(body["error"]) != "":
		orbat.log_event(orbat.second(), "info", "參謀長：" + str(body["error"]))
		chief_line = "參謀長：" + str(body["error"])
	for m in body.get("messages", []):          # 預算 80%／100%
		orbat.log_event(orbat.second(), "info", str(m))

func _is_player_controlled(uid: String) -> bool:
	if orbat.platoons.has(uid):
		return orbat.platoons[uid].controlled_by == "player"
	if orbat.companies.has(uid):
		return str(orbat.companies[uid].get("controlled_by", "ai")) == "player"
	return false

func _chief_end() -> void:
	var r: Dictionary = await chief.battle_end(writer.to_dict(), director.result)
	chief_end_response = r
	if orbat == null:
		return
	if r["code"] == 200:
		var body: Dictionary = r["body"]
		var card: Dictionary = body.get("card", {})
		orbat.log_event(orbat.second(), "info", "戰報卡已產生（推翻 %d、未判定 %d）" % [int(card.get("overrides", 0)), int(body.get("unjudged", 0))])
		chief_line = "參謀長：" + str(body.get("summary", "")).split("\n")[0]
		chief_state = "ended"
		_show_aar(body)
	else:
		orbat.log_event(orbat.second(), "info", "戰報卡沒拿到（%s）" % r["error"])
		chief_state = "ended"

## 視窗大小變了：HUD 兩行的可用寬度重算（側欄固定 440 px 靠右）。
func _relayout_hud() -> void:
	for l in [hud_label, chief_label]:
		if l != null:
			l.custom_minimum_size = Vector2(hud_text_width(), 0.0)
			l.size = Vector2(hud_text_width(), l.size.y)

## 會戰長度（秒）：導演的常數，HUD、側欄都用這一份。
func battle_seconds() -> int:
	return int(Director.TURN_SECONDS) * Director.MAX_TURNS

## HUD 左上兩行可用的寬度（視窗寬 − 側欄 − 邊距）。
func hud_text_width() -> float:
	var w := get_viewport().get_visible_rect().size.x if get_viewport() != null else 1280.0
	return maxf(300.0, w - (Sidebar.WIDTH if sidebar_enabled else 0.0) - 24.0)

## 滑鼠是否在側欄或面板上（這些 Control 擋得了點擊，擋不了用座標算的邊緣捲動）。
func mouse_over_ui() -> bool:
	var m := get_viewport().get_mouse_position()
	if sidebar != null and sidebar.visible and sidebar.get_global_rect().has_point(m):
		return true
	if panel != null and panel.visible and panel.get_global_rect().has_point(m):
		return true
	return false

## 側欄「參謀長」區用的狀態（施工單 18）。
func chief_sidebar_info() -> Dictionary:
	return {"state": chief_state, "line": chief_line, "busy_s": chief.busy_seconds() if (chief != null and chief_state == "online") else 0.0,
		"orders": chief_last_orders, "cost": chief_cost, "ticks": chief_ticks, "ended": director != null and director.finished, "override_rate": override_rate}

## 側欄點了排或連：攝影機移過去，並選取（面板出現，施工單 19）。
func _on_sidebar_unit_selected(unit_id: String) -> void:
	var at := unit_world_position(unit_id)
	if camera_rig != null and at != Vector3.INF:
		camera_rig.look_at_ground(at)
	select_unit(unit_id)

## 排＝錨點；連＝存活下級排的平均；找不到＝Vector3.INF。
func unit_world_position(unit_id: String) -> Vector3:
	if orbat == null:
		return Vector3.INF
	if orbat.platoons.has(unit_id):
		return orbat.platoons[unit_id].anchor
	if orbat.companies.has(unit_id):
		var sum := Vector3.ZERO
		var n := 0
		for p in orbat.children_of(unit_id):
			if p.state != "destroyed":
				sum += p.anchor
				n += 1
		if n > 0:
			return sum / float(n)
		var sec := str(orbat.companies[unit_id].get("sector", ""))
		return sector_map.center_of(sec) if sec != "" and sector_map.sectors.has(sec) else Vector3.INF
	return Vector3.INF

# ---- 戰後 AAR（施工單 20）：畫面在 AarScreen，服務呼叫在這裡 ----
func _show_aar(end_body: Dictionary) -> void:
	_aar_started_msec = Time.get_ticks_msec()
	if result_label != null:
		result_label.visible = false                                     # M1 的結果字（「按 R 重開」）別疊在卡上；服務失敗時它還在當保底
	select_unit("")
	aar_model = {"card": end_body.get("card", {}), "seconds": director.result.get("seconds", -1) if director != null else -1,
		"unjudged": int(end_body.get("unjudged", 0)), "chief_line": "", "transcript": [], "round": 1,
		"next_quick": end_body.get("quick_replies", []), "diff": null, "phase": "card", "messages": [], "rolled_back": false,
		"adopted": false, "busy": false, "duration_s": 0.0, "service_duration_s": -1.0, "error": ""}
	if aar != null:
		aar.render(aar_model)
	aar_line()

func aar_duration() -> float:
	return float(Time.get_ticks_msec() - _aar_started_msec) / 1000.0 if _aar_started_msec > 0 else 0.0

func _aar_render(error: String = "") -> void:
	aar_model["duration_s"] = aar_duration()
	aar_model["error"] = error
	if aar != null:
		aar.render(aar_model)

## 一次服務呼叫：進行中畫面鎖按鈕；失敗把人話放到畫面上、不改階段。
func _aar_call(path: String, body: Dictionary = {}, timeout_s: float = 60.0) -> Dictionary:
	if chief == null or chief_state != "ended":
		return {"code": 0, "body": {}, "error": tr("UI_AAR_SERVICE_OFFLINE")}
	if bool(aar_model.get("busy", false)):                               # 上一個還沒回來：不排隊（不然 Enter 兩下吃掉兩回合）
		return {"code": 0, "body": {}, "error": tr("UI_AAR_WAITING")}
	aar_model["busy"] = true
	_aar_render()
	var r: Dictionary = await chief.call_api("POST", path, body, timeout_s)
	aar_model["busy"] = false
	if r["code"] != 200:
		_aar_render("%s：%s" % [path, r["error"]])
	return r

func aar_line() -> void:
	var r: Dictionary = await _aar_call("/aar/line", {}, 60.0)
	if r["code"] == 200:
		aar_model["chief_line"] = str(r["body"].get("chief_line", "")) if r["body"].get("chief_line") != null else ""
		if aar_model["chief_line"] == "":
			aar_model["chief_line"] = tr("UI_AAR_NO_LINE")
		_aar_render()
	else:
		aar_model["chief_line"] = tr("UI_AAR_NO_LINE")
		_aar_render(r["error"])

## 討論一回合：text 或快速回覆編號（1～3）。
func aar_discuss(text: String, index: int) -> void:
	if aar_model.get("phase", "") != "card" or int(aar_model.get("round", 1)) > 3:
		return
	var body := {"index": index} if index > 0 else {"text": text}
	var said := str(aar_model["next_quick"][index - 1]) if (index > 0 and index <= aar_model["next_quick"].size()) else text
	var r: Dictionary = await _aar_call("/aar/discuss", body, 60.0)
	if r["code"] != 200:
		return
	var b: Dictionary = r["body"]
	if b.get("reply") == null:                                           # 第 4 回合起服務只回 done：不追加對話
		aar_model["round"] = 4
		aar_model["next_quick"] = []
		_aar_render()
		return
	aar_model["transcript"].append({"role": "user", "content": said})
	aar_model["transcript"].append({"role": "assistant", "content": str(b.get("reply", ""))})
	aar_model["round"] = int(b.get("round", aar_model["round"])) + 1
	aar_model["next_quick"] = b.get("next_quick", [])
	_aar_render()

func aar_propose() -> void:
	if aar_model.get("phase", "") != "card":
		return
	var r: Dictionary = await _aar_call("/aar/propose", {}, 90.0)
	if r["code"] != 200:
		return
	var b: Dictionary = r["body"]
	if b.get("diff") == null:
		_aar_render(str(b.get("error", tr("UI_AAR_PROPOSE_FAILED"))))
		return
	aar_model["diff"] = b["diff"]
	aar_model["phase"] = "proposed"
	_aar_render()

func aar_adopt() -> void:
	if aar_model.get("phase", "") != "proposed":
		return
	var r: Dictionary = await _aar_call("/aar/adopt", {}, 180.0)   # 含回歸（可能跑好幾個戰例）
	if r["code"] != 200:
		return
	var b: Dictionary = r["body"]
	aar_model["phase"] = "adopted"
	aar_model["adopted"] = bool(b.get("adopted", false))
	aar_model["rolled_back"] = bool(b.get("rolled_back", false))
	aar_model["messages"] = b.get("messages", [])
	aar_model["service_duration_s"] = float(b.get("duration_s", -1.0))   # 服務記的（aar.json、chief stats 用的那個）
	_aar_render()
	if orbat != null:
		orbat.log_event(orbat.second(), "info", tr("UI_EVT_DOCTRINE_ADOPTED" if aar_model["adopted"] else "UI_EVT_DOCTRINE_UNCHANGED") % int(aar_model["service_duration_s"] if aar_model["service_duration_s"] >= 0.0 else aar_duration()))

func aar_skip() -> void:
	if not (aar_model.get("phase", "") in ["card", "proposed"]):
		return
	var r: Dictionary = await _aar_call("/aar/skip", {}, 30.0)
	if r["code"] == 200:
		aar_model["phase"] = "skipped"
		aar_model["messages"] = []
		_aar_render()

func aar_undo() -> void:
	if aar_model.get("phase", "") != "adopted":
		return
	var r: Dictionary = await _aar_call("/aar/undo", {}, 30.0)
	if r["code"] == 200:
		aar_model["phase"] = "undone" if bool(r["body"].get("undone", false)) else "adopted"
		aar_model["messages"].append(str(r["body"].get("message", "")))   # 保留回歸報告，撤銷訊息追加
		_aar_render()

## HUD 第二行。
func chief_hud_text() -> String:
	if not chief_enabled():
		return "參謀長：離線（劇本／空白鍵）"
	var parts: Array[String] = [chief_line]
	if chief != null and chief.busy and chief_state == "online":
		parts.append("參謀長思考中 %d 秒" % int(chief.busy_seconds()))
	if chief_state in ["online", "ended"]:
		parts.append("第 %d 拍｜費用 $%.4f" % [chief_ticks, chief_cost])
	return "｜".join(parts)

## 結果畫面：一塊面板寫勝負、據點、戰力、用時（M0 BattleResult 同欄位，另存 result.json）。
func show_result() -> void:
	if director == null or not director.finished or result_label != null:
		return
	var hud := get_node_or_null("HUD")
	if hud == null:
		return
	if hud_label != null:
		hud_label.text = _status_text("")   # 無頭模式沒有 _process，這裡也更新一次（顯示「已結束」）
	result_label = Label.new()
	result_label.name = "Result"
	result_label.text = director.summary() + "\n按 R 重開"
	result_label.position = Vector2(40, 120)
	result_label.add_theme_font_size_override("font_size", 28)
	result_label.add_theme_color_override("font_outline_color", Color.BLACK)
	result_label.add_theme_constant_override("outline_size", 6)
	hud.add_child(result_label)
