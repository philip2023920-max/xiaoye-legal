class_name Platoon
extends Node3D
## 一個排＝三班＝九個方塊人；是會戰規模的最小行動單位，也是 Board v0.2 orbat 的葉節點。
## 狀態、任務、戰力欄位與 m0 的 Unit 一致；移動由 Orbat.advance 驅動（這裡只管站位與外觀）。

const MEN_PER_SQUAD := 3
const SQUADS := 3
const SQUAD_SPACING := 4.0
const MAN_SPACING := 1.3

var id := ""
var display_name := ""
var unit_type := "infantry"
var side := "us"
var team := 0                      # 骨架契約：0 我方、1 敵方
var parent_id := ""
var strength := 1.0
var state := "idle"                # idle / moving / engaged / routed / destroyed
var task := {}                     # {} 或 {"type": ..., "target": ...}
var controlled_by := "ai"
var cost := 0
var orbat_index := 0               # 戰情板順序（與 M0 的 units 原序一致；連令拆排、主力判定照它）
var vision_radius := 0.0           # 骨架迷霧用（公尺）
var sector := ""                   # 目前所在分區（由錨點算）
var anchor := Vector3.ZERO         # 排的中心點，Orbat 帶著它走
var step_target := ""              # 正在走向的分區；"" 表示要重新決定
var waypoints := PackedVector3Array()
var pause_until := -1.0            # 進到有敵軍的格子後停一回合（秒）
var fighting := false              # 這一秒有交戰（Resolver 設、Orbat 推狀態用）
var soldiers: Array[Soldier] = []
var selected := false              # 施工單 19：被總司令點選
var ring: MeshInstance3D = null    # 排腳下的環：直轄金色、選取白色、兩者都是亮金；參謀長指揮且沒選＝隱藏
const RING_COLORS := {"player": Color(1.0, 0.75, 0.2), "selected": Color(1.0, 1.0, 1.0), "both": Color(1.0, 0.9, 0.4)}
static var _ring_mesh: TorusMesh = null
static var _ring_materials := {}

func setup(data: Dictionary, side_: String, at: Vector3) -> void:
	id = str(data["id"])
	name = id
	display_name = str(data.get("name", id))
	unit_type = str(data.get("type", "infantry"))
	if unit_type == "armor":
		unit_type = "tank"
	side = side_
	team = 0 if side == "us" else 1
	parent_id = str(data.get("parent", "")) if data.get("parent") != null else ""
	strength = float(data.get("strength", 1.0))
	state = str(data.get("state", "idle"))
	controlled_by = str(data.get("controlled_by", "ai"))
	cost = int(data.get("cost", 0))
	var t = data.get("task")
	task = {"type": str(t["type"]), "target": str(t["target"])} if t is Dictionary else {}
	anchor = at
	position = Vector3.ZERO
	add_to_group(RTSKit.UNIT_GROUP)
	add_to_group("platoons")
	_spawn_men()
	_spawn_ring()
	var dead := MEN_PER_SQUAD * SQUADS - clampi(roundi(strength * MEN_PER_SQUAD * SQUADS), 0, MEN_PER_SQUAD * SQUADS)   # 與 sync_men 同一公式
	for i in dead:
		soldiers[soldiers.size() - 1 - i].fall()
	recompute_strength()   # 戰力一律＝存活人數 ÷ 9（樣板 0.8 → 倒 2 人 → 0.78）

func _spawn_men() -> void:
	var squad_slots := RTSKit.formation(anchor, SQUADS, SQUAD_SPACING)
	for s in SQUADS:
		var man_slots := RTSKit.formation(squad_slots[s], MEN_PER_SQUAD, MAN_SPACING)
		for m in MEN_PER_SQUAD:
			var man := Soldier.new()
			man.name = "S%dM%d" % [s + 1, m + 1]
			man.setup(unit_type, side, man_slots[m])
			add_child(man)
			soldiers.append(man)

func _spawn_ring() -> void:
	if _ring_mesh == null:
		_ring_mesh = TorusMesh.new()
		_ring_mesh.inner_radius = 3.2
		_ring_mesh.outer_radius = 3.7
		_ring_mesh.rings = 24
		_ring_mesh.ring_segments = 6
	ring = MeshInstance3D.new()
	ring.name = "Ring"
	ring.mesh = _ring_mesh
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ring.position = anchor + Vector3(0.0, 0.08, 0.0)
	ring.scale = Vector3(1.0, 0.25, 1.0)
	add_child(ring)
	update_ring()

## 骨架 RTSSelection 的鉤子（施工單 19 也直接呼叫）。
func rts_set_selected(on: bool) -> void:
	selected = on
	update_ring()

## 環的顏色依直轄與選取決定；參謀長指揮且沒被選＝不顯示（畫面乾淨）。
func update_ring() -> void:
	if ring == null:
		return
	var player := controlled_by == "player"
	ring.visible = player or selected
	if not ring.visible:
		return
	var key := "both" if (player and selected) else ("player" if player else "selected")
	if not _ring_materials.has(key):
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.albedo_color = RING_COLORS[key]
		_ring_materials[key] = m
	ring.material_override = _ring_materials[key]

func ring_color() -> Color:
	return ring.material_override.albedo_color if (ring != null and ring.visible and ring.material_override != null) else Color(0, 0, 0, 0)

func alive_count() -> int:
	var n := 0
	for s in soldiers:
		if s.alive:
			n += 1
	return n

## 戰力是連續血量（與 M0 strength 同義，0～1）；畫面上倒下的人數＝round((1 − 戰力) × 9)。
func recompute_strength() -> void:
	strength = snappedf(float(alive_count()) / float(MEN_PER_SQUAD * SQUADS), 0.01)

## 讓倒下的人數追上血量（解算後呼叫）。
func sync_men() -> void:
	var should_alive := clampi(roundi(strength * MEN_PER_SQUAD * SQUADS), 0, MEN_PER_SQUAD * SQUADS)
	var n := alive_count() - should_alive
	for s in soldiers:
		if n <= 0:
			break
		if s.alive:
			s.fall()
			n -= 1

## 殺掉 n 人（施工單 12 的解算會用；測試也用）。
func kill(n: int) -> void:
	for s in soldiers:
		if n <= 0:
			break
		if s.alive:
			s.fall()
			n -= 1
	recompute_strength()

func is_active() -> bool:
	return state != "destroyed" and state != "routed"

func rts_is_alive() -> bool:
	return state != "destroyed"

## 把整個排瞬間放到某點（請經由 Orbat.place_platoon，它會同步分區與清暫停）。
func place(at: Vector3) -> void:
	anchor = at
	step_target = ""
	if ring != null:
		ring.position = anchor + Vector3(0.0, 0.08, 0.0)
	waypoints = PackedVector3Array()
	pause_until = -1.0
	var squad_slots := RTSKit.formation(anchor, SQUADS, SQUAD_SPACING)
	for s in SQUADS:
		var man_slots := RTSKit.formation(squad_slots[s], MEN_PER_SQUAD, MAN_SPACING)
		for m in MEN_PER_SQUAD:
			var man := soldiers[s * MEN_PER_SQUAD + m]
			man.position = man_slots[m]
			man.target_point = man_slots[m]

## 更新每個人的站位（錨點動了之後呼叫），再讓他們走過去。
func follow_anchor(dt: float, speed: float) -> void:
	if ring != null:
		ring.position = anchor + Vector3(0.0, 0.08, 0.0)
	var squad_slots := RTSKit.formation(anchor, SQUADS, SQUAD_SPACING)
	for s in SQUADS:
		var man_slots := RTSKit.formation(squad_slots[s], MEN_PER_SQUAD, MAN_SPACING)
		for m in MEN_PER_SQUAD:
			var man := soldiers[s * MEN_PER_SQUAD + m]
			man.target_point = man_slots[m]
			man.advance(dt, speed * 1.25)

func to_dict() -> Dictionary:
	var d := {"id": id, "name": display_name, "echelon": "platoon", "type": unit_type, "parent": parent_id if parent_id != "" else null,
		"strength": strength, "state": state, "sector": sector, "controlled_by": controlled_by, "cost": cost}
	d["task"] = task.duplicate() if not task.is_empty() else null
	return d
