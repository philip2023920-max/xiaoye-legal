class_name Orbat
extends Node3D
## 雙方部隊樹（排是葉節點、連是容器），以及每個物理 tick 的移動推進。
##
## 時間對應（ADR-0014 D19）：M0 一回合＝30 秒；速度 = speed × 20 m ÷ 30 s × 機動力（機動力 0.5 ＝ 60 秒一格，
## 是 M0「只在偶數回合動」的連續版）。分區歸屬看錨點的實際位置（跨過格線就算進了下一格）；走到分區中心才算「到達」，
## 到達有敵軍的分區會停 TURN_SECONDS 再繼續（M0「進敵格就停、下回合再動」的連續版）。

const TURN_SECONDS := 30.0
const ARRIVE_EPS := 0.5

var map: SectorMap
var rules: Rules
var grid: SectorGrid
var nav: RTSNavGrid = null          # 有就繞掩體；沒有就直線走到分區中心
var weather := "clear"
var time_of_day := "day"
var t := 0.0                        # 遊戲秒
var platoons := {}                  # id -> Platoon（雙方）
var companies := {}                 # id -> Dictionary（雙方；見 _company_dict）
var events: Array[String] = []      # 本 tick 以來的事件文字（施工單 13 收走）

func setup(map_: SectorMap, rules_: Rules) -> void:
	map = map_
	rules = rules_
	grid = SectorGrid.new(map.cols, map.rows)

## 從戰情板的 orbat（我方）與敵方劇本的 units（敵方）生成；同格的排在分區內排開。
func build(board: Dictionary, enemy_units: Array = []) -> void:
	weather = str(board.get("weather", "clear"))
	time_of_day = str(board.get("time_of_day", "day"))
	_build_side("us", board.get("orbat", []))
	_build_side("enemy", enemy_units)
	aggregate()

func _build_side(side: String, units: Array) -> void:
	var leaves: Array = []
	for u in units:
		if str(u.get("echelon", "platoon")) == "platoon":
			leaves.append(u)
		else:
			companies[str(u["id"])] = _company_dict(u, side)
	# 同一分區裡的排排成方陣
	var by_sector := {}
	for u in leaves:
		var sid := str(u["sector"])
		if not by_sector.has(sid):
			by_sector[sid] = []
		by_sector[sid].append(u)
	for sid in by_sector.keys():
		var group: Array = by_sector[sid]
		var slots := RTSKit.formation(map.center_of(sid), group.size(), 7.0)
		for i in group.size():
			add_platoon(group[i], side, slots[i])

func add_platoon(data: Dictionary, side: String, at: Vector3) -> Platoon:
	var p := Platoon.new()
	p.setup(data, side, at)
	p.sector = map.sector_at(at)
	p.vision_radius = rules.sight(p.unit_type, weather, time_of_day) * SectorMap.SECTOR_SIZE
	add_child(p)
	platoons[p.id] = p
	return p

func _company_dict(u: Dictionary, side: String) -> Dictionary:
	return {"id": str(u["id"]), "name": str(u.get("name", u["id"])), "echelon": str(u.get("echelon", "company")), "side": side,
		"parent": u.get("parent"), "strength": float(u.get("strength", 1.0)), "state": str(u.get("state", "idle")),
		"sector": str(u.get("sector", "")), "task": {}, "controlled_by": str(u.get("controlled_by", "ai")), "cost": int(u.get("cost", 0)), "type": "mixed"}

# ---- 查詢 ----
func leaves(side: String) -> Array[Platoon]:
	var out: Array[Platoon] = []
	var ids := platoons.keys()
	ids.sort()
	for pid in ids:
		var p: Platoon = platoons[pid]
		if p.side == side:
			out.append(p)
	return out

func children_of(company_id: String) -> Array:
	var out: Array = []
	for p in leaves(companies[company_id]["side"]):
		if p.parent_id == company_id:
			out.append(p)
	return out

func other(side: String) -> String:
	return "enemy" if side == "us" else "us"

func unit_sector(side: String, unit_id: String) -> String:
	if platoons.has(unit_id):
		var p: Platoon = platoons[unit_id]
		return p.sector if (p.side == side and p.state != "destroyed") else ""
	if companies.has(unit_id) and companies[unit_id]["side"] == side and companies[unit_id]["state"] != "destroyed":
		return companies[unit_id]["sector"]
	return ""

func hostile_sectors(side: String) -> Dictionary:
	var out := {}
	for e in leaves(other(side)):
		if e.state != "destroyed":
			out[e.sector] = true
	return out

func own_sectors(side: String) -> Array[String]:
	var out: Array[String] = []
	for sid in map.sectors.keys():
		if map.sectors[sid]["owner"] == side:
			out.append(sid)
	return out

func safe_own_sectors(side: String) -> Dictionary:
	var hostile := hostile_sectors(side)
	var out := {}
	for sid in own_sectors(side):
		if not hostile.has(sid):
			out[sid] = true
	return out

func engineer_sectors(side: String) -> Dictionary:
	var out := {}
	for p in leaves(side):
		if rules.resolve_type(p.unit_type) == "engineer" and p.state != "routed" and p.state != "destroyed":
			out[p.sector] = true
	return out

## 這個排進不去的分區（戰車 vs 森林／河川；河川有本方工兵在那格就能過）。
func blocked_sectors(p: Platoon) -> Dictionary:
	var out := {}
	var eng := engineer_sectors(p.side)
	for sid in map.sectors.keys():
		if not rules.can_enter(p.unit_type, map.sectors[sid]["terrain"], eng.has(sid)):
			out[sid] = true
	return out

## 「我方最強存活非潰散單位（自己除外）」所在格；沒有回 ""。
func strongest_other_sector(p: Platoon) -> String:
	var best: Platoon = null
	for q in leaves(p.side):
		if q.id != p.id and q.is_active():
			if best == null or q.strength > best.strength:
				best = q
	return best.sector if best != null else ""

func total_strength(side: String) -> float:
	var s := 0.0
	for p in leaves(side):
		if p.state != "destroyed":
			s += p.strength
	return s

func speed_mps(p: Platoon) -> float:
	return float(rules.unit(p.unit_type)["speed"]) * SectorMap.SECTOR_SIZE / TURN_SECONDS * rules.mobility(p.unit_type, weather)

# ---- 命令（移植 sim.apply_orders；排的明確命令優先於連令）----
func order_problem(side: String, o: Order) -> String:
	if not (o.task in Order.TASKS):
		return "任務「%s」不是六種之一" % o.task
	var is_platoon: bool = platoons.has(o.unit_id) and platoons[o.unit_id].side == side
	var is_company: bool = companies.has(o.unit_id) and companies[o.unit_id]["side"] == side
	if not is_platoon and not is_company:
		return "單位 %s 不存在或已殲滅" % o.unit_id
	if is_platoon and platoons[o.unit_id].state == "destroyed":
		return "單位 %s 不存在或已殲滅" % o.unit_id
	if is_company and companies[o.unit_id]["state"] == "destroyed":
		return "單位 %s 不存在或已殲滅" % o.unit_id
	if o.task == "support":
		if o.target == o.unit_id or unit_sector(side, o.target) == "":
			return "support 目標 %s 不是存活的其他友軍" % o.target
	elif not map.sectors.has(o.target):
		return "任務 %s 的目標「%s」不是分區 id" % [o.task, o.target]
	return ""

## 套用一批命令；回傳被退回的理由清單。連令拆給子排，但同批裡有自己命令的排以自己的為準。
func apply_orders(side: String, orders: Array) -> Array[String]:
	var rejected: Array[String] = []
	var valid: Array = []
	for o in orders:
		var problem := order_problem(side, o)
		if problem == "":
			valid.append(o)
		else:
			rejected.append(problem)
			events.append("%s的命令被引擎退回：%s" % ["參謀長" if side == "us" else "敵軍", problem])
	var explicit := {}
	for o in valid:
		explicit[o.unit_id] = true
	valid.sort_custom(func(a: Order, b: Order) -> bool: return companies.has(a.unit_id) and not companies.has(b.unit_id))
	for o in valid:
		var task := {"type": o.task, "target": o.target}
		if companies.has(o.unit_id):
			var split := FormationAI.split_company_task(children_of(o.unit_id), task, o.issuer == "player")
			for cid in split.keys():
				if explicit.has(cid):
					continue
				_give_task(platoons[cid], split[cid])
			companies[o.unit_id]["task"] = task
			_log_order(side, companies[o.unit_id]["name"], o)
		else:
			_give_task(platoons[o.unit_id], task)
			_log_order(side, platoons[o.unit_id].display_name, o)
	return rejected

func _give_task(p: Platoon, task: Dictionary) -> void:
	p.task = task
	p.step_target = ""   # 重新決定路線

func _log_order(side: String, who_name: String, o: Order) -> void:
	if side == "us":
		events.append("參謀長令 %s %s %s" % [who_name, Order.TASK_ZH.get(o.task, o.task), o.target])

# ---- 推進 ----
func advance(dt: float) -> void:
	t += dt
	for p in leaves("us") + leaves("enemy"):
		_advance_platoon(p, dt)
	aggregate()

func advance_for(seconds: float, dt: float = 1.0 / 60.0) -> void:
	var n := int(round(seconds / dt))
	for i in n:
		advance(dt)

func _advance_platoon(p: Platoon, dt: float) -> void:
	if p.state == "destroyed":
		return
	p.sector = map.sector_at(p.anchor)
	if t < p.pause_until:
		p.follow_anchor(dt, speed_mps(p))
		return
	if p.step_target == "":
		var next := FormationAI.decide_move(p, self)
		if next == "":
			if p.state == "moving":
				p.state = "idle"
			p.follow_anchor(dt, speed_mps(p))
			return
		p.step_target = next
		var goal := map.center_of(next)
		p.waypoints = nav.route(p.anchor, goal) if nav != null else PackedVector3Array([goal])
		if p.waypoints.is_empty():
			p.waypoints = PackedVector3Array([goal])
		if p.state != "routed":
			p.state = "moving"
	var target := p.waypoints[0]
	target.y = 0.0
	p.anchor = p.anchor.move_toward(target, speed_mps(p) * dt)
	if p.anchor.distance_to(target) <= ARRIVE_EPS:
		p.waypoints.remove_at(0)
		if p.waypoints.is_empty():
			p.anchor = map.center_of(p.step_target)
			p.sector = p.step_target
			p.step_target = ""
			if p.state == "moving":
				p.state = "idle"   # 到了分區中心先停：到達任務目標就一直待命，還在路上下一 tick 會再出發
			if hostile_sectors(p.side).has(p.sector):
				p.pause_until = t + TURN_SECONDS   # 進到有敵軍的格子就停一回合（§2）
	p.follow_anchor(dt, speed_mps(p))

## 連級節點：戰力＝子排平均、分區＝最強存活子排、狀態由子排推（m0 sim.aggregate）。
func aggregate() -> void:
	for cid in companies.keys():
		var kids := children_of(cid)
		if kids.is_empty():
			continue
		var total := 0.0
		var alive: Array = []
		for k in kids:
			total += k.strength
			if k.state != "destroyed":
				alive.append(k)
		var c: Dictionary = companies[cid]
		c["strength"] = snappedf(total / kids.size(), 0.0001)
		if alive.is_empty():
			c["state"] = "destroyed"
		elif alive.all(func(k) -> bool: return k.state == "routed"):
			c["state"] = "routed"
		elif alive.any(func(k) -> bool: return k.state == "engaged"):
			c["state"] = "engaged"
		elif alive.any(func(k) -> bool: return k.state == "moving"):
			c["state"] = "moving"
		else:
			c["state"] = "idle"
		var best = alive[0]
		for k in alive:
			if k.strength > best.strength or (k.strength == best.strength and k.id < best.id):
				best = k
		c["sector"] = best.sector

func total_soldiers(side: String) -> int:
	var n := 0
	for p in leaves(side):
		n += p.soldiers.size()
	return n
