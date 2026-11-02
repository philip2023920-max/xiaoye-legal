class_name RTSSelection
extends Node
## Mouse and keyboard to selection and orders.
##
## Left click picks, left drag boxes, Shift adds, double-click takes every unit
## of that kind on screen. Right click orders: onto an enemy it attacks, onto
## ground it moves in formation, and Shift queues. Ctrl+1..9 saves a control
## group, 1..9 recalls it, and pressing the number twice quickly jumps the
## camera there.
##
## Units are picked by projecting them onto the screen rather than by
## raycasting, so a small unit seen from far off is still easy to click and
## needs no oversized collision shape.

signal selection_changed(units: Array[Node3D])
## Fired for every order, before units are told. Use it for sounds, markers,
## or to handle orders yourself instead of through the rts_* methods.
signal order_issued(units: Array[Node3D], point: Vector3, target: Node3D, queued: bool)

@export var camera_rig: RTSCameraRig
@export var player_team: int = 0
@export var pick_radius: float = 24.0
@export var drag_threshold: float = 6.0
## Gap between units when a group is sent to one point. 0 sends all to the point.
@export var formation_spacing: float = 3.0
@export var control_groups_enabled: bool = true
## Seconds within which a second press of a group key jumps the camera to it.
@export var group_double_tap: float = 0.4
@export var stop_key: Key = KEY_H
@export var box_fill: Color = Color(0.45, 0.85, 1.0, 0.12)
@export var box_border: Color = Color(0.45, 0.85, 1.0, 0.9)

var selected: Array[Node3D] = []

var _dragging: bool = false
var _drag_start: Vector2 = Vector2.ZERO
var _drag_now: Vector2 = Vector2.ZERO
var _ignore_release: bool = false
var _groups: Dictionary = {}
var _last_group_key: int = -1
var _last_group_time: float = -10.0

func _ready() -> void:
	add_to_group(RTSKit.SELECTION_GROUP)
	if camera_rig == null:
		camera_rig = get_tree().get_first_node_in_group(RTSKit.CAMERA_GROUP) as RTSCameraRig
	var layer := CanvasLayer.new()
	layer.layer = 90
	add_child(layer)
	var box := preload("selection_box.gd").new()
	box.selection = self
	layer.add_child(box)

func is_dragging() -> bool:
	return _dragging and _drag_start.distance_to(_drag_now) >= drag_threshold

func drag_rect() -> Rect2:
	return Rect2(_drag_start, Vector2.ZERO).expand(_drag_now)

func _unhandled_input(event: InputEvent) -> void:
	if camera_rig == null:
		return
	var button := event as InputEventMouseButton
	if button != null:
		if button.button_index == MOUSE_BUTTON_LEFT:
			if button.pressed and button.double_click:
				select_kind_at_screen(button.position)
				_dragging = false
				_ignore_release = true
			elif button.pressed:
				_dragging = true
				_drag_start = button.position
				_drag_now = button.position
			elif _ignore_release:
				_ignore_release = false
			elif _dragging:
				_drag_now = button.position
				var was_box := is_dragging()
				_dragging = false
				if was_box:
					select_in_screen_rect(drag_rect(), button.shift_pressed)
				else:
					select_at_screen(button.position, button.shift_pressed)
		elif button.button_index == MOUSE_BUTTON_RIGHT and button.pressed:
			order_at_screen(button.position, button.shift_pressed)
		return
	var motion := event as InputEventMouseMotion
	if motion != null and _dragging:
		_drag_now = motion.position
		return
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo:
		if control_groups_enabled and key.keycode >= KEY_1 and key.keycode <= KEY_9:
			var slot: int = key.keycode - KEY_1
			if key.ctrl_pressed:
				assign_group(slot)
			else:
				_recall_pressed(slot)
		elif key.keycode == stop_key:
			stop()

# ------------------------------------------------------------ selecting

## Replace (or add to) the selection. Only your own live units are kept.
func select(units: Array, additive: bool = false) -> void:
	if not additive:
		for unit in selected:
			_mark(unit, false)
		selected.clear()
	for node in units:
		var unit := node as Node3D
		if unit == null or not RTSKit.is_alive(unit) or RTSKit.team_of(unit) != player_team:
			continue
		if not selected.has(unit):
			selected.append(unit)
			_mark(unit, true)
	selection_changed.emit(selected)

func clear() -> void:
	select([], false)

## Select the unit under the cursor. The nearest unit of any team wins, so
## clicking an enemy beside your own unit selects nothing rather than the friend.
func select_at_screen(point: Vector2, additive: bool = false) -> void:
	var unit := unit_at_screen(point, -1)
	if unit != null and RTSKit.team_of(unit) != player_team:
		unit = null
	if unit == null and additive:
		return
	select([unit] if unit != null else [], additive)

func select_in_screen_rect(rect: Rect2, additive: bool = false) -> void:
	var found: Array[Node3D] = []
	for unit in RTSKit.units(get_tree(), player_team):
		if not RTSKit.box_selectable(unit) or not camera_rig.is_on_screen(unit.global_position):
			continue
		if rect.has_point(camera_rig.screen_position(unit.global_position)):
			found.append(unit)
	select(found, additive)

## Every unit of the clicked unit's kind that is on screen.
func select_kind_at_screen(point: Vector2) -> void:
	var clicked := unit_at_screen(point, player_team)
	if clicked == null:
		return
	var kind := RTSKit.kind_of(clicked)
	var found: Array[Node3D] = []
	for unit in RTSKit.units(get_tree(), player_team):
		if RTSKit.kind_of(unit) == kind and camera_rig.is_on_screen(unit.global_position):
			found.append(unit)
	select(found)

## The nearest unit to a screen point, within [member pick_radius]. With a team
## of -1, any team. Hidden units (fog) cannot be picked.
func unit_at_screen(point: Vector2, team: int = -1) -> Node3D:
	var best: Node3D = null
	var best_d := pick_radius
	for unit in RTSKit.units(get_tree(), team):
		if not unit.is_visible_in_tree() or not camera_rig.is_on_screen(unit.global_position):
			continue
		var d: float = point.distance_to(camera_rig.screen_position(unit.global_position))
		if d < best_d:
			best_d = d
			best = unit
	return best

func _mark(unit: Node3D, on: bool) -> void:
	if is_instance_valid(unit) and unit.has_method("rts_set_selected"):
		unit.call("rts_set_selected", on)

func _prune() -> void:
	var live: Array[Node3D] = []
	for unit in selected:
		if RTSKit.is_alive(unit):
			live.append(unit)
	selected = live

# ------------------------------------------------------------ control groups

func assign_group(slot: int) -> void:
	_prune()
	_groups[slot] = selected.duplicate()

func group(slot: int) -> Array[Node3D]:
	var live: Array[Node3D] = []
	for unit in _groups.get(slot, []):
		if RTSKit.is_alive(unit):
			live.append(unit)
	_groups[slot] = live
	return live

func recall_group(slot: int, jump_camera: bool = false) -> void:
	var units := group(slot)
	if units.is_empty():
		return
	select(units)
	if jump_camera and camera_rig != null:
		camera_rig.look_at_ground(_centre(units))

func _recall_pressed(slot: int) -> void:
	var now := Time.get_ticks_msec() / 1000.0
	var twice := slot == _last_group_key and now - _last_group_time <= group_double_tap
	_last_group_key = slot
	_last_group_time = now
	recall_group(slot, twice)

func _centre(units: Array[Node3D]) -> Vector3:
	var sum := Vector3.ZERO
	for unit in units:
		sum += unit.global_position
	return sum / float(maxi(units.size(), 1))

# ------------------------------------------------------------ orders

func order_at_screen(point: Vector2, queued: bool = false) -> void:
	var target := unit_at_screen(point, -1)
	if target != null and RTSKit.team_of(target) == player_team:
		target = null
	order_ground(camera_rig.ground_at(point), target, queued)

## The same order from anywhere: the minimap calls this, so a right-click there
## and a right-click on the world cannot drift apart.
func order_ground(point: Vector3, target: Node3D = null, queued: bool = false) -> void:
	_prune()
	if selected.is_empty():
		return
	order_issued.emit(selected, point, target, queued)
	var movers: Array[Node3D] = []
	for unit in selected:
		if target != null and unit.has_method("rts_attack"):
			unit.call("rts_attack", target)
		elif unit.has_method("rts_move"):
			movers.append(unit)
	if movers.is_empty():
		return
	if formation_spacing <= 0.0 or movers.size() == 1:
		for unit in movers:
			unit.call("rts_move", point, queued)
		return
	var slots := RTSKit.formation(point, movers.size(), formation_spacing)
	var assigned := RTSKit.assign_slots(movers, slots)
	for unit in movers:
		unit.call("rts_move", assigned.get(unit, point), queued)

func stop() -> void:
	_prune()
	for unit in selected:
		if unit.has_method("rts_stop"):
			unit.call("rts_stop")
