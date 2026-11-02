class_name SectorMap
extends Node3D
## 5×5（或任意）分區格：地形色、擁有方色調、據點旗、方塊掩體、格線，以及世界座標 ↔ 分區 id。
##
## 座標約定（docs/09：A 在左、1 在上）：x 向右＝欄（A→E），z 向下＝列（1→5），
## 每格 SECTOR_SIZE 公尺，A1 的左上角在原點，所以 center_of("C3") == (50, 0, 50)。

const SECTOR_SIZE := 20.0
const LETTERS := "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
const TERRAIN_COLORS := {
	"open": Color(0.56, 0.66, 0.36), "hill": Color(0.64, 0.56, 0.38), "forest": Color(0.26, 0.46, 0.26),
	"town": Color(0.60, 0.58, 0.55), "river": Color(0.30, 0.50, 0.80),
}
const OWNER_TINT := {"us": Color(0.35, 0.55, 1.0), "enemy": Color(1.0, 0.35, 0.3)}
const FLAG_COLORS := {"us": Color(0.3, 0.5, 1.0), "enemy": Color(0.95, 0.25, 0.2), "none": Color(0.95, 0.95, 0.95)}
const COVER_MASK := 1 << 1   # 位元遮罩值（第 2 層），不是層號；掩體給之後尋路烘焙用（骨架約定：地面第 1 層、牆第 2 層）
const GROUND_MASK := 1 << 0  # 第 1 層

var cols := 0
var rows := 0
var sectors := {}       # id -> {terrain, owner, contested, cover, objective}
var objectives := {}    # id -> {sector, value, owner}
var _tiles := {}        # id -> MeshInstance3D
var _flags := {}        # objective id -> Node3D

static func id_of(col: int, row: int) -> String:
	return LETTERS[col] + str(row + 1)

## 分區 id → (欄, 列)；格式不對回 (-1, -1)（例如 "c3" 會先轉大寫，"A" 或 "3A" 不合法）。
static func col_row_of(sector_id: String) -> Vector2i:
	var sid := sector_id.strip_edges().to_upper()
	if sid.length() < 2 or not sid.substr(1).is_valid_int():
		return Vector2i(-1, -1)
	var col := LETTERS.find(sid[0])
	var row := int(sid.substr(1)) - 1
	if col < 0 or row < 0:
		return Vector2i(-1, -1)
	return Vector2i(col, row)

func build_from_board(board: Dictionary) -> void:
	for child in get_children():
		remove_child(child)   # 先脫離樹再釋放：queue_free 要到幀尾才移除，同名新節點會被自動改名
		child.queue_free()
	sectors.clear(); objectives.clear(); _tiles.clear(); _flags.clear()
	var map: Dictionary = board["map"]
	cols = int(map["cols"]); rows = int(map["rows"])
	for sid in map["sectors"].keys():
		var s: Dictionary = map["sectors"][sid]
		sectors[sid] = {"terrain": str(s.get("terrain", "open")), "owner": str(s.get("owner", "none")),
			"contested": bool(s.get("contested", false)), "cover": s.get("cover", null), "objective": s.get("objective", null)}
	for o in board.get("objectives", []):
		objectives[o["id"]] = {"sector": o["sector"], "value": int(o["value"]), "owner": str(o.get("owner", "none"))}
	_build_ground()
	_build_tiles()
	_build_grid_lines()
	_build_props()
	_build_flags()

# ---- 座標 ----
func world_rect() -> Rect2:
	return Rect2(0.0, 0.0, cols * SECTOR_SIZE, rows * SECTOR_SIZE)

func center_of(sector_id: String) -> Vector3:
	assert(sectors.has(sector_id), "不存在的分區 id：%s" % sector_id)
	var cr := col_row_of(sector_id)
	return Vector3((cr.x + 0.5) * SECTOR_SIZE, 0.0, (cr.y + 0.5) * SECTOR_SIZE)

## 世界座標落在哪個分區；出界回空字串。
func sector_at(p: Vector3) -> String:
	var col := floori(p.x / SECTOR_SIZE)
	var row := floori(p.z / SECTOR_SIZE)
	if col < 0 or row < 0 or col >= cols or row >= rows:
		return ""
	return id_of(col, row)

func terrain_of(sector_id: String) -> String:
	return sectors[sector_id]["terrain"]

func owner_of(sector_id: String) -> String:
	return sectors[sector_id]["owner"]

## 分區易手（施工單 13 的歸屬判定會呼叫）：改色、改旗。（不叫 set_owner：那是 Node 內建方法）
func set_sector_owner(sector_id: String, who: String, contested: bool = false) -> void:
	sectors[sector_id]["owner"] = who
	sectors[sector_id]["contested"] = contested
	_paint_tile(sector_id)
	var obj = sectors[sector_id]["objective"]
	if obj != null and objectives.has(obj):
		objectives[obj]["owner"] = who
		_paint_flag(obj)

# ---- 建構 ----
func _material(color: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	return m

func _build_ground() -> void:
	var ground := StaticBody3D.new()
	ground.name = "Ground"
	ground.collision_layer = GROUND_MASK
	ground.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	var rect := world_rect()
	box.size = Vector3(rect.size.x, 1.0, rect.size.y)
	shape.shape = box
	shape.position = Vector3(rect.size.x * 0.5, -0.5, rect.size.y * 0.5)
	ground.add_child(shape)
	add_child(ground)

func _build_tiles() -> void:
	var holder := Node3D.new()
	holder.name = "Tiles"
	add_child(holder)
	for sid in sectors.keys():
		var tile := MeshInstance3D.new()
		tile.name = sid
		var plane := PlaneMesh.new()
		plane.size = Vector2(SECTOR_SIZE - 0.6, SECTOR_SIZE - 0.6)
		tile.mesh = plane
		tile.position = center_of(sid)
		holder.add_child(tile)
		_tiles[sid] = tile
		_paint_tile(sid)

func _paint_tile(sid: String) -> void:
	var s: Dictionary = sectors[sid]
	var color: Color = TERRAIN_COLORS.get(s["terrain"], TERRAIN_COLORS["open"])
	if OWNER_TINT.has(s["owner"]):
		color = color.lerp(OWNER_TINT[s["owner"]], 0.35)
	if s["contested"]:
		color = color.lerp(Color(1.0, 0.9, 0.2), 0.3)
	_tiles[sid].material_override = _material(color)

func _build_grid_lines() -> void:
	var holder := Node3D.new()
	holder.name = "Grid"
	add_child(holder)
	var rect := world_rect()
	var mat := _material(Color(0.12, 0.12, 0.12))
	for c in range(cols + 1):
		var line := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = Vector3(0.3, 0.2, rect.size.y)
		line.mesh = box
		line.material_override = mat
		line.position = Vector3(c * SECTOR_SIZE, 0.1, rect.size.y * 0.5)
		holder.add_child(line)
	for r in range(rows + 1):
		var line := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = Vector3(rect.size.x, 0.2, 0.3)
		line.mesh = box
		line.material_override = mat
		line.position = Vector3(rect.size.x * 0.5, 0.1, r * SECTOR_SIZE)
		holder.add_child(line)

## 掩體：城鎮 6 個方塊、森林 8 棵樹；都是碰撞層 2 的 StaticBody3D，群組 "cover"，meta sector。
func _build_props() -> void:
	var holder := Node3D.new()
	holder.name = "Props"
	add_child(holder)
	for sid in sectors.keys():
		var terrain: String = sectors[sid]["terrain"]
		var c := center_of(sid)
		if terrain == "town":
			var mat := _material(Color(0.45, 0.42, 0.4))
			for i in 6:
				var offset := Vector3((i % 3 - 1) * 6.0, 0.0, floori(i / 3.0) * 7.0 - 3.5)
				holder.add_child(_block(sid, c + offset, Vector3(3.0, 3.0, 3.0), mat))
		elif terrain == "forest":
			var mat := _material(Color(0.18, 0.4, 0.2))
			for i in 8:
				var offset := Vector3((i % 4 - 1.5) * 4.5, 0.0, (floori(i / 4.0) - 0.5) * 7.0)
				holder.add_child(_tree(sid, c + offset, mat))

func _block(sid: String, at: Vector3, size: Vector3, mat: StandardMaterial3D) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = COVER_MASK
	body.collision_mask = 0
	body.position = at + Vector3(0.0, size.y * 0.5, 0.0)
	body.add_to_group("cover")
	body.set_meta("sector", sid)
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	mesh.material_override = mat
	body.add_child(mesh)
	var shape := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	shape.shape = bs
	body.add_child(shape)
	return body

func _tree(sid: String, at: Vector3, mat: StandardMaterial3D) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = COVER_MASK
	body.collision_mask = 0
	body.position = at + Vector3(0.0, 2.5, 0.0)
	body.add_to_group("cover")
	body.set_meta("sector", sid)
	var mesh := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.4; cyl.bottom_radius = 1.4; cyl.height = 5.0
	mesh.mesh = cyl
	mesh.material_override = mat
	body.add_child(mesh)
	var shape := CollisionShape3D.new()
	var cs := CylinderShape3D.new()
	cs.radius = 1.0; cs.height = 5.0
	shape.shape = cs
	body.add_child(shape)
	return body

## 據點旗：旗桿＋旗面＋標籤「O2 (5)」；群組 "objective_flag"，節點名＝目標 id。
func _build_flags() -> void:
	var holder := Node3D.new()
	holder.name = "Flags"
	add_child(holder)
	for oid in objectives.keys():
		var o: Dictionary = objectives[oid]
		var flag := Node3D.new()
		flag.name = oid
		flag.position = center_of(o["sector"])
		flag.add_to_group("objective_flag")
		var pole := MeshInstance3D.new()
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.2; cyl.bottom_radius = 0.2; cyl.height = 6.0
		pole.mesh = cyl
		pole.position = Vector3(0, 3.0, 0)
		pole.material_override = _material(Color(0.3, 0.3, 0.3))
		flag.add_child(pole)
		var cloth := MeshInstance3D.new()
		cloth.name = "Cloth"
		var box := BoxMesh.new()
		box.size = Vector3(2.6, 1.5, 0.1)
		cloth.mesh = box
		cloth.position = Vector3(1.3, 5.2, 0)
		flag.add_child(cloth)
		var label := Label3D.new()
		label.text = "%s (%d)" % [oid, o["value"]]
		label.position = Vector3(0, 7.2, 0)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.font_size = 64
		label.pixel_size = 0.02
		flag.add_child(label)
		holder.add_child(flag)
		_flags[oid] = flag
		_paint_flag(oid)

func _paint_flag(oid: String) -> void:
	var who: String = objectives[oid]["owner"]
	var cloth: MeshInstance3D = _flags[oid].get_node("Cloth")
	cloth.material_override = _material(FLAG_COLORS.get(who, FLAG_COLORS["none"]))
