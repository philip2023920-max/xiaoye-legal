class_name Rules
extends RefCounted
## 規則資料表（戰鬥模型 v1，ADR-0013／0014）：直接讀 m0/rules/<era>.json，查表邏輯與 m0/chief/rules.py 一樣。
## 數字全部來自表；程式只做算式（docs/10-sim-rules.md §2、§4）。

const DEFAULT_ERA := "ww2_1944"
const UNIT_TYPES := ["infantry", "mg", "mortar", "at", "tank", "recon", "engineer"]
const TERRAINS := ["open", "hill", "forest", "town", "river"]
const WEATHERS := ["clear", "rain", "snow", "fog"]
const TIMES := ["day", "night"]

var era := ""
var display_name := ""
var K := 0.25
var cover_cap := 0.8
var budget := 100
var units := {}
var aliases := {}
var terrain := {}
var weather := {}
var time := {}
var engineer := {"hold_cover_bonus": 0.1}
var templates := {}

## 讀一個世代的規則檔；缺表就 push_error 並回 null（人話）。
static func load_era(which: String = DEFAULT_ERA) -> Rules:
	var data := BoardIO.load_json("m0://rules/%s.json" % which)
	if data.is_empty():
		push_error("找不到或讀不了世代規則檔「%s」" % which)
		return null
	var r := Rules.new()
	r.era = str(data.get("era", which))
	r.display_name = str(data.get("name", which))
	r.K = float(data.get("K", 0.25))
	r.cover_cap = float(data.get("cover_cap", 0.8))
	r.budget = int(data.get("budget", 100))
	r.units = data.get("units", {})
	r.aliases = data.get("aliases", {})
	r.terrain = data.get("terrain", {})
	r.weather = data.get("weather", {})
	r.time = data.get("time", {})
	r.engineer = data.get("engineer", {"hold_cover_bonus": 0.1})
	r.templates = data.get("templates", {})
	var problems: Array[String] = []
	for u in UNIT_TYPES:
		if not r.units.has(u):
			problems.append("兵種表缺少：%s" % u)
	for t in TERRAINS:
		if not r.terrain.has(t):
			problems.append("地形表缺少：%s" % t)
	for w in WEATHERS:
		if not r.weather.has(w):
			problems.append("天氣表缺少：%s" % w)
	for t in TIMES:
		if not r.time.has(t):
			problems.append("時段表缺少：%s" % t)
	if not problems.is_empty():
		push_error("規則檔 %s 有問題：%s" % [which, "；".join(problems)])
		return null
	return r

func resolve_type(unit_type: String) -> String:
	return str(aliases.get(unit_type, unit_type))

func has_unit(unit_type: String) -> bool:
	return units.has(resolve_type(unit_type))

func unit(unit_type: String) -> Dictionary:
	var t := resolve_type(unit_type)
	if not units.has(t):
		push_error("兵種「%s」不在 %s 規則表內" % [unit_type, era])
		return {"fire_soft": 0.0, "fire_hard": 0.0, "armor": 0.0, "speed": 1, "sight": 1, "cost": 0, "indirect": false}
	return units[t]

## 混合火力：fire_soft × (1 − 目標裝甲) + fire_hard × 目標裝甲。
func effective_fire(attacker_type: String, target_type: String) -> float:
	var a := unit(attacker_type)
	var t := unit(target_type)
	return float(a["fire_soft"]) * (1.0 - float(t["armor"])) + float(a["fire_hard"]) * float(t["armor"])

## 守方掩蔽：分區 cover（沒填用地形預設）＋天氣＋時段（＋工兵固守 0.1），上限 cover_cap。sector_cover < 0 代表沒填。
func effective_cover(terrain_name: String, wx: String, tod: String, sector_cover: float = -1.0, engineer_holding: bool = false) -> float:
	var base := sector_cover if sector_cover >= 0.0 else float(terrain[terrain_name]["cover"])
	var c := base + float(weather[wx]["cover_bonus"]) + float(time[tod]["cover_bonus"])
	if engineer_holding:
		c += float(engineer.get("hold_cover_bonus", 0.0))
	return minf(snappedf(c, 0.0001), cover_cap)

func fire_mult(wx: String, tod: String) -> float:
	return snappedf(float(weather[wx]["fire_mult"]) * float(time[tod]["fire_mult"]), 0.0001)

func sight(unit_type: String, wx: String, tod: String) -> int:
	return maxi(0, int(unit(unit_type)["sight"]) + int(weather[wx]["sight"]) + int(time[tod]["sight"]))

## 機動力：天氣的 all_mobility；裝甲 ≥ 0.5 的兵種再取 armor_mobility 的最小值。
func mobility(unit_type: String, wx: String) -> float:
	var w: Dictionary = weather[wx]
	var m := float(w["all_mobility"])
	if float(unit(unit_type)["armor"]) >= 0.5:
		m = minf(m, float(w["armor_mobility"]))
	return m

func can_enter(unit_type: String, terrain_name: String, engineer_present: bool = false) -> bool:
	var t: Dictionary = terrain[terrain_name]
	if float(unit(unit_type)["armor"]) >= 0.5 and not bool(t["armor_passable"]):
		return bool(t.get("engineer_bridges", false)) and engineer_present
	return true

func template_cost(template_name: String) -> int:
	var total := 0
	for u in templates[template_name]["units"]:
		total += int(unit(u)["cost"])
	return total
