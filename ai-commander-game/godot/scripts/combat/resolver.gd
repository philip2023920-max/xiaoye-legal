class_name Resolver
extends RefCounted
## 戰鬥解算（施工單 12）：docs/10 §4 v1 的查表公式，連續時間版（§15）。
##
## 回合＝30 秒。每個回合開始時把所有單位的戰力拍一張「回合快照」，接下來 30 秒每秒套用
## 「M0 一回合的傷害 ÷ 30」（用快照戰力算攻擊與分攤），所以 30 秒合計與 M0 手算例一致，
## 而人是一個一個倒。中途加入交戰的單位以加入當下的戰力當快照。
## 狀態門檻（§5）：戰力 < 0.30 潰散、≤ 0.05 殲滅，潰散／殲滅時任務清空；每秒結算後判定。

const TURN_SECONDS := 30.0
const ROUT_THRESHOLD := 0.30
const DESTROY_THRESHOLD := 0.05

var orbat: Orbat
var snapshot := {}            # id -> 回合快照戰力
var round_index := -1
var last_second := 0
var fighting := {}            # id -> true（這一秒有交戰的單位，Orbat 用來推 engaged）
var damage_last_second := {}  # id -> 這一秒受的傷（測試與特效用）
var tracers: Array = []       # [{from: Vector3, to: Vector3}]（這一秒的射線，給畫面）

func _init(orbat_: Orbat) -> void:
	orbat = orbat_

## 由 Orbat.advance 每 tick 呼叫；每跨過一個整數秒就結算一次。
func step(t: float) -> void:
	var sec := int(floor(t + 1e-4))
	while last_second < sec:
		last_second += 1
		_resolve_second(last_second)

func _fires(p: Platoon) -> bool:
	return p.state != "routed" and p.state != "destroyed" and p.task.get("type", "") != "withdraw"

func _snap(p: Platoon) -> float:
	if not snapshot.has(p.id):
		snapshot[p.id] = p.strength   # 中途加入：以加入當下為準
	return snapshot[p.id]

func _resolve_second(sec: int) -> void:
	var r := int((sec - 1) / TURN_SECONDS)
	if r != round_index:
		round_index = r
		snapshot.clear()
		for pid in orbat.platoons.keys():
			snapshot[pid] = orbat.platoons[pid].strength
	fighting.clear()
	damage_last_second.clear()
	tracers.clear()
	var map := orbat.map
	var rules := orbat.rules
	var fire_mult := rules.fire_mult(orbat.weather, orbat.time_of_day)
	var damages := {}
	var sectors := {}
	for pid in orbat.platoons.keys():
		var p: Platoon = orbat.platoons[pid]
		if p.state != "destroyed":
			sectors[p.sector] = true
	var keys := sectors.keys()
	keys.sort()
	for sid in keys:
		var us_all := _in_sector("us", sid)
		var en_all := _in_sector("enemy", sid)
		var us_active := us_all.filter(func(p: Platoon) -> bool: return p.state != "routed")
		var en_active := en_all.filter(func(p: Platoon) -> bool: return p.state != "routed")
		if us_active.is_empty() or en_active.is_empty():
			continue   # 要有雙方「能戰鬥」的單位才交火；潰散單位只會被打
		var adj := orbat.grid.neighbors(sid)
		var sup_us := _indirect_support("us", adj)
		var sup_en := _indirect_support("enemy", adj)
		_damage_to(en_all, us_all + sup_us, _cover_for("enemy", sid), fire_mult, damages)
		_damage_to(us_all, en_all + sup_en, _cover_for("us", sid), fire_mult, damages)
		for p in us_active + en_active:
			fighting[p.id] = true
		_add_tracers(us_active + sup_us, en_active)
		_add_tracers(en_active + sup_en, us_active)
	for pid in damages.keys():
		var p: Platoon = orbat.platoons[pid]
		var d: float = damages[pid]
		p.strength = maxf(0.0, p.strength - d)
		damage_last_second[pid] = d
		p.sync_men()
	_transitions(sec)

func _in_sector(side: String, sid: String) -> Array:
	var out: Array = []
	for p in orbat.leaves(side):
		if p.sector == sid and p.state != "destroyed":
			out.append(p)
	return out

## 鄰格的迫砲（間接射擊）：非潰散、非撤退，才加入攻方；只打不被打。
func _indirect_support(side: String, adjacent: Array[String]) -> Array:
	var out: Array = []
	for p in orbat.leaves(side):
		if p.sector in adjacent and bool(orbat.rules.unit(p.unit_type)["indirect"]) and _fires(p):
			out.append(p)
	return out

func _cover_for(side: String, sid: String) -> float:
	var s: Dictionary = orbat.map.sectors[sid]
	var holding := false
	for p in orbat.leaves(side):
		if p.sector == sid and orbat.rules.resolve_type(p.unit_type) == "engineer" and p.state != "routed" and p.state != "destroyed" \
				and p.task.get("type", "") == "hold" and p.task.get("target", "") == sid:
			holding = true
	var sector_cover := float(s["cover"]) if s["cover"] != null else -1.0
	return orbat.rules.effective_cover(s["terrain"], orbat.weather, orbat.time_of_day, sector_cover, holding)

## 對每個目標 t：Σ_攻方 snap(a) × 混合火力 × share(t) × (1 − 掩蔽) × K × 倍率 ÷ 30（§4，每秒 1/30）。
func _damage_to(targets: Array, attackers: Array, cover: float, fire_mult: float, out: Dictionary) -> void:
	var shooters := attackers.filter(func(a: Platoon) -> bool: return _fires(a))
	var alive := targets.filter(func(p: Platoon) -> bool: return p.state != "destroyed")
	var pool := 0.0
	for tgt in alive:
		pool += _snap(tgt)
	if pool <= 0.0 or shooters.is_empty():
		return
	for tgt in alive:
		var share := _snap(tgt) / pool
		var total := 0.0
		for a in shooters:
			total += _snap(a) * orbat.rules.effective_fire(a.unit_type, tgt.unit_type)
		var dmg := total * share * (1.0 - cover) * orbat.rules.K * fire_mult / TURN_SECONDS
		if dmg > 0.0:
			out[tgt.id] = out.get(tgt.id, 0.0) + dmg

func _add_tracers(shooters: Array, targets: Array) -> void:
	if targets.is_empty():
		return
	var i := 0
	for a in shooters:
		if not _fires(a) or a.soldiers.is_empty():
			continue
		var tgt: Platoon = targets[i % targets.size()]
		i += 1
		var shooter: Platoon = a
		var from_man: Soldier = shooter.soldiers[(last_second * 7 + i) % shooter.soldiers.size()]
		var to_man: Soldier = tgt.soldiers[(last_second * 5 + i) % tgt.soldiers.size()]
		tracers.append({"from": from_man.global_position + Vector3(0, 1.2, 0), "to": to_man.global_position + Vector3(0, 1.0, 0)})

func _transitions(sec: int) -> void:
	for side in ["us", "enemy"]:
		var who := "我方" if side == "us" else "敵方"
		for p in orbat.leaves(side):
			if p.state == "destroyed":
				continue
			if p.strength <= DESTROY_THRESHOLD:
				p.state = "destroyed"
				p.task = {}
				p.step_target = ""
				orbat.log_event(sec, "destroyed", "%s %s 在 %s 被殲滅" % [who, p.display_name, p.sector], p.id, p.sector)
			elif p.strength < ROUT_THRESHOLD and p.state != "routed":
				p.state = "routed"
				p.task = {}
				p.step_target = ""
				orbat.log_event(sec, "routed", "%s %s 在 %s 潰散" % [who, p.display_name, p.sector], p.id, p.sector)
