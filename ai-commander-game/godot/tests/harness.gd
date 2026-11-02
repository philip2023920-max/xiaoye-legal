class_name TestHarness
extends RefCounted
## 無頭測試共用：計數、守門、看門狗。每支 tests/*.gd 是獨立的 SceneTree 腳本，各自一個程序。

var tree: SceneTree
var expected := 0
var checks := 0
var failures := 0

func _init(tree_: SceneTree, expected_: int, watchdog_s: float = 90.0) -> void:
	tree = tree_
	expected = expected_
	tree.create_timer(watchdog_s).timeout.connect(func() -> void:
		printerr("逾時 %d 秒：測試可能被執行期錯誤打斷（看上面的 SCRIPT ERROR）" % int(watchdog_s))
		tree.quit(2))

func check(ok: bool, label: String) -> void:
	checks += 1
	if ok:
		print("  ok   ", label)
	else:
		failures += 1
		printerr("  FAIL ", label)

func approx(a: float, b: float, eps: float = 0.01) -> bool:
	return absf(a - b) <= eps

## 印總結並以正確的 exit code 結束。
func finish() -> void:
	print("checks: %d (expected %d), failures: %d" % [checks, expected, failures])
	tree.quit(0 if (failures == 0 and checks == expected) else 1)
