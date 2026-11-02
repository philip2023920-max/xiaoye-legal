class_name Soldier
extends Node3D
## 一個方塊人：膠囊體身體＋方塊頭（戰車排畫成低矮方塊車）。沒有物理，位置由排帶著走。

const SIDE_COLORS := {"us": Color(0.30, 0.50, 1.0), "enemy": Color(0.95, 0.30, 0.25)}
const TYPE_HEAD_COLORS := {
	"infantry": Color(0.95, 0.9, 0.8), "mg": Color(1.0, 0.85, 0.2), "mortar": Color(1.0, 0.55, 0.15), "at": Color(0.7, 0.4, 0.9),
	"tank": Color(0.25, 0.25, 0.28), "recon": Color(0.3, 0.9, 0.9), "engineer": Color(0.55, 0.35, 0.2),
}

var alive := true
var unit_type := "infantry"
var side := "us"
var target_point := Vector3.ZERO
var _body: MeshInstance3D
var _head: MeshInstance3D

## 共用資源：同兵種／陣營的人共用同一份 mesh 與材質（Compatibility 渲染器不會自動合批；1,700 人各自一份材質是最差情況）。
static var _mesh_cache := {}
static var _mat_cache := {}

static func _shared_mesh(key: String) -> Mesh:
	if not _mesh_cache.has(key):
		var m: Mesh
		match key:
			"capsule":
				m = CapsuleMesh.new(); m.radius = 0.35; m.height = 1.6
			"tank_body":
				m = BoxMesh.new(); m.size = Vector3(1.6, 1.0, 2.6)
			"head":
				m = BoxMesh.new(); m.size = Vector3(0.55, 0.55, 0.55)
			"tank_head":
				m = BoxMesh.new(); m.size = Vector3(1.0, 0.5, 1.0)
		_mesh_cache[key] = m
	return _mesh_cache[key]

static func _shared_material(key: String, color: Color) -> StandardMaterial3D:
	if not _mat_cache.has(key):
		var mat := StandardMaterial3D.new()
		mat.albedo_color = color
		_mat_cache[key] = mat
	return _mat_cache[key]

func setup(type_: String, side_: String, at: Vector3) -> void:
	unit_type = type_
	side = side_
	position = at
	target_point = at
	_body = MeshInstance3D.new()
	_body.name = "Body"
	if unit_type == "tank":
		_body.mesh = _shared_mesh("tank_body")
		_body.position.y = 0.5
	else:
		_body.mesh = _shared_mesh("capsule")
		_body.position.y = 0.8
	_body.material_override = _shared_material("body:" + side, SIDE_COLORS.get(side, Color.WHITE))
	add_child(_body)
	_head = MeshInstance3D.new()
	_head.name = "Head"
	_head.mesh = _shared_mesh("tank_head" if unit_type == "tank" else "head")
	_head.position.y = 1.85 if unit_type != "tank" else 1.25
	_head.material_override = _shared_material("head:" + unit_type, TYPE_HEAD_COLORS.get(unit_type, Color.WHITE))
	add_child(_head)

func head_color() -> Color:
	return _head.material_override.albedo_color

## 倒地（會戰 LOD：不做全身物理，倒下、變灰）。
func fall() -> void:
	alive = false
	rotation.x = deg_to_rad(90.0)
	position.y = 0.4
	var grey := _shared_material("fallen", Color(0.45, 0.45, 0.45))
	_body.material_override = grey
	_head.material_override = grey

## 朝自己的站位走（speed 公尺／秒），帶一點搖晃。
func advance(dt: float, speed: float) -> void:
	if not alive:
		return
	var flat := Vector3(target_point.x, position.y, target_point.z)
	if position.distance_to(flat) < 0.05:
		rotation.z = 0.0
		return
	position = position.move_toward(flat, speed * dt)
	rotation.z = sin(Time.get_ticks_msec() * 0.012 + position.x) * 0.08
