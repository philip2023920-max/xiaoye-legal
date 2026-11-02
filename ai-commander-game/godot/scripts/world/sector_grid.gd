class_name SectorGrid
extends RefCounted
## 分區格的純邏輯（移植 m0/chief/grid.py）：四鄰固定順序（上、左、右、下）、曼哈頓距離、BFS 最短路第一步。

var cols := 0
var rows := 0

func _init(c: int = 5, r: int = 5) -> void:
	cols = c
	rows = r

func has(sector_id: String) -> bool:
	var cr := SectorMap.col_row_of(sector_id)
	return cr.x >= 0 and cr.y >= 0 and cr.x < cols and cr.y < rows

## 上、左、右、下，固定順序讓結果可重現（§3 側翼「同距依上、左、右、下」靠它）。
func neighbors(sector_id: String) -> Array[String]:
	var cr := SectorMap.col_row_of(sector_id)
	var out: Array[String] = []
	for d in [Vector2i(0, -1), Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, 1)]:
		var n: Vector2i = cr + d
		if n.x >= 0 and n.y >= 0 and n.x < cols and n.y < rows:
			out.append(SectorMap.id_of(n.x, n.y))
	return out

static func distance(a: String, b: String) -> int:
	var pa := SectorMap.col_row_of(a)
	var pb := SectorMap.col_row_of(b)
	return absi(pa.x - pb.x) + absi(pa.y - pb.y)

## BFS 最短路徑的第一步；已到達、無路、或 goal 本身在 avoid 內都回 ""。avoid 是「分區 id → true」的字典（當集合用）。
func next_step(start: String, goal: String, avoid: Dictionary = {}) -> String:
	if start == goal or avoid.has(goal):
		return ""
	var prev := {start: ""}
	var queue: Array[String] = [start]
	var head := 0
	while head < queue.size():
		var cur := queue[head]
		head += 1
		if cur == goal:
			break
		for n in neighbors(cur):
			if not prev.has(n) and not avoid.has(n):
				prev[n] = cur
				queue.append(n)
	if not prev.has(goal):
		return ""
	var node := goal
	while prev[node] != start:
		node = prev[node]
	return node
