class_name Order
extends RefCounted
## 一條任務式命令（與 m0 的 Order 同欄位）：unit_id、task、target、reason、issuer（ai／player）。

const TASKS := ["seize", "hold", "flank", "withdraw", "support", "reserve"]
const TASK_ZH := {"seize": "奪取", "hold": "固守", "flank": "側翼包抄", "withdraw": "撤往", "support": "支援", "reserve": "預備於"}

var unit_id := ""
var task := ""
var target := ""
var reason := ""
var issuer := "ai"

static func make(unit_id_: String, task_: String, target_: String, issuer_: String = "ai", reason_: String = "") -> Order:
	var o := Order.new()
	o.unit_id = unit_id_
	o.task = task_
	o.target = target_
	o.issuer = issuer_
	o.reason = reason_
	return o

static func from_dict(d: Dictionary, issuer_: String = "ai") -> Order:
	return make(str(d.get("unit_id", "")), str(d.get("task", "")), str(d.get("target", "")), str(d.get("issuer", issuer_)), str(d.get("reason", "")))
