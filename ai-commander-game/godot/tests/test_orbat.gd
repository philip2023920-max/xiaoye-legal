extends SceneTree
## 施工單 11 無頭測試：部隊樹、速度、機動力、通行、六種任務、連令拆排、戰力聚合、潰散撤退。
## 期望值來自 docs/10 §2、§3（1 回合＝30 秒、BFS 鄰格順序上左右下）、樣板 board_deployed_balanced.json 與 enemy_script_v1.json。
##   godot --headless --path . -s tests/test_orbat.gd

const DT := 1.0 / 60.0

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 34)
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

func _run() -> void:
	# ---- 生成 ----
	var o := make_orbat()
	h.check(o.leaves("us").size() == 8 and o.total_soldiers("us") == 72, "均衡範本：8 排 72 人")
	h.check(o.leaves("enemy").size() == 6 and o.total_soldiers("enemy") == 54, "敵方 normal 劇本：6 排 54 人")
	h.check(o.companies.has("co-A") and o.companies.has("e-co-1") and o.children_of("co-A").size() == 8, "連是容器，子排 8 個")
	var a1: Platoon = o.platoons["plt-A1"]
	var a4: Platoon = o.platoons["plt-A4"]
	h.check(a1.sector == "B2" and a1.unit_type == "infantry" and a4.sector == "A1" and a4.unit_type == "mg", "排的分區與兵種照樣板")
	h.check(a1.soldiers[0].head_color() != o.platoons["e-plt-13"].soldiers[0].head_color(), "兵種用頭色分（步兵≠戰車）")
	h.check(o.companies["co-A"]["strength"] == 1.0 and o.companies["co-A"]["sector"] == "B2", "連戰力＝子排平均、分區＝最強子排（同強取 id 序 → plt-A1 的 B2）")
	o.advance_for(1.0)
	h.check(a1.sector == "B2" and a1.state == "idle" and o.t > 0.99, "沒有命令就原地待命")

	# ---- 速度與路線（§2：speed 1 → 20 m／30 s；BFS 上左右下 → B2→C2→C3）----
	var rej := o.apply_orders("us", [Order.make("plt-A1", "seize", "C3")])
	h.check(rej.is_empty() and a1.task == {"type": "seize", "target": "C3"} and a1.state == "idle", "排接到 seize C3")
	o.advance_for(31.0)
	h.check(a1.sector == "C2" and a1.state == "moving", "31 秒後在 C2（第一步往右；B2 有兩個排，站位離中心 3.5 m，20 秒就跨線）")
	o.advance_for(36.0)
	h.check(a1.sector == "C3" and a1.state == "idle" and a1.anchor == o.map.center_of("C3"), "67 秒後到 C3 中心並待命（23.5 m + 20 m ÷ 0.667 m/s ≈ 65 秒）")
	h.check(o.events.any(func(e: String) -> bool: return e.begins_with("參謀長令 A1 步兵排 奪取 C3")), "事件流記下命令")

	# ---- 偵察排速度 2：B1 → C3 共 3 格，45 秒 ----
	var a7: Platoon = o.platoons["plt-A7"]
	a7.place(o.map.center_of("B1")); a7.sector = "B1"
	o.apply_orders("us", [Order.make("plt-A7", "seize", "C3")])
	o.advance_for(46.0)
	h.check(a7.sector == "C3" and a7.anchor == o.map.center_of("C3"), "偵察排速度 2：B1 到 C3 共 3 格 45 秒到中心")

	# ---- 進敵格停一回合（§2）：我方 A2 從 A2 seize C4，經 B2/C2 … 改用明確情境 ----
	var o2 := make_orbat()
	var b: Platoon = o2.platoons["plt-A3"]          # 步兵在 B1
	b.place(o2.map.center_of("B3")); b.sector = "B3"
	var e12: Platoon = o2.platoons["e-plt-12"]      # 敵機槍在 C3
	o2.apply_orders("us", [Order.make("plt-A3", "seize", "D3")])
	o2.advance_for(31.0)
	h.check(b.sector == "C3" and e12.sector == "C3", "31 秒進到有敵軍的 C3")
	o2.advance_for(31.0)
	h.check(b.sector == "C3", "停一回合：62 秒仍在 C3")
	o2.advance_for(31.0)
	h.check(b.sector == "D3", "93 秒後繼續走到 D3")

	# ---- 機動力：雨天戰車減半（60 秒一格）；雪天步兵減半 ----
	var o3 := make_orbat()
	o3.weather = "rain"
	var tank: Platoon = o3.platoons["e-plt-13"]      # 敵戰車在 E4
	o3.apply_orders("enemy", [Order.make("e-plt-13", "seize", "E2")])
	o3.advance_for(29.0)
	h.check(tank.sector == "E4", "雨天戰車機動力 0.5：29 秒還沒跨過格線（晴天 15 秒就跨）")
	o3.advance_for(33.0)
	h.check(tank.sector == "E3" and tank.anchor.distance_to(o3.map.center_of("E3")) < 1.0, "62 秒剛走到 E3 中心（60 秒一格）")
	o3.advance_for(40.0)
	h.check(tank.sector == "E2", "102 秒跨進 E2")
	o3.weather = "snow"
	var inf: Platoon = o3.platoons["plt-A2"]        # 步兵在 A2
	o3.apply_orders("us", [Order.make("plt-A2", "seize", "A4")])
	o3.advance_for(29.0)
	h.check(inf.sector == "A2", "雪天步兵也減半：29 秒還在 A2")

	# ---- 通行：戰車不進森林、河川要工兵 ----
	var o4 := make_orbat()
	var t13: Platoon = o4.platoons["e-plt-13"]
	o4.apply_orders("enemy", [Order.make("e-plt-13", "seize", "E1")])     # E1 森林
	o4.advance_for(31.0)
	h.check(t13.sector == "E4" and t13.state == "idle", "目標是森林 → 戰車原地不動")
	o4.apply_orders("enemy", [Order.make("e-plt-13", "seize", "D4")])     # D4 河川，敵方沒有工兵
	o4.advance_for(31.0)
	h.check(t13.sector == "E4", "沒工兵過不了河")
	var our_tank := o4.add_platoon({"id": "plt-T1", "name": "T1 戰車排", "echelon": "platoon", "type": "tank", "parent": "co-A", "strength": 1.0, "state": "idle", "sector": "D3"}, "us", o4.map.center_of("D3"))
	var eng: Platoon = o4.platoons["plt-A8"]
	eng.place(o4.map.center_of("D4")); eng.sector = "D4"
	o4.apply_orders("us", [Order.make("plt-T1", "seize", "D4")])
	o4.advance_for(31.0)
	h.check(our_tank.sector == "D4", "本方工兵在河上 → 戰車可過")

	# ---- 連令拆排、排令優先、直轄不碰、flank 拆法、退回 ----
	var o5 := make_orbat()
	o5.platoons["plt-A3"].controlled_by = "player"
	o5.platoons["plt-A3"].task = {"type": "hold", "target": "B1"}
	var rej5 := o5.apply_orders("us", [Order.make("plt-A1", "hold", "B2"), Order.make("co-A", "seize", "C3")])
	h.check(rej5.is_empty() and o5.platoons["plt-A2"].task == {"type": "seize", "target": "C3"} and o5.platoons["plt-A8"].task["type"] == "seize", "連令拆給子排")
	h.check(o5.platoons["plt-A1"].task == {"type": "hold", "target": "B2"}, "同批排令優先於連令")
	h.check(o5.platoons["plt-A3"].task == {"type": "hold", "target": "B1"}, "參謀長的連令不碰總司令直轄的排")
	o5.apply_orders("us", [Order.make("co-A", "seize", "C2", "player")])
	h.check(o5.platoons["plt-A3"].task == {"type": "seize", "target": "C2"}, "玩家的連令可以拆給直轄排")
	o5.apply_orders("us", [Order.make("co-A", "flank", "C3")])
	h.check(o5.platoons["plt-A1"].task == {"type": "hold", "target": "B2"} and o5.platoons["plt-A2"].task["type"] == "flank", "連 flank：第一個排原地 hold，其餘 flank")
	var bad := o5.apply_orders("us", [Order.make("plt-Z9", "seize", "C3"), Order.make("plt-A1", "support", "plt-A1"), Order.make("plt-A2", "seize", "Z9"), Order.make("e-plt-11", "hold", "C3")])
	h.check(bad.size() == 4 and bad[0].contains("不存在") and bad[1].contains("support") and bad[2].contains("不是分區") and bad[3].contains("不存在"), "壞命令以人話退回（含對敵軍下令）")

	# ---- support：走到友軍相鄰格就停 ----
	var o6 := make_orbat()
	var a2: Platoon = o6.platoons["plt-A2"]          # A2
	var a5: Platoon = o6.platoons["plt-A5"]          # B2 迫砲
	o6.apply_orders("us", [Order.make("plt-A2", "support", "plt-A5")])
	o6.advance_for(1.0)
	h.check(a2.sector == "A2" and a2.state == "idle", "已在友軍相鄰格 → 不動")
	a2.place(o6.map.center_of("A5")); a2.sector = "A5"
	a2.step_target = ""
	o6.advance_for(93.0)
	h.check(a2.sector == "A2" and a2.state == "idle", "從 A5 走 3 格到 B2 的相鄰格就停：A2 與 B3 同距 3，取 id 序 A2")

	# ---- 戰力聚合與潰散撤退 ----
	var o7 := make_orbat()
	var p1: Platoon = o7.platoons["plt-A1"]
	p1.kill(4)
	o7.aggregate()
	h.check(h.approx(p1.strength, 0.56) and p1.alive_count() == 5, "殺 4 人 → 戰力 5/9 = 0.56")
	h.check(h.approx(o7.companies["co-A"]["strength"], (0.56 + 7.0) / 8.0, 0.001), "連戰力＝子排平均")
	var e12b: Platoon = o7.platoons["e-plt-12"]      # 敵機槍在 C3（敵方擁有？樣板 C3 無主）
	o7.map.set_sector_owner("C3", "enemy")
	p1.place(o7.map.center_of("C3")); p1.sector = "C3"   # 我方進 C3 → 對敵方而言 C3 有敵軍
	e12b.state = "routed"
	e12b.kill(7)
	o7.advance_for(31.0)
	h.check(e12b.sector == "D3", "潰散往最近沒敵軍的本方分區 D4 退，第一步 D3（右）")
	o7.advance_for(31.0)
	h.check(e12b.sector == "D4" and e12b.state == "routed", "退到 D4 就停，狀態仍潰散")
	h.finish()
