class_name AarScreen
extends PanelContainer
## 戰後 AAR 畫面（施工單 20，規則 docs/10 §11、§12）：戰報卡（勝負與星數、據點、推翻、費用、徽章、關鍵三幕、提示、參謀長一句話）
## → 討論（三個快速回覆＋輸入框，最多三回合）→ 準則提案（新增綠、刪除紅）→ 採納／跳過／撤銷 → 再打一場。
## 卡、徽章、討論、diff、採納、回歸、撤銷全在服務端（16 的 /battle/end 與 /aar/*）；這裡只是畫面：render(model) 把整個狀態畫出來，
## 按鈕只發訊號，服務呼叫在 Battle。純函式（文字、bbcode）無頭測試直接驗。

signal quick_reply(index: int)
signal text_sent(text: String)
signal propose_pressed
signal adopt_pressed
signal skip_pressed
signal undo_pressed
signal again_pressed

const BADGE_IDS := ["decisive", "hands_off", "thrifty_winner", "local_hero", "ground_holder"]
const COLOR_ADD := Color(0.55, 0.95, 0.55)
const COLOR_REMOVE := Color(1.0, 0.45, 0.45)
const TARGET_S := 120.0

## 文字進 bbcode 前把方括號換成全形：LLM 回覆、diff、玩家輸入裡的 [b]／[url] 不能改版面。
static func esc(t: String) -> String:
	return t.replace("[", "［").replace("]", "］")

var model := {}
var title_label: Label
var header_label: Label
var badges_label: Label
var hint_label: Label
var moments_label: RichTextLabel
var chief_line_label: Label
var discussion_label: RichTextLabel
var round_label: Label
var quick_buttons: Array[Button] = []
var input: LineEdit
var send_btn: Button
var propose_btn: Button
var skip_btn: Button
var diff_label: RichTextLabel
var adopt_btn: Button
var undo_btn: Button
var again_btn: Button
var result_label: Label
var timer_label: Label
var waiting_label: Label
var renders := 0

func _init() -> void:
	name = "AarScreen"
	UiText.load_csv()
	anchor_left = 0.04
	anchor_right = 0.64
	anchor_top = 0.05
	anchor_bottom = 0.95
	offset_left = 0.0
	offset_right = 0.0
	offset_top = 0.0
	offset_bottom = 0.0
	visible = false
	var bg := StyleBoxFlat.new()                                        # 不透明底：地圖與 HUD 不透出來
	bg.bg_color = Color(0.08, 0.09, 0.11, 0.97)
	bg.set_content_margin_all(12.0)
	add_theme_stylebox_override("panel", bg)
	var scroll := ScrollContainer.new()
	scroll.name = "Scroll"
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	var root := VBoxContainer.new()
	root.name = "Root"
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(root)
	title_label = _label(root, "Title", 26)
	header_label = _label(root, "Header")
	badges_label = _label(root, "Badges")
	hint_label = _label(root, "Hint")
	hint_label.add_theme_color_override("font_color", Color(1.0, 0.85, 0.5))
	_section(root, "UI_AAR_MOMENTS")
	moments_label = _rich(root, "Moments", 110.0)
	_section(root, "UI_AAR_CHIEF_LINE")
	chief_line_label = _label(root, "ChiefLine")
	round_label = _label(root, "Round")
	round_label.add_theme_color_override("font_color", Color(0.7, 0.85, 1.0))
	discussion_label = _rich(root, "Discussion", 110.0)
	var quick_row := HFlowContainer.new()                               # en 的三顆按鈕 814 px 會撐破面板：換行排
	quick_row.name = "Quick"
	root.add_child(quick_row)
	for i in 3:
		var b := _button(quick_row, "Quick%d" % (i + 1), "")
		b.pressed.connect(func() -> void: quick_reply.emit(i + 1))
		quick_buttons.append(b)
	var input_row := HBoxContainer.new()
	input_row.name = "Input"
	root.add_child(input_row)
	input = LineEdit.new()
	input.name = "Text"
	input.placeholder_text = tr("UI_AAR_INPUT_HINT")
	input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input.text_submitted.connect(func(t: String) -> void: _send())
	input_row.add_child(input)
	send_btn = _button(input_row, "Send", tr("UI_AAR_SEND"))
	send_btn.pressed.connect(_send)
	_section(root, "UI_AAR_DIFF")
	diff_label = _rich(root, "Diff", 90.0)
	var action_row := HFlowContainer.new()                              # 按鈕列放在提案「下面」：看完整提案才按採納
	action_row.name = "Actions"
	root.add_child(action_row)
	propose_btn = _button(action_row, "Propose", tr("UI_AAR_PROPOSE"))
	propose_btn.pressed.connect(func() -> void: propose_pressed.emit())
	adopt_btn = _button(action_row, "Adopt", tr("UI_AAR_ADOPT"))
	adopt_btn.pressed.connect(func() -> void: adopt_pressed.emit())
	skip_btn = _button(action_row, "Skip", tr("UI_AAR_SKIP"))
	skip_btn.pressed.connect(func() -> void: skip_pressed.emit())
	undo_btn = _button(action_row, "Undo", tr("UI_AAR_UNDO"))
	undo_btn.pressed.connect(func() -> void: undo_pressed.emit())
	again_btn = _button(action_row, "Again", tr("UI_AAR_AGAIN"))
	again_btn.pressed.connect(func() -> void: again_pressed.emit())
	result_label = _label(root, "Result")
	result_label.add_theme_color_override("font_color", Color(0.55, 0.95, 0.55))
	waiting_label = _label(root, "Waiting")
	waiting_label.add_theme_color_override("font_color", Color(1.0, 0.93, 0.6))
	timer_label = _label(root, "Timer")

func _label(parent: Control, n: String, size: int = 0) -> Label:
	var l := Label.new()
	l.name = n
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if size > 0:
		l.add_theme_font_size_override("font_size", size)
	parent.add_child(l)
	return l

func _section(parent: Control, key: String) -> void:
	var l := Label.new()
	l.text = "— %s —" % tr(key)
	l.add_theme_color_override("font_color", Color(0.7, 0.85, 1.0))
	parent.add_child(l)

func _rich(parent: Control, n: String, min_h: float) -> RichTextLabel:
	var r := RichTextLabel.new()
	r.name = n
	r.bbcode_enabled = true
	r.fit_content = true
	r.custom_minimum_size = Vector2(0.0, min_h)
	r.focus_mode = Control.FOCUS_NONE
	parent.add_child(r)
	return r

func _button(parent: Control, n: String, text: String) -> Button:
	var b := Button.new()
	b.name = n
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	parent.add_child(b)
	return b

func _send() -> void:
	if send_btn.disabled or not input.editable:                         # 等回覆時 Enter 也不送（不然一次吃掉兩回合）
		return
	var t := input.text.strip_edges()
	if t == "":
		return
	input.text = ""
	text_sent.emit(t)

# ---- 純函式 ----
static func stars(winner: String) -> String:
	return {"us": "★★★", "draw": "★★☆", "enemy": "★☆☆"}.get(winner, "☆☆☆")

static func result_text(winner: String) -> String:
	return TranslationServer.translate("UI_AAR_RESULT_" + winner)

static func header_text(card: Dictionary, seconds: int = -1) -> String:
	var score: Array = card.get("score", [0, 0])
	var end_key := "UI_AAR_END_" + str(card.get("end_reason", "turns"))
	var end_txt := TranslationServer.translate(end_key)
	if end_txt == end_key:
		end_txt = str(card.get("end_reason", ""))
	var secs := seconds if seconds >= 0 else int(card.get("turns", 0)) * 30
	return TranslationServer.translate("UI_AAR_HEADER") % [result_text(str(card.get("winner", "draw"))), stars(str(card.get("winner", "draw"))), secs, end_txt,
		int(score[0]) if score.size() > 0 else 0, int(score[1]) if score.size() > 1 else 0, int(card.get("overrides", 0)), str(card.get("override_rate", "")),
		float(card.get("cost_usd", 0.0)), str(card.get("provider", "")), str(card.get("model", ""))]

static func badge_names(ids: Array) -> String:
	if ids.is_empty():
		return TranslationServer.translate("UI_AAR_NO_BADGES")
	var names: Array[String] = []
	for b in ids:
		var key := "UI_BADGE_" + str(b)
		var t := TranslationServer.translate(key)
		names.append(str(b) if t == key else t)
	return TranslationServer.translate("UI_AAR_BADGES") % "、".join(names)

static func moments_bbcode(moments: Array) -> String:
	if moments.is_empty():
		return TranslationServer.translate("UI_AAR_NO_MOMENTS")
	var lines: Array[String] = []
	for m in moments:
		var idx := int(m.get("index", 0))
		var t := int(m.get("t", 0))
		if str(m.get("kind", "")) == "override":
			var outcome := str(m.get("outcome", ""))
			var col := "#8cf28c" if outcome == "👍" else ("#ff7373" if outcome == "👎" else "#d9d9d9")
			lines.append("[color=%s]%s[/color]" % [col, esc(TranslationServer.translate("UI_AAR_MOMENT_OVERRIDE") % [idx, t, str(m.get("note", "")), str(m.get("ai_text", "")), str(m.get("player_text", "")), outcome if outcome != "" else "…"])])
		else:
			lines.append(esc(TranslationServer.translate("UI_AAR_MOMENT_TURNING") % [idx, t, str(m.get("note", ""))]))
	return "\n".join(lines)

static func diff_bbcode(diff: Variant) -> String:
	if diff == null or not (diff is Dictionary):
		return ""
	var d: Dictionary = diff
	var lines: Array[String] = []
	if str(d.get("summary", "")) != "":
		lines.append(esc(TranslationServer.translate("UI_AAR_DIFF_SUMMARY") % str(d["summary"])))
	for a in d.get("add", []):
		lines.append("[color=#%s]%s[/color]" % [COLOR_ADD.to_html(false), esc(TranslationServer.translate("UI_AAR_ADD") % [str(a.get("text", "")), str(a.get("section", ""))])])
	for r in d.get("remove", []):
		lines.append("[color=#%s]%s[/color]" % [COLOR_REMOVE.to_html(false), esc(TranslationServer.translate("UI_AAR_REMOVE") % str(r))])
	if d.get("add", []).is_empty() and d.get("remove", []).is_empty():
		lines.append(TranslationServer.translate("UI_AAR_EMPTY_DIFF"))
	return "\n".join(lines)

static func transcript_bbcode(transcript: Array) -> String:
	var lines: Array[String] = []
	for m in transcript:
		var who := TranslationServer.translate("UI_AAR_YOU") if str(m.get("role", "")) == "user" else TranslationServer.translate("UI_SECTION_CHIEF")
		lines.append("[b]%s[/b]：%s" % [who, esc(str(m.get("content", "")))])
	return "\n".join(lines)

## model：card{}, seconds, unjudged, chief_line, transcript[], round（下一回合編號，4＝討論結束）, next_quick[], diff（null 或 {}）,
## phase（card／proposed／adopted／skipped／undone）, messages[], rolled_back, busy, duration_s, error。
func render(m: Dictionary) -> void:
	model = m
	renders += 1
	visible = true
	var card: Dictionary = m.get("card", {})
	var phase := str(m.get("phase", "card"))
	var busy := bool(m.get("busy", false))
	title_label.text = tr("UI_AAR_TITLE")
	header_label.text = header_text(card, int(m.get("seconds", -1)))
	if int(m.get("unjudged", 0)) > 0:
		header_label.text += "｜" + tr("UI_AAR_UNJUDGED") % int(m["unjudged"])
	badges_label.text = badge_names(card.get("badges", []))
	hint_label.text = (tr("UI_AAR_HINT") % str(card["hint"])) if str(card.get("hint", "")) != "" else ""
	hint_label.visible = hint_label.text != ""
	moments_label.text = moments_bbcode(card.get("moments", []))
	chief_line_label.text = str(m.get("chief_line", "")) if str(m.get("chief_line", "")) != "" else tr("UI_AAR_WAITING_LINE")
	var rnd := int(m.get("round", 1))
	var discussing := phase == "card" and rnd <= 3
	round_label.text = tr("UI_AAR_DISCUSS") % mini(rnd, 3) if phase == "card" else tr("UI_AAR_DISCUSS_DONE")
	discussion_label.text = transcript_bbcode(m.get("transcript", []))
	discussion_label.visible = not m.get("transcript", []).is_empty()
	var quick: Array = m.get("next_quick", [])
	for i in 3:
		var b := quick_buttons[i]
		b.visible = discussing and i < quick.size()
		b.text = str(quick[i]) if i < quick.size() else ""
		b.disabled = busy
	input.visible = discussing
	input.editable = not busy
	send_btn.visible = discussing
	send_btn.disabled = busy
	propose_btn.visible = phase == "card"
	propose_btn.disabled = busy
	adopt_btn.visible = phase == "proposed" and m.get("diff") != null and not bool(m["diff"].get("empty", false))
	adopt_btn.disabled = busy
	skip_btn.visible = phase in ["card", "proposed"]
	skip_btn.disabled = busy
	undo_btn.visible = phase == "adopted" and bool(m.get("adopted", true)) and not bool(m.get("rolled_back", false))   # 回滾過＝沒有上一版可撤
	undo_btn.disabled = busy
	again_btn.visible = phase in ["adopted", "skipped", "undone"]
	again_btn.disabled = busy
	diff_label.text = diff_bbcode(m.get("diff"))
	diff_label.visible = diff_label.text != ""
	var results: Array[String] = []
	match phase:
		"adopted":
			results.append(tr("UI_AAR_ROLLED_BACK") if bool(m.get("rolled_back", false)) else (tr("UI_AAR_ADOPTED") if bool(m.get("adopted", true)) else tr("UI_AAR_EMPTY_DIFF")))
		"skipped":
			results.append(tr("UI_AAR_SKIPPED"))
		"undone":
			results.append(tr("UI_AAR_UNDONE"))
	for msg in m.get("messages", []):
		results.append(str(msg))
	if str(m.get("error", "")) != "":
		results.append(str(m["error"]))
	result_label.text = "\n".join(results)
	result_label.visible = result_label.text != ""
	waiting_label.text = tr("UI_AAR_WAITING") if busy else ""
	waiting_label.visible = busy
	set_duration(float(m.get("duration_s", 0.0)), float(m.get("service_duration_s", -1.0)))

## service_s ≥ 0 時以服務記的為準（aar.json 的 duration_s，從第一次互動起算；與 chief stats 一致）。
func set_duration(s: float, service_s: float = -1.0) -> void:
	var shown := service_s if service_s >= 0.0 else s
	timer_label.text = tr("UI_AAR_TIMER") % [int(shown), int(TARGET_S)]
	timer_label.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85) if shown < TARGET_S else Color(1.0, 0.6, 0.6))
