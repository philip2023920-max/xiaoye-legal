extends SceneTree
## 施工單 12 無頭測試：docs/10 §4 v1 三個手算例（30 秒合計＝M0 一回合）、工兵、潰散／殲滅門檻、撤退不開火、天氣變化。
##   godot --headless --path . -s tests/test_combat.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 30)
	_run.call_deferred()

## 5×5 全平地（cover 0.2）的小戰情板；terrain 可覆寫某幾格。
func mini_board(weather: String = "clear", tod: String = "day", terrain: Dictionary = {}) -> Dictionary:
	var sectors := {}
	for r in 5:
		for c in 5:
			var sid := SectorMap.id_of(c, r)
			var t: String = terrain.get(sid, "open")
			var cover: float = {"open": 0.2, "hill": 0.4, "forest": 0.5, "town": 0.6, "river": 0.1}[t]
			sectors[sid] = {"id": sid, "terrain": t, "cover": cover}
	return {"schema_version": "0.2", "battle_id": "mini", "t": 0, "era": "ww2_1944", "weather": weather, "time_of_day": tod,
		"map": {"cols": 5, "rows": 5, "sectors": sectors}, "orbat": [], "objectives": [], "events": []}

func unit(id: String, typ: String, sector: String, task_type: String = "", target: String = "", strength: float = 1.0) -> Dictionary:
	var d := {"id": id, "name": id, "echelon": "platoon", "type": typ, "parent": null, "strength": strength, "state": "idle", "sector": sector}
	if task_type != "":
		d["task"] = {"type": task_type, "target": target}
	return d

func make(board: Dictionary, us: Array, enemy: Array) -> Orbat:
	board["orbat"] = us
	var map := SectorMap.new()
	get_root().add_child(map)
	map.build_from_board(board)
	var o := Orbat.new()
	get_root().add_child(o)
	o.setup(map, Rules.load_era())
	o.build(board, enemy)
	return o

func _run() -> void:
	# ---- 例 1：步兵 vs 戰車，雨天平地日間 → 0.1044／0.216 ----
	var o1 := make(mini_board("rain"), [unit("inf", "infantry", "C3", "hold", "C3")], [unit("tank", "tank", "C3", "hold", "C3")])
	o1.advance_for(30.5)
	var tank: Platoon = o1.platoons["tank"]
	var inf: Platoon = o1.platoons["inf"]
	h.check(h.approx(tank.strength, 1.0 - 0.1044, 0.0011), "例 1：戰車 30 秒受 0.1044（容差 1%）")
	h.check(h.approx(inf.strength, 1.0 - 0.216, 0.0022), "例 1：步兵 30 秒受 0.216")
	h.check(tank.alive_count() == 8 and inf.alive_count() == 7, "倒下人數＝round((1−戰力)×9)：戰車 1 人、步兵 2 人")
	h.check(inf.state == "engaged" and tank.state == "engaged", "交戰中狀態 engaged")
	h.check(o1.resolver.tracers.size() >= 2, "這一秒有射線")

	# ---- 例 2：機槍在霧夜城鎮 vs 步兵 → 0.0273／0.021 ----
	var o2 := make(mini_board("fog", "night", {"C3": "town"}), [unit("mg", "mg", "C3", "hold", "C3")], [unit("e", "infantry", "C3", "hold", "C3")])
	o2.advance_for(30.5)
	h.check(h.approx(o2.platoons["e"].strength, 1.0 - 0.0273, 0.0003), "例 2：步兵受 0.0273（掩蔽封頂 0.8、倍率 0.42）")
	h.check(h.approx(o2.platoons["mg"].strength, 1.0 - 0.021, 0.0003), "例 2：機槍受 0.021")

	# ---- 例 3：迫砲鄰格間接射擊，晴天平地 → 0.38／0.20／0 ----
	var o3 := make(mini_board(), [unit("inf", "infantry", "C3", "hold", "C3"), unit("mortar", "mortar", "B3", "hold", "B3")], [unit("e", "infantry", "C3", "hold", "C3")])
	o3.advance_for(30.5)
	h.check(h.approx(o3.platoons["e"].strength, 1.0 - 0.38, 0.004), "例 3：敵步兵受 (1.0+0.9)×0.8×0.25 = 0.38")
	h.check(h.approx(o3.platoons["inf"].strength, 0.80, 0.002), "例 3：我步兵受 0.20")
	h.check(o3.platoons["mortar"].strength == 1.0 and o3.platoons["mortar"].state == "idle", "例 3：迫砲不在格內不被打、不標 engaged")
	var o3b := make(mini_board(), [unit("mortar", "mortar", "B3", "hold", "B3")], [unit("e", "infantry", "C3", "hold", "C3")])
	o3b.advance_for(5.5)
	h.check(o3b.platoons["e"].strength == 1.0, "只有迫砲在鄰格、沒有本方單位在該格交戰 → 不開火")

	# ---- 例 4：工兵固守本格 → 本方掩蔽 +0.1；敵受 0.36、我各 0.0875 ----
	var o4 := make(mini_board(), [unit("inf", "infantry", "C3", "hold", "C3"), unit("eng", "engineer", "C3", "hold", "C3")], [unit("e", "infantry", "C3", "hold", "C3")])
	o4.advance_for(30.5)
	h.check(h.approx(o4.platoons["e"].strength, 1.0 - 0.36, 0.004), "例 4：敵受 (1.0+0.8)×0.8×0.25 = 0.36")
	h.check(h.approx(o4.platoons["inf"].strength, 1.0 - 0.0875, 0.001) and h.approx(o4.platoons["eng"].strength, 1.0 - 0.0875, 0.001), "例 4：我方各受 1.0×0.5×0.7×0.25 = 0.0875（工兵只加本方）")

	# ---- 反戰車 vs 戰車 → 0.204／0.236 ----
	var o5 := make(mini_board(), [unit("at", "at", "C3", "hold", "C3")], [unit("tank", "tank", "C3", "hold", "C3")])
	o5.advance_for(30.5)
	h.check(h.approx(o5.platoons["tank"].strength, 1.0 - 0.204, 0.0021) and h.approx(o5.platoons["at"].strength, 1.0 - 0.236, 0.0024), "反戰車對戰車 0.204、戰車對反戰車 0.236")

	# ---- 回合快照：第二回合用新戰力（30 秒後 tank 0.8956 → 第二個 30 秒步兵受 0.216×0.8956）----
	o1.advance_for(30.0)
	h.check(h.approx(inf.strength, 0.784 - 0.216 * 0.8956, 0.003), "第二回合的攻擊用第二回合開始的戰力快照")

	# ---- 門檻：潰散（< 0.30）→ 任務清空、事件；殲滅（≤ 0.05）→ 事件、人全倒；潰散單位不開火但會被打 ----
	var o6 := make(mini_board(), [unit("u1", "infantry", "C3", "hold", "C3"), unit("u2", "infantry", "C3", "hold", "C3"), unit("u3", "infantry", "C3", "hold", "C3")],
		[unit("e", "infantry", "C3", "hold", "C3", 0.32)])
	o6.map.set_sector_owner("D3", "enemy")
	var e: Platoon = o6.platoons["e"]
	o6.advance_for(2.5)
	h.check(e.state == "routed" and e.task.is_empty() and o6.events.any(func(ev: Dictionary) -> bool: return ev["kind"] == "routed" and ev["unit"] == "e"), "每秒受 0.6/30=0.02：第 2 秒 0.28 < 0.30 → 潰散、任務清空、事件")
	var before: float = o6.platoons["u1"].strength
	var e_after_rout := e.strength
	o6.advance_for(1.0)
	h.check(o6.platoons["u1"].strength == before and e.strength == e_after_rout and o6.platoons["u1"].state == "idle", "敵方只剩潰散單位 → 沒有交戰（§4：雙方都要有能戰鬥的單位），我方回 idle")
	o6.advance_for(20.0)
	h.check(e.sector != "C3" or e.anchor != o6.map.center_of("C3"), "潰散單位往本方分區 D3 退")
	var b6 := mini_board()
	b6["map"]["sectors"]["C3"]["cover"] = 0.0
	var o6b := make(b6, [unit("u1", "infantry", "C3", "hold", "C3"), unit("u2", "infantry", "C3", "hold", "C3"), unit("u3", "infantry", "C3", "hold", "C3"), unit("u4", "mg", "C3", "hold", "C3")],
		[unit("e", "infantry", "C3", "hold", "C3", 0.06), unit("e2", "infantry", "C3", "hold", "C3", 1.0)])
	var ed: Platoon = o6b.platoons["e"]
	h.check(h.approx(ed.strength, 0.11) and ed.alive_count() == 1, "開局 0.06 → 倒 8 人剩 1 人 → 戰力重算 1/9 = 0.11（§15）")
	o6b.advance_for(1.5)
	h.check(ed.state == "routed" and o6b.platoons["e2"].state == "engaged" and o6b.platoons["u1"].state == "engaged", "第 1 秒殘排 < 0.30 潰散；同格還有能戰鬥的敵排 → 交戰繼續，潰散排仍是目標")
	o6b.advance_for(19.0)
	h.check(ed.state == "destroyed" and ed.alive_count() == 0 and ed.task.is_empty() and o6b.events.any(func(ev: Dictionary) -> bool: return ev["kind"] == "destroyed" and ev["unit"] == "e"), "每秒受 4.3×(0.11/1.11)×0.25/30 ≈ 0.0036：約 17 秒後 ≤ 0.05 → 殲滅、任務清空、人全倒、事件")
	var o6c := make(mini_board(), [unit("u1", "infantry", "C3", "hold", "C3"), unit("u2", "infantry", "C3", "hold", "C3"), unit("u3", "infantry", "C3", "hold", "C3")], [unit("e", "infantry", "C3", "hold", "C3", 0.06)])
	o6c.advance_for(2.5)
	h.check(o6c.platoons["e"].state == "routed" and o6c.platoons["e"].strength > 0.05 and o6c.platoons["u1"].state == "idle" and o6c.resolver.fighting.is_empty(), "落單的殘排潰散後就不再被瞄準（§4 要雙方都有能戰鬥的單位），在 M1 裡它逃得掉（§15 註明與 M0 的差異）")

	# ---- 撤退中不開火；潰散撤出（有本方安全分區就退）----
	var o7 := make(mini_board(), [unit("u", "infantry", "C3", "withdraw", "A3")], [unit("e", "infantry", "C3", "hold", "C3")])
	o7.advance_for(1.5)
	h.check(o7.platoons["e"].strength == 1.0 and o7.platoons["u"].strength < 1.0, "withdraw 的單位不開火但會被打")
	var o8 := make(mini_board(), [unit("u1", "infantry", "C3", "hold", "C3"), unit("u2", "infantry", "C3", "hold", "C3"), unit("u3", "infantry", "C3", "hold", "C3")],
		[unit("e", "infantry", "C3", "hold", "C3", 0.32)])
	o8.map.set_sector_owner("D3", "enemy")
	o8.advance_for(2.5)
	o8.advance_for(31.0)
	h.check(o8.platoons["e"].sector == "D3" and o8.platoons["e"].state == "routed", "潰散後退到最近沒敵軍的本方分區 D3（§2 v1.1）")

	# ---- 天氣／時段變化：事件與效果 ----
	var o9 := make(mini_board(), [unit("u", "infantry", "C3", "hold", "C3")], [unit("e", "infantry", "C3", "hold", "C3")])
	o9.advance_for(30.5)
	h.check(h.approx(o9.platoons["e"].strength, 0.80, 0.002), "晴日 30 秒 0.20")
	o9.set_conditions("rain", "night")
	h.check(o9.weather == "rain" and o9.time_of_day == "night" and o9.events.filter(func(ev: Dictionary) -> bool: return ev["kind"] == "weather").size() == 2, "天氣轉雨、進入夜間各一筆 weather 事件")
	h.check(o9.events.any(func(ev: Dictionary) -> bool: return ev["text"] == "天氣轉雨") and o9.events.any(func(ev: Dictionary) -> bool: return ev["text"] == "進入夜間"), "事件文字與 M0 相同")
	var e_before: float = o9.platoons["e"].strength
	o9.advance_for(30.0)
	h.check(h.approx(e_before - o9.platoons["e"].strength, 0.8 * 0.6 * 0.25 * 0.54, 0.001), "雨夜：掩蔽 0.2+0.2=0.4、倍率 0.9×0.6=0.54 → 攻方快照 0.8×1.0×0.6×0.25×0.54 = 0.0648")
	print("  （下面一個 ERROR 是故意的：壞天氣值）")
	o9.set_conditions("hail", "")
	h.check(o9.weather == "rain", "不在表內的天氣不會寫進去")
	h.check(o9.rules.has_unit("armor") and not o9.rules.has_unit("cavalry"), "兵種別名與未知兵種判定")
	h.finish()
