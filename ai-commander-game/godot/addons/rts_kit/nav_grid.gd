class_name RTSNavGrid
extends RefCounted
## Grid pathfinding for ground units, with routes pulled tight.
##
## Built on Godot's [AStarGrid2D]. A raw grid path is a staircase of cell
## centres; this drops every corner a unit can see past, so a route around a
## wall is a few clean waypoints. Mark ground as blocked by hand
## ([method block_rect], [method block_circle]) or bake it from your level's
## colliders ([method bake_from_physics]).
##
## Coarse cells are fine: routes are pulled tight afterwards, so a cell only has
## to be small enough to find the gaps.

var world_rect: Rect2
var cell_size: float
var size: Vector2i

var _astar := AStarGrid2D.new()

func _init(rect: Rect2 = Rect2(-100, -100, 200, 200), cell: float = 2.0) -> void:
	world_rect = rect
	cell_size = cell
	size = Vector2i(maxi(1, ceili(rect.size.x / cell)), maxi(1, ceili(rect.size.y / cell)))
	_astar.region = Rect2i(Vector2i.ZERO, size)
	_astar.cell_size = Vector2.ONE
	_astar.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	_astar.update()

func cell_of(p: Vector3) -> Vector2i:
	return Vector2i(
		clampi(floori((p.x - world_rect.position.x) / cell_size), 0, size.x - 1),
		clampi(floori((p.z - world_rect.position.y) / cell_size), 0, size.y - 1))

func centre_of(cell: Vector2i, y: float = 0.0) -> Vector3:
	return Vector3(world_rect.position.x + (cell.x + 0.5) * cell_size, y,
		world_rect.position.y + (cell.y + 0.5) * cell_size)

func set_cell_solid(cell: Vector2i, solid: bool = true) -> void:
	if _astar.region.has_point(cell):
		_astar.set_point_solid(cell, solid)

func is_cell_solid(cell: Vector2i) -> bool:
	return not _astar.region.has_point(cell) or _astar.is_point_solid(cell)

func is_blocked(p: Vector3) -> bool:
	return is_cell_solid(cell_of(p))

## Block (or clear) every cell whose centre is inside a world-space XZ rect.
func block_rect(rect: Rect2, solid: bool = true) -> void:
	for cy in size.y:
		for cx in size.x:
			var c := centre_of(Vector2i(cx, cy))
			if rect.has_point(Vector2(c.x, c.z)):
				_astar.set_point_solid(Vector2i(cx, cy), solid)

func block_circle(centre: Vector3, radius: float, solid: bool = true) -> void:
	var lo := cell_of(centre - Vector3(radius, 0.0, radius))
	var hi := cell_of(centre + Vector3(radius, 0.0, radius))
	for cy in range(lo.y, hi.y + 1):
		for cx in range(lo.x, hi.x + 1):
			if RTSKit.flat_distance(centre_of(Vector2i(cx, cy)), centre) <= radius:
				_astar.set_point_solid(Vector2i(cx, cy), solid)

## Mark a cell solid wherever a sphere of [param clearance] at [param probe_height]
## touches a collider on [param collision_mask]. Keep your ground on a layer that
## is NOT in the mask, or everything will be blocked. Returns the solid count.
##
## Call after the level is in the tree and one physics frame has passed.
func bake_from_physics(world: World3D, collision_mask: int, clearance: float = 1.0,
		probe_height: float = 1.0) -> int:
	var space := world.direct_space_state
	var sphere := SphereShape3D.new()
	sphere.radius = clearance
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = sphere
	query.collision_mask = collision_mask
	var solid := 0
	for cy in size.y:
		for cx in size.x:
			query.transform = Transform3D(Basis.IDENTITY, centre_of(Vector2i(cx, cy), probe_height))
			var hit := not space.intersect_shape(query, 1).is_empty()
			_astar.set_point_solid(Vector2i(cx, cy), hit)
			if hit:
				solid += 1
	return solid

## Can a unit walk the straight line from [param a] to [param b]? The cells the
## ends stand in are not checked, so a unit brushing a wall can still leave it.
##
## Every cell the line passes through is checked, by walking the grid cell to
## cell. Where the line crosses exactly through a corner it counts as blocked if
## either cell beside the corner is solid, the same rule the path finder uses
## for a diagonal step, so a route cannot slip between two walls that only
## touch at a corner. (Sampling the line every half cell, as this did before
## 2026-10-18, missed exactly that crossing.)
func walkable(a: Vector3, b: Vector3) -> bool:
	var ca := cell_of(a)
	var cb := cell_of(b)
	var gx := (a.x - world_rect.position.x) / cell_size
	var gy := (a.z - world_rect.position.y) / cell_size
	var dx := (b.x - a.x) / cell_size
	var dy := (b.z - a.z) / cell_size
	var cell := ca
	var step := Vector2i(int(signf(dx)), int(signf(dy)))
	var t_delta_x := INF if is_zero_approx(dx) else absf(1.0 / dx)
	var t_delta_y := INF if is_zero_approx(dy) else absf(1.0 / dy)
	var t_max_x := INF
	var t_max_y := INF
	if step.x != 0:
		t_max_x = ((floorf(gx) + (1.0 if step.x > 0 else 0.0)) - gx) / dx
	if step.y != 0:
		t_max_y = ((floorf(gy) + (1.0 if step.y > 0 else 0.0)) - gy) / dy
	var guard := size.x + size.y + 2
	while cell != cb and guard > 0:
		guard -= 1
		if minf(t_max_x, t_max_y) > 1.0:
			break
		if is_equal_approx(t_max_x, t_max_y):
			# Through a corner: the two cells beside it, then the diagonal one.
			if _solid_between(cell + Vector2i(step.x, 0), ca, cb) \
					or _solid_between(cell + Vector2i(0, step.y), ca, cb):
				return false
			cell += step
			t_max_x += t_delta_x
			t_max_y += t_delta_y
		elif t_max_x < t_max_y:
			cell.x += step.x
			t_max_x += t_delta_x
		else:
			cell.y += step.y
			t_max_y += t_delta_y
		if _solid_between(cell, ca, cb):
			return false
	return true

## A cell on the line that blocks it: on the grid, solid, and not an end cell.
func _solid_between(c: Vector2i, ca: Vector2i, cb: Vector2i) -> bool:
	return c != ca and c != cb and _astar.region.has_point(c) and _astar.is_point_solid(c)

## Waypoints from [param from] to [param to], not including [param from]. Ends
## at [param to] when it can be reached, otherwise at the nearest point that
## can. Waypoints take [param to]'s height; units handle their own ground.
func route(from: Vector3, to: Vector3) -> PackedVector3Array:
	var goal_cell := cell_of(to)
	var goal_open := not _astar.is_point_solid(goal_cell)
	if goal_open and walkable(from, to):
		return PackedVector3Array([to])
	var start := _open_near(cell_of(from))
	var goal := _open_near(goal_cell)
	var cells: Array[Vector2i] = _astar.get_id_path(start, goal, true)
	var chain := PackedVector3Array([from])
	for c in cells:
		chain.append(centre_of(c, to.y))
	var reached := not cells.is_empty() and cells[cells.size() - 1] == goal_cell
	if reached:
		chain[chain.size() - 1] = to
	if chain.size() == 1:
		return PackedVector3Array()
	return _pull_tight(chain)

func _pull_tight(chain: PackedVector3Array) -> PackedVector3Array:
	var kept := PackedVector3Array()
	var here := 0
	while here < chain.size() - 1:
		var reach := here + 1
		for ahead in range(chain.size() - 1, here, -1):
			if walkable(chain[here], chain[ahead]):
				reach = ahead
				break
		kept.append(chain[reach])
		here = reach
	return kept

## The nearest open cell, searching outward ring by ring. Ties break on the
## coordinates, never on loop order, so two mirrored units get mirrored answers.
func _open_near(cell: Vector2i) -> Vector2i:
	if not _astar.is_point_solid(cell):
		return cell
	for ring in range(1, maxi(size.x, size.y)):
		var best := Vector2i(-1, -1)
		var best_d := INF
		for dy in range(-ring, ring + 1):
			for dx in range(-ring, ring + 1):
				if maxi(absi(dx), absi(dy)) != ring:
					continue
				var c := cell + Vector2i(dx, dy)
				if not _astar.region.has_point(c) or _astar.is_point_solid(c):
					continue
				var d := float(dx * dx + dy * dy)
				if d < best_d or (d == best_d and (c.x < best.x or (c.x == best.x and c.y < best.y))):
					best_d = d
					best = c
		if best.x >= 0:
			return best
	return cell
