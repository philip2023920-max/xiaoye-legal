extends SceneTree
## 施工單 19：推翻／接管。狀態機（OverrideFlow）、面板文字與按鈕狀態、Battle 的接管（含連的子排）／放手／環的顏色／事件，
## 以及跨程序：真的啟動 chief serve（fake）→ /override 算一次、已直轄再改令不算、/release 後再接管又算、推翻率進側欄。
##   godot --headless --path . -s tests/test_override.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 45, 300.0)
	_run.call_deferred()

func make_battle(scene: PackedScene) -> Battle:
	var battle: Battle = scene.instantiate()
	battle.auto_advance = false
	battle.use_cmdline_args = false
	battle.board_out = ""
	battle.snapshot_dir = ""
	battle.chief_autostart = false
	battle.friendly_path = ""
	get_root().add_child(battle)
	return battle

func _run() -> void:
	UiText.load_csv()
	UiText.set_lang("zh-TW")
	# ---- 1. 狀態機 ----
	var f := OverrideFlow.new()
	var states: Array = []
	f.changed.connect(func(st: String) -> void: states.append(st))
	h.check(f.state == "idle" and not f.choose_task("hold") and f.take_order() == null, "idle：不能選任務、沒有命令")
	f.select("plt-A3")
	h.check(f.state == "selected" and f.unit_id == "plt-A3" and not f.pick_sector("B1"), "選單位 → selected；還沒選任務不能點地圖")
	h.check(f.choose_task("hold") and f.state == "picking_sector" and not f.choose_task("charge"), "選任務 → picking_sector；非六種任務不收")
	h.check(not f.pick_unit("plt-A1") and f.pick_sector("B1") and f.state == "ready" and f.target == "B1", "picking_sector 只收分區")
	var o := f.take_order()
	h.check(o != null and o.unit_id == "plt-A3" and o.task == "hold" and o.target == "B1" and o.issuer == "player" and f.state == "selected" and f.task == "", "拿走命令：issuer=player，回到 selected")
	f.choose_task("support")
	h.check(f.state == "picking_unit" and not f.pick_unit("plt-A3") and not f.pick_sector("B1") and f.pick_unit("plt-A1") and f.state == "ready", "support → picking_unit；不能支援自己、不能點分區")
	f.cancel()
	h.check(f.state == "selected" and f.task == "" and f.target == "" and f.is_picking() == false, "取消回 selected")
	f.choose_task("seize"); f.clear()
	h.check(f.state == "idle" and f.unit_id == "" and states.size() >= 9, "clear 回 idle；每次變化都發 changed")

	# ---- 2. 面板 ----
	var p := OverridePanel.new()
	get_root().add_child(p)
	h.check(not p.visible and p.task_buttons.size() == 6 and p.task_buttons["seize"].text == "奪取", "面板預設隱藏、六個任務鈕三語")
	p.show_unit({"id": "plt-A3", "name": "A3 步兵排", "echelon": "platoon", "task": {"type": "seize", "target": "C3"}, "controlled_by": "ai", "state": "moving"}, "selected")
	h.check(p.visible and p.title_label.text == "A3 步兵排（參謀長指揮）" and p.task_label.text == "目前任務：奪取 C3" and not p.takeover_btn.disabled and p.release_btn.disabled and not p.cancel_btn.visible, "參謀長指揮的單位：可接管、不可放手")
	p.show_unit({"id": "plt-A3", "name": "A3 步兵排", "echelon": "platoon", "task": {}, "controlled_by": "player", "state": "idle"}, "picking_sector", "hold")
	h.check(p.title_label.text == "A3 步兵排（直轄中）" and p.task_label.text == "目前任務：—" and p.hint_label.text.begins_with("「固守」→ 點地圖") and p.takeover_btn.disabled and not p.release_btn.disabled and p.cancel_btn.visible, "直轄中＋選目標：提示、可放手、取消鈕")
	var pressed: Array = []
	p.task_pressed.connect(func(t: String) -> void: pressed.append(t))
	p.task_buttons["flank"].pressed.emit()
	h.check(pressed == ["flank"], "任務鈕 → task_pressed")
	p.hide_panel()
	h.check(not p.visible and p.shown_unit == "", "hide_panel")
	p.queue_free()

	# ---- 3. Battle：接管／放手／環／事件（沒有服務） ----
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var b := make_battle(scene)
	await process_frame
	await physics_frame
	await physics_frame
	var a3: Platoon = b.orbat.platoons["plt-A3"]
	h.check(b.panel != null and not b.panel.visible and a3.ring != null and not a3.ring.visible, "開局：面板隱藏、參謀長指揮的排沒有環")
	b.select_unit("plt-A3")
	h.check(b.flow.state == "selected" and b.panel.visible and b.panel.shown_unit == "plt-A3" and a3.selected and a3.ring.visible and a3.ring_color() == Platoon.RING_COLORS["selected"], "點排：選取、面板出現、白環")
	b._on_panel_task("hold")
	h.check(b.flow.state == "picking_sector" and b.panel.hint_label.text.contains("固守"), "面板選固守 → 等點地圖")
	b.flow.pick_sector("B1")
	b._execute_flow()
	h.check(a3.controlled_by == "player" and a3.task == {"type": "hold", "target": "B1"} and a3.ring_color() == Platoon.RING_COLORS["both"] and b.flow.state == "selected", "點 B1 → 直轄、任務固守 B1、亮金環、流程回 selected")
	var ev := b.orbat.events.filter(func(e: Dictionary) -> bool: return e["kind"] == "override")
	h.check(ev.size() == 1 and ev[0]["text"] == "總司令接管 A3 步兵排，改為 固守 B1" and ev[0]["unit"] == "plt-A3" and ev[0]["sector"] == "B1", "事件流：%s" % ev[0]["text"])
	h.check(not b.commander_override("plt-A3", "seize", "Z9") and b.orbat.events.back()["text"].begins_with("總司令的命令被引擎退回"), "壞目標：引擎退回、不改狀態")
	b.select_unit("")
	h.check(not a3.selected and a3.ring_color() == Platoon.RING_COLORS["player"] and not b.panel.visible, "取消選取：直轄的排留金環、面板關")
	# 連：接管含所有子排；參謀長的連令不碰直轄排
	h.check(b.commander_override("co-A", "seize", "C3") and b.orbat.companies["co-A"]["controlled_by"] == "player" and b.orbat.leaves("us").all(func(pl: Platoon) -> bool: return pl.controlled_by == "player"), "接管連 → 連同所有子排直轄")
	h.check(b._is_player_controlled("co-A") and b._is_player_controlled("plt-A5") and b._subtree("co-A").size() == 1 + b.orbat.children_of("co-A").size(), "子樹＝連＋子排")
	h.check(b.commander_release("plt-A5") and b.orbat.platoons["plt-A5"].controlled_by == "ai" and not b.orbat.platoons["plt-A5"].ring.visible and b.orbat.events.back()["text"] == "總司令放手 A5 迫砲排，交回參謀長", "放手一個排：交回參謀長、環消失、事件")
	h.check(b.commander_release("co-A") and b.orbat.companies["co-A"]["controlled_by"] == "ai" and b.orbat.leaves("us").all(func(pl: Platoon) -> bool: return pl.controlled_by == "ai") and not b.commander_release("co-A"), "放手連 → 全部交回；再放手一次回 false")
	h.check(b.commander_override("co-A", "seize", "C3") and b.commander_release("plt-A4") and b.orbat.companies["co-A"]["controlled_by"] == "ai" and b.orbat.platoons["plt-A3"].controlled_by == "player" and b.orbat.platoons["plt-A4"].controlled_by == "ai", "放手連底下一個排 → 連不再整個直轄，其他排仍直轄（§9）")
	b.commander_release("co-A")
	for pl in b.orbat.leaves("us"):
		b.commander_release(pl.id)
	# V6：潰散只能撤退（引擎與面板）
	b.orbat.platoons["plt-A6"].state = "routed"
	h.check(not b.commander_override("plt-A6", "hold", "B2") and b.orbat.platoons["plt-A6"].controlled_by == "ai" and b.orbat.events.back()["text"].contains("潰散中") and b.commander_override("plt-A6", "withdraw", "A1"), "潰散排：固守被退回、撤退可以")
	b.select_unit("plt-A6")
	h.check(b.panel.task_buttons["hold"].disabled and not b.panel.task_buttons["withdraw"].disabled, "面板：潰散排只開「撤退」")
	b.commander_release("plt-A6")
	b.orbat.platoons["plt-A6"].state = "idle"
	b.select_unit("")
	# 連不能支援自己的子排；殲滅的排接管回 false
	b.select_unit("co-A"); b._on_panel_task("support")
	b.flow.pick_unit("plt-A1") if not ("plt-A1" in b._subtree("co-A")) else null
	h.check(b.flow.state == "picking_unit" and "plt-A1" in b._subtree("co-A"), "連選支援時子排不是合法目標（_left_click 會擋）")
	b.flow.cancel(); b.select_unit("")
	b.orbat.platoons["plt-A7"].state = "destroyed"; b.orbat.platoons["plt-A7"].task = {}; b.orbat.platoons["plt-A7"].sector = ""
	h.check(not b.commander_takeover("plt-A7"), "殲滅且無分區的排：接管回 false、不捏造目標")
	b.orbat.platoons["plt-A7"].state = "idle"
	h.check(b.pick_radius_px(b.orbat.platoons["plt-A1"].anchor) >= Battle.PICK_RADIUS_PX, "挑排半徑至少 28 px、放大時放寬")
	b.director.finished = true
	h.check(not b.commander_override("plt-A2", "hold", "B2"), "會戰結束後不再接管")
	b.director.finished = false
	h.check(b.commander_takeover("plt-A2") and b.orbat.platoons["plt-A2"].controlled_by == "player" and b.orbat.platoons["plt-A2"].task == {"type": "seize", "target": "C3"}, "「接管」照目前任務直轄（A2 原本 seize C3）")
	b.orbat.platoons["plt-A1"].task = {}
	h.check(b.commander_takeover("plt-A1") and b.orbat.platoons["plt-A1"].task["type"] == "hold" and b.orbat.platoons["plt-A1"].task["target"] == b.orbat.platoons["plt-A1"].sector, "沒任務的單位接管＝固守所在分區")
	# 側欄點樹 → 選取＋面板
	b.sidebar.select_unit("plt-A4")
	h.check(b.flow.unit_id == "plt-A4" and b.panel.shown_unit == "plt-A4", "側欄點樹 → 選取與面板")
	h.check(b.platoon_at_screen(Vector2(-9999, -9999)) == "", "螢幕外沒有排可點")
	b.queue_free()
	await process_frame

	# ---- 4. 跨程序：/override 與 /release ----
	var out_dir := ProjectSettings.globalize_path("user://override_test")
	var b2 := make_battle(scene)
	b2.chief_provider = "fake"
	b2.chief_extra = PackedStringArray(["--out-root", out_dir, "--ledger", "none"])
	await process_frame
	await physics_frame
	await physics_frame
	var started: bool = await b2.start_chief()
	h.check(started, "服務上線")
	b2.director.tick(1.0 / 60.0)
	b2.chief_update()                                         # 第 1 拍：參謀長對 A1～A3 下令
	while b2.chief.busy or b2.scheduler.in_flight:
		await process_frame
	h.check(b2.chief_ticks == 1 and b2.orbat.platoons["plt-A1"].task == {"type": "seize", "target": "C3"}, "第 1 拍參謀長令套用（A1 奪取 C3）")
	h.check(b2.commander_override("plt-A1", "hold", "B2"), "總司令改 A1 固守 B2")
	while b2.chief.busy:
		await process_frame
	var r1: Dictionary = b2.last_override
	h.check(r1["code"] == 200 and r1["body"]["counted"] == true and r1["body"]["recorded"] == 1 and r1["body"]["ai_order"]["task"] == "seize" and r1["body"]["player_order"] == {"task": "hold", "target": "B2"}, "/override：算一次、ai_order＝參謀長的 seize C3")
	h.check(b2.override_rate == "1/3" and b2.orbat.overrides_this_battle == 1 and b2.orbat.events.back()["text"] == "推翻已記錄（第 1 次，推翻率 1/3）", "推翻率 1/3、板上 overrides_this_battle=1、事件")
	b2.commander_override("plt-A1", "seize", "C3")
	while b2.chief.busy:
		await process_frame
	h.check(b2.last_override["body"]["counted"] == false and b2.orbat.overrides_this_battle == 1 and b2.orbat.events.back()["text"] == "已直轄單位改令，不算推翻", "已直轄再改令：不算")
	b2.commander_release("plt-A1")
	while b2.chief.busy:
		await process_frame
	b2.commander_override("plt-A1", "hold", "B2")
	while b2.chief.busy:
		await process_frame
	h.check(b2.last_override["body"]["counted"] == true and b2.last_override["body"]["recorded"] == 2 and b2.orbat.overrides_this_battle == 2, "放手後再接管：又算一次（/release 生效）")
	b2._set_controlled("plt-A3", "player")
	b2._send_override("plt-A3", {"task": "charge", "target": "B2"})     # 服務退回（400）→ 收回直轄
	while b2.chief.busy:
		await process_frame
	h.check(b2.last_override["code"] == 400 and b2.orbat.platoons["plt-A3"].controlled_by == "ai" and b2.orbat.events.back()["text"].begins_with("推翻沒記錄到，已收回直轄"), "服務退回的命令：收回直轄並寫明原因")
	b2.sidebar.refresh(b2.writer.to_dict(), b2.chief_sidebar_info())
	h.check(b2.sidebar.chief_label.text.contains("推翻率 2/3"), "側欄參謀長區顯示推翻率")
	# 參謀長下一拍的連令不碰直轄排（服務端 V2 擋 + 客戶端保險）
	b2.orbat.platoons["plt-A1"].task = {"type": "hold", "target": "B2"}
	for i in 60 * 20:
		b2.director.tick(1.0 / 60.0)
	b2.chief_update()
	while b2.chief.busy or b2.scheduler.in_flight:
		await process_frame
	h.check(b2.chief_ticks == 2 and b2.orbat.platoons["plt-A1"].controlled_by == "player" and b2.orbat.platoons["plt-A1"].task == {"type": "hold", "target": "B2"} and b2.orbat.platoons["plt-A2"].task == {"type": "hold", "target": "C3"}, "第 2 拍 co-A 固守 C3：A2 跟著改、直轄的 A1 不動")
	await b2.chief.stop()
	b2.queue_free()
	await process_frame
	h.finish()
