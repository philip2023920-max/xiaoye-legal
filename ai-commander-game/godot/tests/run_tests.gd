extends SceneTree
## 施工單 10 無頭測試。期望值來自 docs/09（座標約定、樣板內容）與 docs/issues/10 驗收清單，不照程式回算。
##
##   godot --headless --path . --import            （第一次或換版本後）
##   godot --headless --path . -s tests/run_tests.gd
##
## 任何失敗 exit 1。EXPECTED_CHECKS 守門：執行期錯誤會讓函式中途結束，數量對不上就會被抓到。

const EXPECTED_CHECKS := 26

var _checks := 0
var _failures := 0

func _initialize() -> void:
	_run.call_deferred()

func check(ok: bool, name: String) -> void:
	_checks += 1
	if ok:
		print("  ok   ", name)
	else:
		_failures += 1
		printerr("  FAIL ", name)

func _run() -> void:
	# ---- BoardIO ----
	var board := BoardIO.load_board("m0://samples/board_start.json")
	check(not board.is_empty(), "樣板 board_start.json 讀得到（m0:// 指向隔壁 m0/）")
	check(str(board.get("schema_version")) == "0.2", "schema_version 0.2")
	check(board["map"]["sectors"].size() == 25, "5×5 共 25 個分區")
	check(BoardIO.load_board("m0://samples/orders_scripted.json").is_empty(), "不是戰情板（沒有 schema_version）→ 空字典")
	check(BoardIO.load_board("m0://samples/nope.json").is_empty(), "找不到檔案 → 空字典")

	# ---- SectorMap 座標 ----
	var map := SectorMap.new()
	get_root().add_child(map)
	map.build_from_board(board)
	check(SectorMap.id_of(2, 2) == "C3" and SectorMap.col_row_of("E5") == Vector2i(4, 4), "id ↔ 欄列")
	check(map.world_rect() == Rect2(0, 0, 100, 100), "地圖矩形 100×100 m")
	check(map.center_of("C3") == Vector3(50, 0, 50), "C3 中心 (50,0,50)")
	check(map.center_of("A1") == Vector3(10, 0, 10), "A1 中心 (10,0,10)：A 在左、1 在上")
	check(map.sector_at(map.center_of("D2")) == "D2", "中心反查 D2")
	check(map.sector_at(Vector3(0.1, 0, 0.1)) == "A1" and map.sector_at(Vector3(99.9, 0, 99.9)) == "E5", "角落 A1／E5")
	check(map.sector_at(Vector3(-0.1, 0, 5)) == "" and map.sector_at(Vector3(5, 0, 100.0)) == "", "出界回空字串")
	check(map.terrain_of("C3") == "town" and map.terrain_of("D4") == "river" and map.terrain_of("E1") == "forest", "地形照樣板")
	check(map.owner_of("B2") == "us" and map.owner_of("E4") == "enemy" and map.owner_of("C3") == "none", "擁有方照樣板")
	check(map.objectives["O2"]["sector"] == "C3" and map.objectives["O2"]["value"] == 5, "據點 O2 在 C3、5 分")

	# ---- 掩體與旗 ----
	var covers := get_nodes_in_group("cover")
	var by_sector := {}
	for c in covers:
		var sid: String = c.get_meta("sector")
		by_sector[sid] = by_sector.get(sid, 0) + 1
	check(by_sector.get("C3", 0) == 6, "城鎮 C3 有 6 個方塊掩體")
	check(by_sector.get("E1", 0) == 8 and by_sector.get("A4", 0) == 8, "森林 E1／A4 各 8 棵樹")
	check(not by_sector.has("A1") and not by_sector.has("D4"), "平地與河川沒有掩體")
	var all_layer2 := true
	for c in covers:
		if (c as StaticBody3D).collision_layer != 2:
			all_layer2 = false
	check(all_layer2, "掩體都在碰撞層 2（尋路烘焙用）")
	var flags := get_nodes_in_group("objective_flag")
	check(flags.size() == 3, "三面據點旗")
	var ground := map.get_node("Ground") as StaticBody3D
	check(ground != null and ground.collision_layer == 1, "地面碰撞體在層 1（攝影機射線用）")

	# ---- 易手改色 ----
	map.set_sector_owner("C3", "us", true)
	check(map.owner_of("C3") == "us" and map.objectives["O2"]["owner"] == "us", "set_sector_owner 同步分區與據點")

	# ---- Battle 場景 ----
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var battle: Node3D = scene.instantiate()
	get_root().add_child(battle)
	await process_frame
	check(battle.camera_rig != null and battle.camera_rig.is_in_group(RTSKit.CAMERA_GROUP), "攝影機是骨架的 RTSCameraRig")
	check(battle.camera_rig.bounds == Rect2(0, 0, 100, 100) and battle.camera_rig.pitch_degrees == 60.0, "攝影機邊界＝地圖、俯仰 60°")
	check(battle.camera_rig.distance == 70.0 and battle.camera_rig.min_distance <= 70.0 and 70.0 <= battle.camera_rig.max_distance, "距離 70 在範圍內")
	check(battle.get_node("HUD/Status") != null and battle.sector_map.sectors.size() == 25, "HUD 與地圖都在場景裡")

	print("checks: %d (expected %d), failures: %d" % [_checks, EXPECTED_CHECKS, _failures])
	var ok := _failures == 0 and _checks == EXPECTED_CHECKS
	map.queue_free(); battle.queue_free()
	await process_frame
	quit(0 if ok else 1)
