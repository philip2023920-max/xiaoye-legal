class_name RTSMinimap
extends Control
## A minimap: ground shaded by the fog, units as dots, the camera's view as a
## frame. Left click or drag moves the camera; right click orders the selection
## there, exactly as a right click on the world would (Shift queues).
##
## Set [member world_rect] to the same rect as the fog. The other references
## are found by group when left empty.

@export var world_rect: Rect2 = Rect2(-100, -100, 200, 200)
@export var camera_rig: RTSCameraRig
@export var selection: RTSSelection
@export var fog: RTSFogOfWar
@export var player_team: int = 0
## Dot colour per team index; teams past the end use the last colour.
@export var team_colors: Array[Color] = [Color(0.35, 0.75, 1.0), Color(1.0, 0.35, 0.3), Color(1.0, 0.85, 0.3)]
@export var unexplored_color: Color = Color(0.02, 0.025, 0.03)
@export var remembered_color: Color = Color(0.16, 0.2, 0.17)
@export var visible_color: Color = Color(0.3, 0.38, 0.3)
@export var frame_color: Color = Color(1, 1, 1, 0.8)
@export var dot_radius: float = 2.5
@export var redraw_interval: float = 0.1

var _ground: ColorRect
var _marks: Control
var _timer: float = 0.0
var _dragging: bool = false

const _GROUND_SHADER := """
shader_type canvas_item;
uniform sampler2D visible_tex : filter_linear, hint_default_white;
uniform sampler2D explored_tex : filter_linear, hint_default_white;
uniform vec4 unexplored : source_color;
uniform vec4 remembered : source_color;
uniform vec4 seen : source_color;
void fragment() {
	float v = texture(visible_tex, UV).r;
	float k = texture(explored_tex, UV).r;
	COLOR = mix(mix(unexplored, remembered, k), seen, v);
}
"""

func _ready() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	var shader := Shader.new()
	shader.code = _GROUND_SHADER
	var material := ShaderMaterial.new()
	material.shader = shader
	_ground = ColorRect.new()
	_ground.material = material
	_ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ground.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_ground)
	_marks = Control.new()
	_marks.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_marks.set_anchors_preset(Control.PRESET_FULL_RECT)
	_marks.draw.connect(_draw_marks)
	add_child(_marks)
	call_deferred("_find_references")

func _find_references() -> void:
	if camera_rig == null:
		camera_rig = get_tree().get_first_node_in_group(RTSKit.CAMERA_GROUP) as RTSCameraRig
	if selection == null:
		selection = get_tree().get_first_node_in_group(RTSKit.SELECTION_GROUP) as RTSSelection
	if fog == null:
		fog = get_tree().get_first_node_in_group(RTSKit.FOG_GROUP) as RTSFogOfWar
	var material := _ground.material as ShaderMaterial
	material.set_shader_parameter("unexplored", unexplored_color)
	material.set_shader_parameter("remembered", remembered_color)
	material.set_shader_parameter("seen", visible_color)
	if fog != null:
		material.set_shader_parameter("visible_tex", fog.visible_texture)
		material.set_shader_parameter("explored_tex", fog.explored_texture)

func _process(delta: float) -> void:
	_timer += delta
	if _timer >= redraw_interval:
		_timer = 0.0
		_marks.queue_redraw()

func world_to_map(p: Vector3) -> Vector2:
	var uv := (Vector2(p.x, p.z) - world_rect.position) / world_rect.size
	return uv * size

func map_to_world(point: Vector2) -> Vector3:
	var uv := point / size
	var xz := world_rect.position + uv * world_rect.size
	var y: float = camera_rig.ground_height if camera_rig != null else 0.0
	return Vector3(xz.x, y, xz.y)

func _draw_marks() -> void:
	var tree := get_tree()
	if tree == null:
		return
	for unit in RTSKit.units(tree):
		var team := RTSKit.team_of(unit)
		if team != player_team and not unit.is_visible_in_tree():
			continue
		var color: Color = team_colors[clampi(team, 0, team_colors.size() - 1)] if not team_colors.is_empty() else Color.WHITE
		var at := world_to_map(unit.global_position)
		var selected := selection != null and selection.selected.has(unit)
		_marks.draw_circle(at, dot_radius + (1.0 if selected else 0.0), Color.WHITE if selected else color)
	if camera_rig != null and camera_rig.camera != null:
		var view := camera_rig.get_viewport().get_visible_rect().size
		var corners := PackedVector2Array()
		for p in [Vector2.ZERO, Vector2(view.x, 0), view, Vector2(0, view.y), Vector2.ZERO]:
			corners.append(world_to_map(camera_rig.ground_at(p)))
		_marks.draw_polyline(corners, frame_color, 1.0)

func _gui_input(event: InputEvent) -> void:
	var button := event as InputEventMouseButton
	if button != null:
		if button.button_index == MOUSE_BUTTON_LEFT:
			_dragging = button.pressed
			if button.pressed and camera_rig != null:
				camera_rig.look_at_ground(map_to_world(button.position))
		elif button.button_index == MOUSE_BUTTON_RIGHT and button.pressed and selection != null:
			selection.order_ground(map_to_world(button.position), null, button.shift_pressed)
		accept_event()
		return
	var motion := event as InputEventMouseMotion
	if motion != null and _dragging and camera_rig != null:
		camera_rig.look_at_ground(map_to_world(motion.position))
		accept_event()
