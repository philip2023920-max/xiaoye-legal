extends SceneTree
## 施工單 13 無頭測試：§6 歸屬、§2 視距與敵情、Board v0.2 欄位、原子寫入。期望值來自 docs/09、docs/10 §2／§6／§8b 與樣板。
##   godot --headless --path . -s tests/test_board_writer.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 27)
	_run.call_deferred()

func make_orbat() -> Orbat:
	var board := BoardIO.load_board("m0://samples/board_deployed_balanced.json")
	var map := SectorMap.new()
	get_root().add_child(map)
	map.build_from_board(board)
	var o := Orbat.new()
	get_root().add_child(o)
	o.setup(map, Rules.load_era())
	o.build(board, BoardIO.load_json("m0://samples/enemy_script_v1.json").get("units", []))
	return o

func _run() -> void:
	var o := make_orbat()
	var w := BoardWriter.new(o, "hill-town-start", "ww2_1944")
	o.second_hooks.append(w.update)
	w.update(0)
	h.check(w.visible == ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "D1"], "開局視距：步兵 1（自己四格＋四鄰）、偵察排 2（B1 → C1、D1、C2、B3）")
	h.check(w.contacts.is_empty(), "敵軍都在兩格外 → 敵情空")
	h.check(BoardWriter.phase_of(90.0) == "early" and BoardWriter.phase_of(91.0) == "mid" and BoardWriter.phase_of(211.0) == "late", "階段：≤90 秒 early、≤210 mid、其餘 late（M0 回合 3／7 × 30）")
	o.apply_orders("us", [Order.make("plt-A1", "seize", "C3")])
	o.advance_for(20.0)
	var a1: Platoon = o.platoons["plt-A1"]
	h.check(a1.sector == "C2" and o.map.owner_of("C2") == "us", "A1 跨進 C2 → 無主分區歸我方（§6）")
	h.check(o.events.any(func(e: Dictionary) -> bool: return e["kind"] == "seized" and e["sector"] == "C2" and e["text"] == "我方取得 C2"), "seized 事件文字與 M0 相同")
	h.check(w.contacts.has("e-plt-12") and w.contacts["e-plt-12"]["sector"] == "C3" and w.contacts["e-plt-12"]["confidence"] == 0.9, "C2 看得到 C3 → 敵機槍進敵情（可信度 0.9）")
	h.check(not w.contacts.has("e-plt-11"), "C4 距 C2 兩格 → 看不到")
	h.check(o.events.any(func(e: Dictionary) -> bool: return e["kind"] == "contact" and e["text"] == "在 C3 發現敵 敵 12 機槍排"), "contact 事件")
	o.advance_for(45.0)
	h.check(a1.sector == "C3" and o.map.owner_of("C3") == "enemy" and bool(o.map.sectors["C3"]["contested"]), "我方進敵守的 C3 → 擁有者不變、爭奪中")
	h.check(o.map.objectives["O2"]["owner"] == "enemy", "據點 owner 跟著分區")
	var d := w.to_dict()
	h.check(d["schema_version"] == "0.2" and d["time_unit"] == "second" and d["t"] == 65 and d["phase"] == "early", "Board v0.2 頂層：秒為單位")
	h.check(d["map"]["sectors"].size() == 25 and d["map"]["sectors"]["C3"]["contested"] == true and d["map"]["sectors"]["C3"]["objective"] == "O2", "分區欄位")
	h.check(d["orbat"].size() == 9 and d["orbat"][0]["id"] == "co-A" and d["orbat"][0]["type"] == "mixed" and d["orbat"][1]["parent"] == "co-A", "orbat：連在前、排帶 parent（戰情板順序）")
	h.check(d["orbat"][1]["task"] == {"type": "seize", "target": "C3"} and d["orbat"][1]["state"] == "engaged", "排的任務與狀態")
	var known_ids: Array = d["enemy_known"].map(func(c: Dictionary) -> String: return c["id"])
	var sorted_ids: Array = known_ids.duplicate()
	sorted_ids.sort()
	h.check(known_ids.size() >= 1 and known_ids == sorted_ids, "敵情列表照 id 排序")
	h.check(d["objectives"].size() == 3 and d["fog"]["visible_sectors"].has("C3") and d["overrides_this_battle"] == 0, "目標、迷霧、推翻數")
	h.check(d["events"].size() >= 3 and d["events"][0].has("t") and d["events"][0].has("kind") and d["events"][0].has("text"), "事件欄位與 M0 Event 相同")
	# ---- 原子寫入 ----
	var out := "user://test_board_writer/board.json"
	var ok := w.write(out)
	var real := ProjectSettings.globalize_path(out)
	h.check(ok and FileAccess.file_exists(real) and not FileAccess.file_exists(real + ".tmp"), "寫檔成功、暫存檔已改名")
	var back: Variant = JSON.parse_string(FileAccess.get_file_as_string(real))
	h.check(typeof(back) == TYPE_DICTIONARY and back["t"] == 65 and back["orbat"].size() == 9, "讀回來一樣")
	var ok2 := w.write(out)
	h.check(ok2 and w.writes == 2, "第二次覆寫成功（改名蓋過既有檔）")
	# ---- 看到被殲滅就從敵情移除 ----
	var e12: Platoon = o.platoons["e-plt-12"]
	e12.state = "destroyed"
	o.advance_for(1.5)
	h.check(not w.contacts.has("e-plt-12"), "親眼看到殲滅 → 從敵情拿掉")
	h.check(JSON.stringify(w.to_dict()).length() < 12000, "壓縮前 JSON 長度合理（< 12 KB）")
	# ---- 夜間／霧視距縮小；爭奪中撤出不寫 seized；5 分鐘後檔案大小 ----
	var o2 := make_orbat()
	var w2 := BoardWriter.new(o2, "x", "ww2_1944")
	o2.second_hooks.append(w2.update)
	w2.update(0)
	var day_count := w2.visible.size()
	o2.set_conditions("", "night")
	o2.advance_for(1.5)
	var night_count := w2.visible.size()
	o2.set_conditions("fog", "")
	o2.advance_for(1.0)
	h.check(day_count == 9 and night_count == 5 and w2.visible.size() == 4, "視距：日 9 格 → 夜 5 格（步兵 0、偵察 1）→ 霧 4 格（只看自己）")
	h.check(o2.platoons["plt-A7"].vision_radius == 0.0 and o2.platoons["plt-A7"].unit_type == "recon", "骨架迷霧半徑跟著天氣變（霧 → 0）")
	var o3 := make_orbat()
	var w3 := BoardWriter.new(o3, "x", "ww2_1944")
	o3.second_hooks.append(w3.update)
	w3.update(0)
	var a2: Platoon = o3.platoons["plt-A2"]
	o3.map.set_sector_owner("C3", "enemy")
	o3.place_platoon(a2, o3.map.center_of("C3"))
	o3.advance_for(1.5)
	var seized_before: int = o3.events.filter(func(e: Dictionary) -> bool: return e["kind"] == "seized").size()
	h.check(bool(o3.map.sectors["C3"]["contested"]) and o3.map.owner_of("C3") == "enemy", "進敵守的格 → 爭奪中、擁有者不變")
	o3.place_platoon(a2, o3.map.center_of("A5"))
	o3.advance_for(1.5)
	var seized_after: int = o3.events.filter(func(e: Dictionary) -> bool: return e["kind"] == "seized").size()
	h.check(not bool(o3.map.sectors["C3"]["contested"]) and o3.map.owner_of("C3") == "enemy" and seized_after == seized_before + 1, "撤出 → 爭奪解除、擁有者不變、只多一筆 A5 的 seized")
	var o4 := make_orbat()
	var w4 := BoardWriter.new(o4, "x", "ww2_1944")
	o4.second_hooks.append(w4.update)
	o4.apply_orders("us", [Order.make("co-A", "seize", "C3", "player")])
	o4.advance_for(300.0)
	var big := JSON.stringify(w4.to_dict())
	h.check(big.length() < 32768 and w4.to_dict()["t"] == 300 and w4.to_dict()["phase"] == "late", "5 分鐘整場：JSON < 32 KB、t=300、late")
	h.finish()
