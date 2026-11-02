class_name FormationAI
extends RefCounted
## 編制 AI（移植 m0/chief/formation_ai.py，規則 docs/10 §2、§3）：任務式命令 → 這個排下一步該走到哪個分區。
## 純函式：吃 Platoon 與 Orbat 的查詢，不碰隨機數。

## 連的任務拆給「可行動」子排（排除殲滅、潰散；參謀長的令也排除總司令直轄的排）。flank：第一個排原地 hold，其餘 flank。
static func split_company_task(children: Array, task: Dictionary, include_player: bool = false) -> Dictionary:
	var alive: Array = []
	for c in children:
		if c.state != "destroyed" and c.state != "routed" and (include_player or c.controlled_by != "player"):
			alive.append(c)
	var out := {}
	if task["type"] == "flank" and alive.size() >= 2:
		out[alive[0].id] = {"type": "hold", "target": alive[0].sector}
		for i in range(1, alive.size()):
			out[alive[i].id] = task.duplicate()
		return out
	for c in alive:
		out[c.id] = task.duplicate()
	return out

## 側翼進入點：目標的鄰格中離「我方主力所在格」最遠的那一格（同距取固定順序第一個）。
static func flank_approach_sector(grid: SectorGrid, target: String, main_sector: String) -> String:
	var cands := grid.neighbors(target)
	if cands.is_empty():
		return ""
	if main_sector == "":
		return cands[0]
	var best := cands[0]
	var best_d := SectorGrid.distance(best, main_sector)
	for s in cands:
		var d := SectorGrid.distance(s, main_sector)
		if d > best_d:
			best = s
			best_d = d
	return best

## 回傳這個排接下來要走到的分區 id；"" 表示原地。
static func decide_move(p: Platoon, orbat: Orbat) -> String:
	if p.state == "destroyed" or (p.state != "routed" and p.task.is_empty()):
		return ""   # 沒任務的排不用算 avoid（每 tick 省一輪查表）
	var grid := orbat.grid
	var avoid := orbat.blocked_sectors(p)
	if p.state == "routed":
		# 潰散：有 withdraw 令就照令；否則往最近「沒有敵軍」的本方分區退，退路也不穿敵格（§2 v1.1）
		avoid.merge(orbat.hostile_sectors(p.side))
		if p.task.get("type", "") == "withdraw":
			return grid.next_step(p.sector, p.task["target"], avoid)
		var safe := orbat.safe_own_sectors(p.side)
		if safe.is_empty() or safe.has(p.sector):
			return ""
		var goal := ""
		var best := 1 << 30
		var keys := safe.keys()
		keys.sort()
		for s in keys:
			var d := SectorGrid.distance(p.sector, s)
			if d < best:
				best = d
				goal = s
		return grid.next_step(p.sector, goal, avoid)
	if p.task.is_empty():
		return ""
	var t: String = p.task["type"]
	var target: String = p.task["target"]
	if t in ["seize", "hold", "withdraw", "reserve"]:
		return grid.next_step(p.sector, target, avoid)
	if t == "support":
		var buddy_sector := orbat.unit_sector(p.side, target)
		if buddy_sector == "":
			return ""
		if p.sector == buddy_sector or p.sector in grid.neighbors(buddy_sector):
			return ""   # 已在友軍同格或相鄰格，固守
		var cands: Array[String] = []
		for s in grid.neighbors(buddy_sector):
			if not avoid.has(s):
				cands.append(s)
		if cands.is_empty():
			cands = grid.neighbors(buddy_sector)
		var goal := cands[0]
		var best := SectorGrid.distance(p.sector, goal)
		for s in cands:
			var d := SectorGrid.distance(p.sector, s)
			if d < best or (d == best and s < goal):
				best = d
				goal = s
		return grid.next_step(p.sector, goal, avoid)
	if t == "flank":
		if p.sector == target:
			return ""
		var main := orbat.strongest_other_sector(p)
		var approach := flank_approach_sector(grid, target, main)
		if approach == "":
			return grid.next_step(p.sector, target, avoid)
		if p.sector == approach:
			return "" if avoid.has(target) else target   # 從側翼進入目標（目標本身進不去就原地）
		var avoid2 := avoid.duplicate()
		avoid2[target] = true   # 繞路時不穿過目標
		return grid.next_step(p.sector, approach, avoid2)
	return ""
