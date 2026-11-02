class_name RTSKit
extends RefCounted
## Shared conventions for the RTS Kit.
##
## The kit never asks your units to extend a base class. A unit is any
## [Node3D] in the group [constant UNIT_GROUP]. Everything else is optional and
## duck-typed, so the kit fits a game that already has its own unit script:
##
## [codeblock]
## var team: int                  # which side it is on (required)
## var vision_radius: float       # how far it lifts the fog (0 = none)
## var unit_type: String          # what double-click selects all of
## var rts_box_selectable: bool   # false keeps buildings out of box selection
##
## func rts_set_selected(on: bool) -> void    # show or hide a ring
## func rts_move(point: Vector3, queued: bool) -> void
## func rts_attack(target: Node3D) -> void
## func rts_stop() -> void
## func rts_is_alive() -> bool
## [/codeblock]

const UNIT_GROUP := &"rts_units"
const CAMERA_GROUP := &"rts_camera"
const FOG_GROUP := &"rts_fog"
const SELECTION_GROUP := &"rts_selection"

static func team_of(unit: Node) -> int:
	var team: Variant = unit.get("team")
	return int(team) if team != null else -1

static func is_alive(unit: Object) -> bool:
	if not is_instance_valid(unit):
		return false
	var node := unit as Node
	if node == null or node.is_queued_for_deletion():
		return false
	if node.has_method("rts_is_alive"):
		return bool(node.call("rts_is_alive"))
	return true

static func vision_of(unit: Node) -> float:
	var radius: Variant = unit.get("vision_radius")
	return float(radius) if radius != null else 0.0

## What "the same kind of unit" means for double-click selection.
static func kind_of(unit: Node) -> String:
	var kind: Variant = unit.get("unit_type")
	if kind != null and String(kind) != "":
		return String(kind)
	if unit.scene_file_path != "":
		return unit.scene_file_path
	var script: Script = unit.get_script()
	return script.resource_path if script != null else unit.get_class()

static func box_selectable(unit: Node) -> bool:
	var flag: Variant = unit.get("rts_box_selectable")
	return flag == null or bool(flag)

## Every live unit, optionally only one team's.
static func units(tree: SceneTree, team: int = -1) -> Array[Node3D]:
	var out: Array[Node3D] = []
	for node in tree.get_nodes_in_group(UNIT_GROUP):
		var unit := node as Node3D
		if unit != null and is_alive(unit) and (team < 0 or team_of(unit) == team):
			out.append(unit)
	return out

## Ground distance: horizontal only. A drone overhead is "here" for an order.
static func flat_distance(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()

## Slots for [param count] units around [param center], in a square-ish block,
## so a group sent to one point does not try to stand on it all at once.
static func formation(center: Vector3, count: int, spacing: float) -> Array[Vector3]:
	var out: Array[Vector3] = []
	if count <= 0:
		return out
	var cols: int = ceili(sqrt(float(count)))
	var rows: int = ceili(float(count) / float(cols))
	for i in count:
		var row: int = i / cols
		var col: int = i % cols
		var in_row: int = mini(cols, count - row * cols)
		var x: float = (float(col) - float(in_row - 1) * 0.5) * spacing
		var z: float = (float(row) - float(rows - 1) * 0.5) * spacing
		out.append(center + Vector3(x, 0.0, z))
	return out

## Pair each unit with a slot, nearest first, so units do not cross over each
## other to reach the far side of the block. Greedy rather than optimal: it is
## run once per order, and ties break on list order so the result is stable.
static func assign_slots(units_in: Array, slots: Array[Vector3]) -> Dictionary:
	var result := {}
	var free: Array = units_in.duplicate()
	for slot in slots:
		var best: Node3D = null
		var best_d := INF
		for unit in free:
			var d: float = flat_distance((unit as Node3D).global_position, slot)
			if d < best_d:
				best_d = d
				best = unit
		if best == null:
			break
		free.erase(best)
		result[best] = slot
	return result
