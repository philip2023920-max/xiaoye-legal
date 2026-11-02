extends SceneTree
## 施工單 15 回歸守門（沙盒 CPU）：會戰規模（14 個排、126 人）每 tick 的邏輯成本要遠低於 60 Hz 的 16.7 ms 預算；
## 5 倍規模（630 人）也要在預算內。數字只做上限守門，絕對值以 docs/issues/15 記錄的實測為準。
##   godot --headless --path . -s tests/test_perf.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 3, 600.0)
	_run.call_deferred()

func measure(scale: int, seconds: float) -> Array:
	var bench = load("res://tools/bench.gd").new()
	var o: Orbat = bench.build(scale)
	var ticks := int(seconds * 60.0)
	var t0 := Time.get_ticks_usec()
	for i in ticks:
		o.advance(1.0 / 60.0)
	var avg := (Time.get_ticks_usec() - t0) / 1000.0 / ticks
	var soldiers := o.total_soldiers("us") + o.total_soldiers("enemy")
	o.queue_free()
	return [avg, soldiers]

func _run() -> void:
	var one := measure(1, 30.0)
	h.check(one[1] == 126 and one[0] < 8.0, "會戰規模 126 人：%.3f ms/tick（上限 8 ms，預算 16.7）" % one[0])
	var five := measure(5, 10.0)
	h.check(five[1] == 630 and five[0] < 16.7, "5 倍 630 人：%.3f ms/tick（上限 16.7 ms）" % five[0])
	h.check(five[0] < one[0] * 12.0, "成本大致線性（5 倍規模 < 12 倍成本）")
	h.finish()
