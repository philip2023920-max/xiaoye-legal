class_name BoardWriter
extends RefCounted
## 戰情板寫入（施工單 13，ADR-0014 D18）：每秒做 §6 歸屬與 §2 視距／敵情，組成 Board v0.2 JSON，
## 原子寫入（先寫 .tmp 再改名）。M0 的 Python（chief show／replay／戰報卡）讀同一份。

const SCHEMA_VERSION := "0.2"

var orbat: Orbat
var battle_id := ""
var era := ""
var contacts := {}              # 敵方 id -> Contact 字典（只記看過的）
var visible: Array[String] = []
var last_update_second := -1
var writes := 0
var _warned := false

func _init(orbat_: Orbat, battle_id_: String, era_: String) -> void:
	orbat = orbat_
	battle_id = battle_id_
	era = era_

## 每跨過一個整數秒呼叫一次（Orbat 的 second hook）。
func update(sec: int) -> void:
	if sec <= last_update_second:
		return
	last_update_second = sec
	_ownership(sec)
	_intelligence(sec)

## §6：分區內只有一方有非潰散單位 → 該方擁有；兩方都有 → 原擁有者不變、contested；沒人 → 不變。
func _ownership(sec: int) -> void:
	var map := orbat.map
	for sid in map.sectors.keys():
		var us_here := false
		var en_here := false
		for p in orbat.leaves("us"):
			if p.sector == sid and p.is_active():
				us_here = true
				break
		for p in orbat.leaves("enemy"):
			if p.sector == sid and p.is_active():
				en_here = true
				break
		var s: Dictionary = map.sectors[sid]
		var before: String = s["owner"]
		var owner := before
		var contested := false
		if us_here and en_here:
			contested = true
		elif us_here:
			owner = "us"
		elif en_here:
			owner = "enemy"
		if owner != before or contested != bool(s["contested"]):
			map.set_sector_owner(sid, owner, contested)
		var obj_id = s["objective"]
		if obj_id != null and map.objectives.has(obj_id):
			map.objectives[obj_id]["owner"] = map.sectors[sid]["owner"]   # 目標 owner 無條件跟著分區（M0 每回合同步）
		if owner != before:
			var obj = s["objective"]
			orbat.log_event(sec, "seized", "%s取得 %s%s" % ["我方" if owner == "us" else "敵方", sid, ("（目標 %s）" % obj) if obj != null else ""], "", sid)

## §2 視距：每個未殲滅友軍排看得見曼哈頓距離 ≤ sight 的分區；0＝只看自己那格。
func visible_sectors() -> Array[String]:
	var seen := {}
	for p in orbat.leaves("us"):
		if p.state == "destroyed":
			continue
		var sight := orbat.rules.sight(p.unit_type, orbat.weather, orbat.time_of_day)
		for sid in orbat.map.sectors.keys():
			if SectorGrid.distance(p.sector, sid) <= sight:
				seen[sid] = true
	var out: Array[String] = []
	out.assign(seen.keys())
	out.sort()
	return out

func _intelligence(sec: int) -> void:
	visible = visible_sectors()
	var vis := {}
	for sid in visible:
		vis[sid] = true
	for e in orbat.leaves("enemy"):
		if e.state == "destroyed":
			if vis.has(e.sector) and contacts.has(e.id):
				contacts.erase(e.id)   # 親眼看到被殲滅，從敵情拿掉
			continue
		if not vis.has(e.sector):
			continue
		var is_new := not contacts.has(e.id)
		contacts[e.id] = {"id": e.id, "echelon": "platoon", "type": e.unit_type, "sector": e.sector,
			"strength_est": snappedf(e.strength, 0.01), "last_seen": sec, "confidence": 0.9}
		if is_new:
			orbat.log_event(sec, "contact", "在 %s 發現敵 %s" % [e.sector, e.display_name], e.id, e.sector)

static func phase_of(t_seconds: float) -> String:
	if t_seconds <= 90.0:
		return "early"
	return "mid" if t_seconds <= 210.0 else "late"

## Board v0.2（docs/09）。enemy_known 只放看過的敵情，不是敵方真實狀態。
func to_dict() -> Dictionary:
	var map := orbat.map
	var sectors := {}
	for sid in map.sectors.keys():
		var s: Dictionary = map.sectors[sid]
		var d := {"id": sid, "terrain": s["terrain"], "owner": s["owner"], "contested": bool(s["contested"])}
		if s["cover"] != null:
			d["cover"] = float(s["cover"])
		if s["objective"] != null:
			d["objective"] = s["objective"]
		sectors[sid] = d
	var orbat_list: Array = []
	for cid in orbat.companies.keys():
		var c: Dictionary = orbat.companies[cid]
		if c["side"] != "us":
			continue
		orbat_list.append({"id": c["id"], "name": c["name"], "echelon": c["echelon"], "type": "mixed", "parent": c["parent"],
			"strength": snappedf(float(c["strength"]), 0.01), "state": c["state"], "sector": c["sector"],
			"task": (c["task"].duplicate() if not c["task"].is_empty() else null), "controlled_by": c["controlled_by"], "cost": c["cost"]})
	for p in orbat.leaves("us"):
		var d := p.to_dict()
		d["strength"] = snappedf(p.strength, 0.01)
		orbat_list.append(d)
	var objectives: Array = []
	for oid in map.objectives.keys():
		var o: Dictionary = map.objectives[oid]
		objectives.append({"id": oid, "sector": o["sector"], "value": o["value"], "owner": o["owner"]})
	var known: Array = []
	var cids := contacts.keys()
	cids.sort()
	for cid in cids:
		known.append(contacts[cid])
	return {
		"schema_version": SCHEMA_VERSION, "battle_id": battle_id, "t": orbat.second(), "time_unit": "second",
		"phase": phase_of(orbat.t), "scale": "battle", "era": era, "weather": orbat.weather, "time_of_day": orbat.time_of_day,
		"map": {"cols": map.cols, "rows": map.rows, "sectors": sectors},
		"orbat": orbat_list, "enemy_known": known, "objectives": objectives, "events": orbat.events.duplicate(true),
		"fog": {"visible_sectors": visible}, "overrides_this_battle": orbat.overrides_this_battle,
	}

## 寫入：先寫 path.tmp 再改名蓋過去。讀端永遠不會讀到半截；但 Windows 的改名是「先刪再搬」（Godot 的 DirAccess 實作），
## 可能短暫無檔，所以 M0 讀端遇到「找不到／JSON 不完整」要重試幾次（chief show 已做）。
func write(path: String) -> bool:
	var real := ProjectSettings.globalize_path(path)
	var dir := real.get_base_dir()
	if not DirAccess.dir_exists_absolute(dir):
		DirAccess.make_dir_recursive_absolute(dir)
	var tmp := real + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		push_error("寫不了戰情板暫存檔：%s（%s）" % [tmp, error_string(FileAccess.get_open_error())])
		return false
	f.store_string(JSON.stringify(to_dict(), "", false))
	f.close()
	var err := DirAccess.rename_absolute(tmp, real)
	if err != OK:
		# 最後保險：直接寫（非原子）。只警告一次，避免 log 被洗版。
		if not _warned:
			_warned = true
			push_warning("戰情板改名失敗（%s），改為直接寫入 %s（非原子）" % [error_string(err), real])
		var f2 := FileAccess.open(real, FileAccess.WRITE)
		if f2 == null:
			push_error("戰情板寫入失敗：%s（%s）" % [real, error_string(FileAccess.get_open_error())])
			return false
		f2.store_string(FileAccess.get_file_as_string(tmp))
		f2.close()
		DirAccess.remove_absolute(tmp)
	writes += 1
	return true
