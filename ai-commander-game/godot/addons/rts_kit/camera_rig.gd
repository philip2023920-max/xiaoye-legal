class_name RTSCameraRig
extends Node3D
## Top-down RTS camera.
##
## The rig sits on the ground and the camera hangs back and above it, so
## panning is a flat slide and zooming is a dolly along the view axis. A fixed
## pitch means height always reads the same way on screen.
##
## Pan: WASD, arrow keys, screen edges, or middle-mouse drag. Zoom: wheel.

signal moved

@export var pan_speed: float = 30.0
@export var edge_scroll_enabled: bool = true
@export var edge_scroll_margin: float = 16.0
@export var middle_drag_enabled: bool = true
@export var zoom_step: float = 4.0
@export var min_distance: float = 12.0
@export var max_distance: float = 120.0
@export var distance: float = 50.0:
	set(value):
		distance = clampf(value, min_distance, max_distance)
		if is_inside_tree():
			_place_camera()
@export_range(10.0, 89.0) var pitch_degrees: float = 55.0
## Where the rig may go on the ground (XZ). A zero-size rect means anywhere.
@export var bounds: Rect2 = Rect2(-100, -100, 200, 200)
## Physics layers that count as ground for [method ground_at]. With nothing
## there, the flat plane at [member ground_height] is used instead.
@export_flags_3d_physics var ground_collision_mask: int = 1
@export var ground_height: float = 0.0

var camera: Camera3D
var _middle_dragging: bool = false

func _ready() -> void:
	add_to_group(RTSKit.CAMERA_GROUP)
	camera = get_node_or_null("Camera3D") as Camera3D
	if camera == null:
		camera = Camera3D.new()
		camera.name = "Camera3D"
		add_child(camera)
	camera.current = true
	distance = distance
	_place_camera()

func _process(delta: float) -> void:
	var move := Vector3.ZERO
	if Input.is_physical_key_pressed(KEY_A) or Input.is_action_pressed("ui_left"):
		move.x -= 1.0
	if Input.is_physical_key_pressed(KEY_D) or Input.is_action_pressed("ui_right"):
		move.x += 1.0
	if Input.is_physical_key_pressed(KEY_W) or Input.is_action_pressed("ui_up"):
		move.z -= 1.0
	if Input.is_physical_key_pressed(KEY_S) or Input.is_action_pressed("ui_down"):
		move.z += 1.0
	if edge_scroll_enabled and _mouse_in_window():
		var size := get_viewport().get_visible_rect().size
		var mouse := get_viewport().get_mouse_position()
		if mouse.x <= edge_scroll_margin:
			move.x -= 1.0
		elif mouse.x >= size.x - edge_scroll_margin:
			move.x += 1.0
		if mouse.y <= edge_scroll_margin:
			move.z -= 1.0
		elif mouse.y >= size.y - edge_scroll_margin:
			move.z += 1.0
	if move != Vector3.ZERO:
		# Pan speed follows zoom, so the map crosses the screen at a similar
		# rate whether you are close in or pulled right back.
		var rate: float = pan_speed * (distance / 50.0)
		_slide(move.normalized().rotated(Vector3.UP, rotation.y) * rate * delta)

func _mouse_in_window() -> bool:
	if DisplayServer.get_name() == "headless" or not DisplayServer.window_is_focused():
		return false
	return get_viewport().get_visible_rect().has_point(get_viewport().get_mouse_position())

func _unhandled_input(event: InputEvent) -> void:
	var button := event as InputEventMouseButton
	if button != null:
		if button.pressed and button.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance -= zoom_step
		elif button.pressed and button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance += zoom_step
		elif button.button_index == MOUSE_BUTTON_MIDDLE and middle_drag_enabled:
			_middle_dragging = button.pressed
		return
	var motion := event as InputEventMouseMotion
	if motion != null and _middle_dragging:
		# Drag the ground under the cursor: move opposite to the mouse, scaled
		# so a point on the ground roughly stays under the pointer.
		var per_pixel: float = distance / get_viewport().get_visible_rect().size.y * 1.4
		_slide(Vector3(-motion.relative.x, 0.0, -motion.relative.y).rotated(Vector3.UP, rotation.y) * per_pixel)

func _slide(offset: Vector3) -> void:
	position += offset
	_clamp_to_bounds()
	moved.emit()

## Centre the view on a point on the ground. Every "take me there" should go
## through here, so none of them can put the camera where panning would not.
func look_at_ground(point: Vector3) -> void:
	position.x = point.x
	position.z = point.z
	_clamp_to_bounds()
	moved.emit()

func _clamp_to_bounds() -> void:
	if bounds.size == Vector2.ZERO:
		return
	position.x = clampf(position.x, bounds.position.x, bounds.end.x)
	position.z = clampf(position.z, bounds.position.y, bounds.end.y)

func _place_camera() -> void:
	if camera == null:
		return
	var pitch := deg_to_rad(pitch_degrees)
	camera.position = Vector3(0.0, sin(pitch) * distance, cos(pitch) * distance)
	camera.rotation = Vector3(-pitch, 0.0, 0.0)

## Where the mouse cursor meets the ground.
func ground_under_mouse() -> Vector3:
	return ground_at(get_viewport().get_mouse_position())

## Where a screen point meets the ground: physics first (so orders on a
## hillside land on the hillside), then the flat plane.
func ground_at(screen_point: Vector2) -> Vector3:
	var origin := camera.project_ray_origin(screen_point)
	var dir := camera.project_ray_normal(screen_point)
	if ground_collision_mask != 0 and is_inside_tree():
		var query := PhysicsRayQueryParameters3D.create(origin, origin + dir * 5000.0,
			ground_collision_mask)
		var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if not hit.is_empty():
			return hit["position"]
	if absf(dir.y) < 0.0001:
		return Vector3(position.x, ground_height, position.z)
	var t: float = (ground_height - origin.y) / dir.y
	if t < 0.0:
		# Looking at the sky: the horizon, as far out as the camera reaches.
		t = max_distance * 4.0
	return origin + dir * t

func screen_position(world: Vector3) -> Vector2:
	return camera.unproject_position(world)

func is_on_screen(world: Vector3) -> bool:
	if camera.is_position_behind(world):
		return false
	return get_viewport().get_visible_rect().has_point(screen_position(world))
