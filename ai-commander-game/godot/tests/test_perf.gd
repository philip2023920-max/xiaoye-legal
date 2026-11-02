extends SceneTree
## 施工單 15 回歸守門（沙盒 CPU）：會戰規模（14 個排、126 人）每 tick 的邏輯成本要遠低於 60 Hz 的 16.7 ms 預算；
## 5 倍規模（630 人）也要在預算內。數字只做上限守門，絕對值以 docs/issues/15 記錄的實測為準。含每秒戰情板更新。
##   godot --headless --path . -s tests/test_perf.gd

const Bench := preload("res://tools/bench.gd")

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 3, 600.0)
	_run.call_deferred()

func measure(scale: int, seconds: float) -> Dictionary:
	var built := Bench.build(get_root(), scale)
	var o: Orbat = built[0]
	var r := Bench.measure(o, int(seconds * 60.0))
	o.queue_free()
	built[1].queue_free()
	return r

func _run() -> void:
	var one := measure(1, 30.0)
	h.check(one["soldiers"] == 126 and one["avg"] < 8.0, "會戰規模 126 人：平均 %.3f、p99 %.3f ms/tick（上限 8 ms，預算 16.7）" % [one["avg"], one["p99"]])
	var five := measure(5, 10.0)
	h.check(five["soldiers"] == 630 and five["avg"] < 16.7, "5 倍 630 人：平均 %.3f、p99 %.3f ms/tick（上限 16.7 ms）" % [five["avg"], five["p99"]])
	h.check(five["avg"] < one["avg"] * 12.0, "成本大致線性（5 倍規模 < 12 倍成本）")
	await process_frame
	h.finish()
