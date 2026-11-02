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

func setup(type_: String, side_: String, at: Vector3) -> void:
	unit_type = type_
	side = side_
	position = at
	target_point = at
	_body = MeshInstance3D.new()
	_body.name = "Body"
	var body_mat := StandardMaterial3D.new()
	body_mat.albedo_color = SIDE_COLORS.get(side, Color.WHITE)
	if unit_type == "tank":
		var box := BoxMesh.new()
		box.size = Vector3(1.6, 1.0, 2.6)
		_body.mesh = box
		_body.position.y = 0.5
	else:
		var capsule := CapsuleMesh.new()
		capsule.radius = 0.35
		capsule.height = 1.6
		_body.mesh = capsule
		_body.position.y = 0.8
	_body.material_override = body_mat
	add_child(_body)
	_head = MeshInstance3D.new()
	_head.name = "Head"
	var head := BoxMesh.new()
	head.size = Vector3(0.55, 0.55, 0.55) if unit_type != "tank" else Vector3(1.0, 0.5, 1.0)
	_head.mesh = head
	_head.position.y = 1.85 if unit_type != "tank" else 1.25
	var head_mat := StandardMaterial3D.new()
	head_mat.albedo_color = TYPE_HEAD_COLORS.get(unit_type, Color.WHITE)
	_head.material_override = head_mat
	add_child(_head)

func head_color() -> Color:
	return _head.material_override.albedo_color

## 倒地（會戰 LOD：不做全身物理，倒下、變灰）。
func fall() -> void:
	alive = false
	rotation.x = deg_to_rad(90.0)
	position.y = 0.4
	for m in [_body, _head]:
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.45, 0.45, 0.45)
		m.material_override = mat

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
