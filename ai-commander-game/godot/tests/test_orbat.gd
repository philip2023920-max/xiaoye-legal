extends SceneTree
## 施工單 11 無頭測試：部隊樹、速度、機動力、通行、六種任務、連令拆排、戰力聚合、潰散撤退。
## 期望值來自 docs/10 §2、§3、§8b、§15（1 回合＝30 秒、BFS 鄰格順序上左右下、連分區同強取 id 字串序最大者）、
## 樣板 board_deployed_balanced.json 與 enemy_script_v1.json。
##   godot --headless --path . -s tests/test_orbat.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 50)
	_run.call_deferred()

func make_orbat(board_path: String = "m0://samples/board_deployed_balanced.json", enemy_path: String = "m0://samples/enemy_script_v1.json") -> Orbat:
	var board := BoardIO.load_board(board_path)
	var rules := Rules.load_era()
	var map := SectorMap.new()
	get_root().add_child(map)
	map.build_from_board(board)
	var orbat := Orbat.new()
	get_root().add_child(orbat)
	orbat.setup(map, rules)
	var enemy := BoardIO.load_json(enemy_path) if enemy_path != "" else {}
	orbat.build(board, enemy.get("units", []))
	return orbat

func put(o: Orbat, pid: String, sector: String) -> Platoon:
	var p: Platoon = o.platoons[pid]
	o.place_platoon(p, o.map.center_of(sector))
	return p

func _run() -> void:
	# ---- 生成 ----
	var o := make_orbat()
	h.check(o.leaves("us").size() == 8 and o.total_soldiers("us") == 72, "均衡範本：8 排 72 人")
	h.check(o.leaves("enemy").size() == 6 and o.total_soldiers("enemy") == 54, "敵方 normal 劇本：6 排 54 人")
	h.check(o.companies.has("co-A") and o.companies.has("e-co-1") and o.children_of("co-A").size() == 8, "連是容器，子排 8 個")
	var a1: Platoon = o.platoons["plt-A1"]
	var a4: Platoon = o.platoons["plt-A4"]
	h.check(a1.sector == "B2" and a1.unit_type == "infantry" and a4.sector == "A1" and a4.unit_type == "mg", "排的分區與兵種照樣板")
	h.check(a1.anchor == o.map.center_of("B2") and o.platoons["plt-A5"].anchor == o.map.center_of("B2") + Vector3(-7, 0, -7), "同格的排各占一個站位（第一個在中心）")
	h.check(a1.soldiers[0].head_color() != o.platoons["e-plt-13"].soldiers[0].head_color(), "兵種用頭色分（步兵≠戰車）")
	h.check(o.companies["co-A"]["strength"] == 1.0 and o.companies["co-A"]["sector"] == "A1", "連戰力＝子排平均、分區＝最強子排（同強取 id 字串序最大者 plt-A8 → A1，與 M0 相同）")
	h.check(o.companies["e-co-1"]["sector"] == "E4", "敵連分區：e-plt-16 的 E4")
	o.advance_for(1.0)
	h.check(a1.sector == "B2" and a1.state == "idle" and o.t > 0.99, "沒有命令就原地待命")

	# ---- 速度與路線（§2：speed 1 → 20 m／30 s；BFS 上左右下 → B2→C2→C3）----
	var rej := o.apply_orders("us", [Order.make("plt-A1", "seize", "C3")])
	h.check(rej.is_empty() and a1.task == {"type": "seize", "target": "C3"} and a1.state == "idle", "排接到 seize C3")
	o.advance_for(16.0)
	h.check(a1.sector == "C2" and a1.state == "moving", "17 秒後跨進 C2（第一步往右；10 m 跨線，15 秒）")
	o.advance_for(20.0)
	h.check(a1.sector == "C2" and a1.state == "moving", "37 秒後過了 C2 中心還在走（中途分區不算到達，仍是 moving）")
	o.advance_for(25.0)
	h.check(a1.sector == "C3" and a1.state == "idle" and a1.anchor == o.map.center_of("C3"), "62 秒後到 C3 中心並待命（40 m ÷ 0.667 m/s ＝ 60 秒，減兩次 0.5 m 吸附）")
	h.check(o.events.any(func(e: String) -> bool: return e.begins_with("參謀長令 A1 步兵排 奪取 C3")), "事件流記下命令")

	# ---- 偵察排速度 2：B1 → C3 共 3 格，45 秒 ----
	var a7 := put(o, "plt-A7", "B1")
	o.apply_orders("us", [Order.make("plt-A7", "seize", "C3")])
	o.advance_for(46.0)
	h.check(a7.sector == "C3" and a7.anchor.distance_to(o.map.center_of("C3")) < 12.0 and a7.state == "idle", "偵察排速度 2：B1 到 C3 共 3 格 45 秒到（站到 C3 的空站位）")

	# ---- 進敵格停一回合（§2）----
	var o2 := make_orbat()
	var b := put(o2, "plt-A3", "B3")
	var e12: Platoon = o2.platoons["e-plt-12"]      # 敵機槍在 C3
	o2.apply_orders("us", [Order.make("plt-A3", "seize", "D3")])
	o2.advance_for(31.0)
	h.check(b.sector == "C3" and e12.sector == "C3" and b.state == "moving", "31 秒到有敵軍的 C3（中途分區，狀態仍 moving）")
	o2.advance_for(31.0)
	h.check(b.sector == "C3", "停一回合：62 秒仍在 C3")
	o2.advance_for(31.0)
	h.check(b.sector == "D3" and b.state == "idle", "93 秒後繼續走到 D3 並待命")

	# ---- 機動力：雨天戰車減半（60 秒一格）；雪天步兵減半 ----
	var o3 := make_orbat()
	o3.weather = "rain"
	var tank := put(o3, "e-plt-13", "E4")
	o3.apply_orders("enemy", [Order.make("e-plt-13", "seize", "E2")])
	o3.advance_for(29.0)
	h.check(tank.sector == "E4", "雨天戰車機動力 0.5：29 秒還沒跨過格線（晴天 15 秒就跨）")
	o3.advance_for(31.0)
	h.check(tank.sector == "E3" and tank.anchor.distance_to(o3.map.center_of("E3")) < 2.0, "60 秒走到 E3 中心附近（60 秒一格）")
	o3.advance_for(42.0)
	h.check(tank.sector == "E2", "102 秒跨進 E2")
	o3.weather = "snow"
	var inf := put(o3, "plt-A2", "A2")
	o3.apply_orders("us", [Order.make("plt-A2", "seize", "A4")])
	o3.advance_for(29.0)
	h.check(inf.sector == "A2", "雪天步兵也減半：29 秒還在 A2")

	# ---- 通行：戰車不進森林、河川要工兵；側翼進入點也擋 ----
	var o4 := make_orbat()
	var t13 := put(o4, "e-plt-13", "E4")
	o4.apply_orders("enemy", [Order.make("e-plt-13", "seize", "E1")])     # E1 森林
	o4.advance_for(31.0)
	h.check(t13.sector == "E4" and t13.state == "idle", "目標是森林 → 戰車原地不動")
	o4.apply_orders("enemy", [Order.make("e-plt-13", "seize", "D4")])     # D4 河川，敵方沒有工兵
	o4.advance_for(31.0)
	h.check(t13.sector == "E4", "沒工兵過不了河")
	var our_tank := o4.add_platoon({"id": "plt-T1", "name": "T1 戰車排", "echelon": "platoon", "type": "tank", "parent": "co-A", "strength": 1.0, "state": "idle", "sector": "D3"}, "us", o4.map.center_of("D3"))
	put(o4, "plt-A8", "D4")
	o4.apply_orders("us", [Order.make("plt-T1", "seize", "D4")])
	o4.advance_for(31.0)
	h.check(our_tank.sector == "D4", "本方工兵在河上 → 戰車可過")
	o4.place_platoon(our_tank, o4.map.center_of("D1"))
	o4.apply_orders("us", [Order.make("plt-T1", "flank", "E1")])          # 進入點 D1（離主力最遠），目標 E1 是森林
	o4.advance_for(31.0)
	h.check(our_tank.sector == "D1" and our_tank.state == "idle", "側翼進入點就在腳下但目標是森林 → 原地（M0 的 dest in avoid 守門）")

	# ---- 連令拆排、排令優先、直轄不碰、flank 拆法、退回、同單位兩道令 ----
	var o5 := make_orbat()
	o5.platoons["plt-A3"].controlled_by = "player"
	o5.platoons["plt-A3"].task = {"type": "hold", "target": "B1"}
	o5.platoons["plt-A6"].state = "routed"
	o5.platoons["plt-A7"].state = "destroyed"
	var rej5 := o5.apply_orders("us", [Order.make("plt-A1", "hold", "B2"), Order.make("co-A", "seize", "C3")])
	h.check(rej5.is_empty() and o5.platoons["plt-A2"].task == {"type": "seize", "target": "C3"} and o5.platoons["plt-A8"].task["type"] == "seize", "連令拆給子排")
	h.check(o5.platoons["plt-A1"].task == {"type": "hold", "target": "B2"}, "同批排令優先於連令")
	h.check(o5.platoons["plt-A3"].task == {"type": "hold", "target": "B1"}, "參謀長的連令不碰總司令直轄的排")
	h.check(o5.platoons["plt-A6"].task.is_empty() and o5.platoons["plt-A7"].task.is_empty(), "潰散與殲滅的排不被連令拆到")
	o5.apply_orders("us", [Order.make("co-A", "seize", "C2", "player")])
	h.check(o5.platoons["plt-A3"].task == {"type": "seize", "target": "C2"}, "玩家的連令可以拆給直轄排")
	o5.apply_orders("us", [Order.make("co-A", "flank", "C3")])
	h.check(o5.platoons["plt-A1"].task == {"type": "hold", "target": "B2"} and o5.platoons["plt-A2"].task["type"] == "flank", "連 flank：戰情板順序第一個排原地 hold，其餘 flank")
	o5.apply_orders("us", [Order.make("plt-A2", "seize", "C3"), Order.make("plt-A2", "hold", "B2")])
	h.check(o5.platoons["plt-A2"].task == {"type": "hold", "target": "B2"}, "同一單位同批兩道令後者為準")
	var bad := o5.apply_orders("us", [Order.make("plt-Z9", "seize", "C3"), Order.make("plt-A1", "support", "plt-A1"), Order.make("plt-A2", "seize", "Z9"), Order.make("e-plt-11", "hold", "C3")])
	h.check(bad.size() == 4 and bad[0].contains("不存在") and bad[1].contains("support") and bad[2].contains("不是分區") and bad[3].contains("不存在"), "壞命令以人話退回（含對敵軍下令）")

	# ---- support／hold／reserve／withdraw／flank 路徑；直轄排照自己任務走 ----
	var o6 := make_orbat()
	var a2: Platoon = o6.platoons["plt-A2"]          # A2
	o6.apply_orders("us", [Order.make("plt-A2", "support", "plt-A5")])
	o6.advance_for(1.0)
	h.check(a2.sector == "A2" and a2.state == "idle", "support：已在友軍相鄰格 → 不動")
	o6.place_platoon(a2, o6.map.center_of("A5"))
	o6.advance_for(93.0)
	h.check(a2.sector == "A2" and a2.state == "idle", "support：從 A5 走 3 格到 B2 的相鄰格就停（A2 與 B3 同距，取 id 序 A2）")
	var a3 := put(o6, "plt-A3", "B1")
	o6.apply_orders("us", [Order.make("plt-A3", "hold", "B1")])
	o6.advance_for(2.0)
	h.check(a3.sector == "B1" and a3.state == "idle" and a3.anchor == o6.map.center_of("B1"), "hold：已在目標分區就不動")
	var a8 := put(o6, "plt-A8", "A1")
	a8.controlled_by = "player"
	o6.apply_orders("us", [Order.make("plt-A8", "reserve", "A3", "player"), Order.make("co-A", "hold", "B2")])
	o6.advance_for(72.0)
	h.check(a8.sector == "A3" and a8.state == "idle" and a8.task["type"] == "reserve", "reserve：直轄排照自己的任務走到 A3 待命（經 A2 的空站位，約 65 秒），不被參謀長連令蓋掉")
	var a4b := put(o6, "plt-A4", "C2")
	o6.apply_orders("us", [Order.make("plt-A4", "withdraw", "A2")])
	o6.advance_for(31.0)
	h.check(a4b.sector == "B2" and a4b.state == "moving", "withdraw：朝目標走（第一步往左）")
	var o7 := make_orbat()
	var f := put(o7, "plt-A2", "B3")                  # 主力 B2（plt-A1）；目標 C3 的四鄰 C2/B3/D3/C4 離 B2 最遠＝D3（同距取第一個）
	o7.apply_orders("us", [Order.make("plt-A2", "flank", "C3")])
	o7.advance_for(31.0)
	h.check(f.sector == "B2" and f.state == "moving", "flank：繞路不穿過 C3，BFS 先往上 → B3 → B2 → C2 → D2 → D3")
	o7.place_platoon(f, o7.map.center_of("D3"))
	o7.advance_for(31.0)
	h.check(f.sector == "C3" and f.state == "idle", "flank：到了進入點 D3 再進目標 C3")

	# ---- 戰力聚合、連狀態、潰散撤退、全殲滅不當機 ----
	var o8 := make_orbat()
	var p1: Platoon = o8.platoons["plt-A1"]
	p1.kill(4)
	o8.aggregate()
	h.check(h.approx(p1.strength, 0.56) and p1.alive_count() == 5, "殺 4 人 → 戰力 5/9 = 0.56")
	h.check(h.approx(o8.companies["co-A"]["strength"], (0.56 + 7.0) / 8.0, 0.001), "連戰力＝子排平均")
	for pid in ["plt-A1", "plt-A2", "plt-A3", "plt-A4", "plt-A5", "plt-A6", "plt-A7", "plt-A8"]:
		o8.platoons[pid].state = "routed"
	o8.aggregate()
	h.check(o8.companies["co-A"]["state"] == "routed", "子排全潰散 → 連潰散")
	for pid in ["plt-A1", "plt-A2", "plt-A3", "plt-A4", "plt-A5", "plt-A6", "plt-A7", "plt-A8"]:
		o8.platoons[pid].state = "destroyed"
	o8.advance_for(1.0)
	h.check(o8.companies["co-A"]["state"] == "destroyed" and o8.companies["co-A"]["sector"] == "A1", "子排全殲滅 → 連殲滅、分區保留最後值、不當機")
	var e12b := put(o8, "e-plt-12", "C3")
	o8.map.set_sector_owner("C3", "enemy")
	put(o8, "e-plt-11", "C3")
	e12b.state = "routed"
	e12b.kill(7)
	o8.advance_for(31.0)
	h.check(e12b.sector == "C3" and e12b.state == "routed", "潰散但本方分區裡沒敵軍 → 不動")
	var o9 := make_orbat()
	var e12c := put(o9, "e-plt-12", "C3")
	o9.map.set_sector_owner("C3", "enemy")
	put(o9, "plt-A1", "C3")                             # 我方進 C3 → 對敵方而言 C3 有敵軍
	e12c.state = "routed"
	e12c.kill(7)
	o9.advance_for(31.0)
	h.check(e12c.sector == "D3", "潰散往最近沒敵軍的本方分區 D4 退，第一步 D3（右）")
	o9.advance_for(31.0)
	h.check(e12c.sector == "D4" and e12c.state == "routed", "退到 D4 就停，狀態仍潰散")
	var rc := put(o9, "e-plt-14", "C5")                 # 迫砲在 C5，本方 D5 河川
	o9.map.set_sector_owner("C5", "enemy")
	put(o9, "plt-A2", "C5")
	rc.state = "routed"
	o9.apply_orders("enemy", [Order.make("e-plt-14", "withdraw", "E5")])
	o9.advance_for(31.0)
	h.check(rc.sector == "D5", "潰散＋withdraw 令照令走（第一步 D5）")
	var o10 := make_orbat()
	var r7 := put(o10, "plt-A7", "D1")                  # 偵察排 speed 2
	o10.map.set_sector_owner("B1", "us")
	put(o10, "e-plt-11", "D1")
	r7.state = "routed"
	o10.advance_for(30.0)
	h.check(r7.sector == "C1" and r7.anchor.distance_to(o10.map.center_of("C1")) < 2.0, "潰散的偵察排 30 秒只退 1 格（§2：不論兵種；原速會到 B1）")
	h.finish()
