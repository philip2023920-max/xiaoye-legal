class_name Orbat
extends Node3D
## 雙方部隊樹（排是葉節點、連是容器），以及每個物理 tick 的移動推進。
##
## 時間對應（ADR-0014 D19，docs/10 §15）：M0 一回合＝30 秒；速度 = speed × 20 m ÷ 30 s × 機動力（機動力 0.5 ＝ 60 秒一格，
## 是 M0「只在偶數回合動」的連續版）；潰散單位不論兵種以 speed 1 退（§2「只退 1 格」）。
## 分區歸屬看錨點的實際位置（跨過格線就算進了下一格）；走到分區裡自己的站位（距 ARRIVE_EPS 內吸附）才算「到達」，
## 到達有敵軍的分區會停 TURN_SECONDS 再繼續（M0「進敵格就停、下回合再動」的連續版）。

const TURN_SECONDS := 30.0
const ARRIVE_EPS := 0.5
## 一個分區裡最多 9 個排的站位（相對分區中心；城鎮的方塊在 x∈{−6,0,6}、z∈{−3.5,3.5}，這九點都落在空地）。
const SLOT_OFFSETS: Array[Vector3] = [
	Vector3(0, 0, 0), Vector3(-7, 0, -7), Vector3(7, 0, -7), Vector3(-7, 0, 7), Vector3(7, 0, 7),
	Vector3(0, 0, -7), Vector3(-7, 0, 0), Vector3(7, 0, 0), Vector3(0, 0, 7),
]

var map: SectorMap
var rules: Rules
var grid: SectorGrid
var nav: RTSNavGrid = null          # 有就繞掩體；沒有就直線走到站位
var weather := "clear"
var time_of_day := "day"
var t := 0.0                        # 遊戲秒
var platoons := {}                  # id -> Platoon（雙方）
var companies := {}                 # id -> Dictionary（雙方；見 _company_dict）
var events: Array[Dictionary] = []  # {t, kind, text, unit, sector}，與 M0 Event 同欄位（施工單 13 寫進戰情板）
var resolver: Resolver = null        # 戰鬥解算（施工單 12）
var overrides_this_battle := 0
var second_hooks: Array[Callable] = []   # 每跨過一個整數秒呼叫（戰情板的歸屬與敵情，施工單 13）
var _last_hook_second := 0
var _next_index := 0                # 戰情板順序（連令拆排、主力判定都照它，與 M0 的 units 原序一致）
var _cache := {}                    # 每 tick 一次：leaves / hostile / engineers（施工單 15 效能）

func setup(map_: SectorMap, rules_: Rules) -> void:
	map = map_
	rules = rules_
	grid = SectorGrid.new(map.cols, map.rows)
	resolver = Resolver.new(self)

## 目前的整數秒（浮點累加 119.9999 也算 120）。事件、戰情板、工具都用它。
func second() -> int:
	return int(floor(t + 1e-4))

func log_event(at: int, kind: String, text: String, unit: String = "", sector: String = "") -> void:
	var e := {"t": at, "kind": kind, "text": text}
	if unit != "":
		e["unit"] = unit
	if sector != "":
		e["sector"] = sector
	events.append(e)

## 天氣／時段變化（劇本在指定秒數呼叫）：寫 weather 事件。
func set_conditions(wx: String, tod: String) -> void:
	if wx != "" and wx != weather:
		if not rules.weather.has(wx):
			push_error("天氣「%s」不在 %s 規則表內" % [wx, rules.era])
		else:
			weather = wx
			log_event(second(), "weather", "天氣轉%s" % {"clear": "晴", "rain": "雨", "snow": "雪", "fog": "霧"}.get(wx, wx))
	if tod != "" and tod != time_of_day:
		if not rules.time.has(tod):
			push_error("時段「%s」不在 %s 規則表內" % [tod, rules.era])
		else:
			time_of_day = tod
			log_event(second(), "weather", "進入%s" % {"day": "日間", "night": "夜間"}.get(tod, tod))
	for pid in platoons.keys():   # 骨架迷霧的視距跟著天氣時段變
		var p: Platoon = platoons[pid]
		p.vision_radius = rules.sight(p.unit_type, weather, time_of_day) * SectorMap.SECTOR_SIZE

## 從戰情板的 orbat（我方）與敵方劇本的 units（敵方）生成；同格的排各占一個站位。葉節點兵種不合法就拒建並回 false。
func build(board: Dictionary, enemy_units: Array = []) -> bool:
	weather = str(board.get("weather", "clear"))
	time_of_day = str(board.get("time_of_day", "day"))
	var ok := _build_side("us", board.get("orbat", []))
	ok = _build_side("enemy", enemy_units) and ok
	_refresh_cache()
	aggregate()
	return ok

func _build_side(side: String, units: Array) -> bool:
	var ok := true
	var used := {}   # 分區 -> 已用站位數
	for u in units:
		if str(u.get("echelon", "platoon")) != "platoon":
			companies[str(u["id"])] = _company_dict(u, side)
			continue
		var utype := str(u.get("type", "infantry"))
		if utype == "armor":
			utype = "tank"
		if not rules.has_unit(utype):
			push_error("%s單位 %s 的兵種「%s」不在 %s 規則表內（mixed 只能用在有子排的連）" % ["我方" if side == "us" else "敵方", u.get("id", "?"), utype, rules.era])
			ok = false
			continue
		var sid := str(u["sector"])
		var k: int = used.get(sid, 0)
		used[sid] = k + 1
		add_platoon(u, side, map.center_of(sid) + SLOT_OFFSETS[k % SLOT_OFFSETS.size()])
	return ok

func add_platoon(data: Dictionary, side: String, at: Vector3) -> Platoon:
	var p := Platoon.new()
	p.setup(data, side, at)
	p.orbat_index = _next_index
	_next_index += 1
	p.sector = map.sector_at(at)
	p.vision_radius = rules.sight(p.unit_type, weather, time_of_day) * SectorMap.SECTOR_SIZE
	add_child(p)
	platoons[p.id] = p
	_cache = {}
	return p

## 把排放到某點（開局部署、測試、施工單 12 的潰散傳送都用它）：同時更新分區、清掉路線與暫停。
func place_platoon(p: Platoon, at: Vector3) -> void:
	p.place(at)
	p.sector = map.sector_at(at)
	p.pause_until = -1.0
	_cache = {}

func _company_dict(u: Dictionary, side: String) -> Dictionary:
	return {"id": str(u["id"]), "name": str(u.get("name", u["id"])), "echelon": str(u.get("echelon", "company")), "side": side,
		"parent": u.get("parent"), "strength": float(u.get("strength", 1.0)), "state": str(u.get("state", "idle")),
		"sector": str(u.get("sector", "")), "task": {}, "controlled_by": str(u.get("controlled_by", "ai")), "cost": int(u.get("cost", 0)), "type": "mixed"}

# ---- 查詢（戰情板順序）----
func leaves(side: String) -> Array[Platoon]:
	if _cache.has("leaves_" + side):
		return _cache["leaves_" + side]
	var out: Array[Platoon] = []
	for pid in platoons.keys():
		var p: Platoon = platoons[pid]
		if p.side == side:
			out.append(p)
	out.sort_custom(func(a: Platoon, b: Platoon) -> bool: return a.orbat_index < b.orbat_index)
	return out

func _refresh_cache() -> void:
	_cache = {}
	for side in ["us", "enemy"]:
		_cache["leaves_" + side] = leaves(side)
	for side in ["us", "enemy"]:
		_cache["hostile_" + side] = hostile_sectors(side)
		_cache["eng_" + side] = engineer_sectors(side)

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
	if _cache.has("hostile_" + side):
		return _cache["hostile_" + side].duplicate()
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
	if _cache.has("eng_" + side):
		return _cache["eng_" + side]
	var out := {}
	for p in leaves(side):
		if rules.resolve_type(p.unit_type) == "engineer" and p.state != "routed" and p.state != "destroyed":
			out[p.sector] = true
	return out

## 這個排進不去的分區（戰車 vs 森林／河川；河川有本方工兵在那格就能過，以本 tick 開始時的工兵位置為準）。
func blocked_sectors(p: Platoon) -> Dictionary:
	var out := {}
	if float(rules.unit(p.unit_type)["armor"]) < 0.5:
		return out   # 非裝甲：所有地形可通行，省 25 次查表
	var eng := engineer_sectors(p.side)
	for sid in map.sectors.keys():
		if not rules.can_enter(p.unit_type, map.sectors[sid]["terrain"], eng.has(sid)):
			out[sid] = true
	return out

## 「我方最強存活非潰散單位（自己除外）」所在格（同強取戰情板順序第一個，與 M0 的 max 相同）；沒有回 ""。
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

## 公尺／秒：speed 格 × 20 m ÷ 30 s × 機動力；潰散單位 speed 當 1（§2）。
func speed_mps(p: Platoon) -> float:
	var steps := 1 if p.state == "routed" else int(rules.unit(p.unit_type)["speed"])
	return steps * SectorMap.SECTOR_SIZE / TURN_SECONDS * rules.mobility(p.unit_type, weather)

func platoons_in(side: String, sector_id: String) -> Array[Platoon]:
	var out: Array[Platoon] = []
	for p in leaves(side):
		if p.sector == sector_id and p.state != "destroyed":
			out.append(p)
	return out

## 進到 sector 時要站哪：九個站位裡第一個沒被本方其他排占住的（占住＝錨點離站位 < 1 m）。
func free_slot(p: Platoon, sector_id: String) -> Vector3:
	var center := map.center_of(sector_id)
	for off in SLOT_OFFSETS:
		var slot := center + off
		var taken := false
		for q in platoons_in(p.side, sector_id):
			if q.id != p.id and q.anchor.distance_to(slot) < 1.0:
				taken = true
				break
		if not taken:
			return slot
	return center

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
	if is_platoon and platoons[o.unit_id].state == "routed" and o.task != "withdraw":
		return "單位 %s 潰散中，只能撤退" % o.unit_id     # V6（與 M0 player_order_problem／驗證器一致）
	if is_company and companies[o.unit_id]["state"] == "destroyed":
		return "單位 %s 不存在或已殲滅" % o.unit_id
	if o.task == "support":
		if o.target == o.unit_id or unit_sector(side, o.target) == "":
			return "support 目標 %s 不是存活的其他友軍" % o.target
	elif not map.sectors.has(o.target):
		return "任務 %s 的目標「%s」不是分區 id" % [o.task, o.target]
	return ""

## 套用一批命令；回傳被退回的理由清單。先處理連令（拆給子排）再處理排令，所以同批裡有自己命令的排以自己的為準；
## 同一單位兩道令後者為準（與 M0 穩定排序相同）。
func apply_orders(side: String, orders: Array) -> Array[String]:
	var rejected: Array[String] = []
	var valid: Array = []
	for o in orders:
		var problem := order_problem(side, o)
		if problem == "":
			valid.append(o)
		else:
			rejected.append(problem)
			log_event(second(), "info", "%s的命令被引擎退回：%s" % ["參謀長" if side == "us" else "敵軍", problem])
	var explicit := {}
	for o in valid:
		explicit[o.unit_id] = true
	for pass_companies in [true, false]:
		for o in valid:
			if companies.has(o.unit_id) != pass_companies:
				continue
			var task := {"type": o.task, "target": o.target}
			if pass_companies:
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
	p.step_target = ""   # 就地重新決定路線（下一步從目前所在分區算）

func _log_order(side: String, who_name: String, o: Order) -> void:
	if side == "us":
		log_event(second(), "order", "參謀長令 %s %s %s" % [who_name, Order.TASK_ZH.get(o.task, o.task), o.target], o.unit_id, o.target if map.sectors.has(o.target) else "")

# ---- 推進 ----
func advance(dt: float) -> void:
	t += dt
	_refresh_cache()
	for p in leaves("us") + leaves("enemy"):
		_advance_platoon(p, dt)
	if resolver != null:
		resolver.step(t)
	var sec := second()
	while _last_hook_second < sec:
		_last_hook_second += 1
		for hook in second_hooks:
			if hook.is_valid():
				hook.call(_last_hook_second)
	if resolver != null:
		for p in leaves("us") + leaves("enemy"):
			p.fighting = resolver.fighting.has(p.id)
			if p.state == "engaged" and not p.fighting:
				p.state = "moving" if p.step_target != "" else "idle"
			elif p.fighting and p.state != "routed" and p.state != "destroyed":
				p.state = "engaged"
	aggregate()

func advance_for(seconds: float, dt: float = 1.0 / 60.0) -> void:
	var n := int(round(seconds / dt))
	for i in n:
		advance(dt)

func _arrived_at_task(p: Platoon) -> bool:
	return not p.task.is_empty() and p.task["type"] != "support" and p.sector == p.task["target"]

func _advance_platoon(p: Platoon, dt: float) -> void:
	if p.state == "destroyed":
		return
	p.sector = map.sector_at(p.anchor)
	var speed := speed_mps(p)
	var was_engaged := p.state == "engaged"
	if t < p.pause_until:
		p.follow_anchor(dt, speed)
		return
	if p.step_target == "":
		var next := FormationAI.decide_move(p, self)
		if next != "" and blocked_sectors(p).has(next):
			next = ""   # 任何分支算出的下一格都不准是進不去的（M0 sim.py 的 dest in avoid 守門）
		if next == "":
			if p.state == "moving":
				p.state = "idle"
			p.follow_anchor(dt, speed)
			return
		p.step_target = next
		if was_engaged:
			p.state = "engaged"
		var goal := free_slot(p, next)
		p.waypoints = nav.route(p.anchor, goal) if nav != null else PackedVector3Array([goal])
		if p.waypoints.is_empty():
			p.waypoints = PackedVector3Array([goal])
		p.waypoints[p.waypoints.size() - 1] = goal   # 路線終點一律是站位（尋路格的終點可能是最近的開放格）
		if p.state != "routed" and p.state != "engaged":
			p.state = "moving"
	var target := p.waypoints[0]
	target.y = 0.0
	p.anchor = p.anchor.move_toward(target, speed * dt)
	if p.anchor.distance_to(target) <= ARRIVE_EPS:
		p.waypoints.remove_at(0)
		if p.waypoints.is_empty():
			p.anchor = target
			p.sector = p.step_target
			p.step_target = ""
			if p.state == "moving" and _arrived_at_task(p):
				p.state = "idle"   # 到達任務目標才待命；中途經過的分區仍是 moving（§5）
			if hostile_sectors(p.side).has(p.sector):
				p.pause_until = t + TURN_SECONDS   # 到達有敵軍的格子就停一回合（§2）
	p.follow_anchor(dt, speed)

## 連級節點：戰力＝子排平均、分區＝最強存活子排（同強取 id 字串序最大者，與 M0 的 max 相同）、狀態由子排推（§8b）。
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
			continue
		if alive.all(func(k) -> bool: return k.state == "routed"):
			c["state"] = "routed"
		elif alive.any(func(k) -> bool: return k.state == "engaged"):
			c["state"] = "engaged"
		elif alive.any(func(k) -> bool: return k.state == "moving"):
			c["state"] = "moving"
		else:
			c["state"] = "idle"
		var best = alive[0]
		for k in alive:
			if k.strength > best.strength or (k.strength == best.strength and k.id > best.id):
				best = k
		c["sector"] = best.sector

func total_soldiers(side: String) -> int:
	var n := 0
	for p in leaves(side):
		n += p.soldiers.size()
	return n
