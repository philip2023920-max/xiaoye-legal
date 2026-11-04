class_name CostHud
extends Label
## 費用 HUD（施工單 21）：本場／今天／本月；預算 80% 黃、100% 紅並寫「參謀長暫停」；本地模型（fake／ollama）另顯示 token 與秒數。
## 資料：每拍回來的 cost_total_usd／usage／latency，與每 30 秒 GET /status 的今天／本月／預算狀態（Battle 餵進來）。

const COLOR_OK := Color(0.9, 0.9, 0.9)
const COLOR_WARN := Color(1.0, 0.85, 0.3)
const COLOR_PAUSED := Color(1.0, 0.45, 0.45)
const WARN_RATIO := 0.8

var last_state := "ok"

func _init() -> void:
	name = "CostHud"
	add_theme_color_override("font_outline_color", Color.BLACK)
	add_theme_constant_override("outline_size", 4)

## ok / warn（≥80%）/ paused（服務說已暫停，或 ≥100%）。
static func state(cost: float, budget: float, budget_hit: bool) -> String:
	if budget_hit or (budget > 0.0 and cost >= budget):
		return "paused"
	if budget > 0.0 and cost >= WARN_RATIO * budget:
		return "warn"
	return "ok"

## info：cost, today, month, budget（<0 無）, budget_hit, local, tokens, latency_s, ticks。
static func text_for(info: Dictionary) -> String:
	var parts: Array[String] = [TranslationServer.translate("UI_COST_MAIN") % [float(info.get("cost", 0.0)), float(info.get("today", 0.0)), float(info.get("month", 0.0))]]
	var budget := float(info.get("budget", -1.0))
	if budget >= 0.0:
		parts.append(TranslationServer.translate("UI_COST_BUDGET") % budget)
	if bool(info.get("local", false)):
		parts.append(TranslationServer.translate("UI_COST_LOCAL") % [int(info.get("tokens", 0)), float(info.get("latency_s", 0.0))])
	var st := state(float(info.get("cost", 0.0)), budget, bool(info.get("budget_hit", false)))
	if st == "paused":
		parts.append(TranslationServer.translate("UI_COST_PAUSED"))
	elif st == "warn":
		parts.append(TranslationServer.translate("UI_COST_WARN"))
	return "｜".join(parts)

func update(info: Dictionary) -> void:
	text = text_for(info)
	last_state = state(float(info.get("cost", 0.0)), float(info.get("budget", -1.0)), bool(info.get("budget_hit", false)))
	add_theme_color_override("font_color", {"ok": COLOR_OK, "warn": COLOR_WARN, "paused": COLOR_PAUSED}[last_state])
