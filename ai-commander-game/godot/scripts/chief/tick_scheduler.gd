class_name TickScheduler
extends RefCounted
## 參謀長節拍（施工單 17，ADR-0015 D24）：t=0 立即一次，之後每 20 秒；接觸／易手／潰散／殲滅事件可提前觸發，
## 但與上次送出至少隔 8 秒。同時只允許一個請求在飛；在飛期間到期的節拍不會丟，回覆一到、下一次 due() 就補送（用最新的板）。
## 純邏輯、不碰節點，方便無頭測試。

const INTERVAL := 20.0
const MIN_GAP := 8.0
const EVENT_KINDS := ["contact", "seized", "routed", "destroyed"]

var last_sent := -1.0          # 上次送出 tick 的遊戲秒（<0＝還沒送過）
var in_flight := false
var event_pending := false     # 有觸發事件還沒被任何一拍帶走
var ticks_sent := 0
var _events_seen := 0          # orbat.events 已掃過的長度（事件只會追加）

## 每個物理 tick 問一次：現在該送嗎？會把新事件掃進來。
func due(sec: float, events: Array) -> bool:
	while _events_seen < events.size():
		var ev: Dictionary = events[_events_seen]
		_events_seen += 1
		if str(ev.get("kind", "")) in EVENT_KINDS:
			event_pending = true
	if in_flight:
		return false
	if last_sent < 0.0:
		return true
	if sec - last_sent >= INTERVAL - 1e-6:
		return true
	return event_pending and sec - last_sent >= MIN_GAP - 1e-6

func mark_sent(sec: float) -> void:
	last_sent = sec
	in_flight = true
	event_pending = false
	ticks_sent += 1

func mark_done() -> void:
	in_flight = false

## 下一個規律節拍的遊戲秒（HUD 顯示用）。
func next_regular() -> float:
	return 0.0 if last_sent < 0.0 else last_sent + INTERVAL
