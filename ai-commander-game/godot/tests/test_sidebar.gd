extends SceneTree
## 施工單 18：側欄從 BoardWriter 的字典建樹（節點數、文字、直轄標記、殲滅移除）、事件上色、三語字串表、
## 參謀長區文字、收合、點樹 → 攝影機移動；Battle 場景裡的側欄跟著板更新。
##   godot --headless --path . -s tests/test_sidebar.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 44, 120.0)
	_run.call_deferred()

func sample_board() -> Dictionary:
	var b: Dictionary = BoardIO.load_board("m0://samples/godot_board_sample.json")
	return b

func _run() -> void:
	get_root().size = Vector2i(1280, 720)        # 無頭預設 64×64；版面要用真的視窗大小量
	# ---- 字串表 ----
	var n := UiText.load_csv()
	h.check(n >= 40 and UiText.keys.has("UI_SECTION_UNITS") and UiText.load_csv() == n, "ui.csv 載入 %d 個鍵，重複載入不重複加" % n)
	UiText.set_lang("zh-TW")
	h.check(TranslationServer.translate("UI_SECTION_UNITS") == "部隊" and TranslationServer.translate("UI_TASK_seize") == "奪取", "zh-TW")
	UiText.set_lang("zh-CN")
	h.check(TranslationServer.translate("UI_SECTION_UNITS") == "部队" and TranslationServer.translate("UI_TASK_seize") == "夺取", "zh-CN")
	UiText.set_lang("en")
	h.check(TranslationServer.translate("UI_SECTION_UNITS") == "Units" and TranslationServer.translate("UI_SCORE") % [8, 3] == "Us 8 : Enemy 3", "en 與格式化")
	var row := UiText._split_csv('a,"b,c","d""e",f')
	h.check(row.size() == 4 and row[1] == "b,c" and row[2] == 'd"e', "CSV 引號欄位")
	# 三欄都齊：每個鍵三種語言都有翻譯（不是鍵本身）
	var missing := 0
	for k in UiText.keys:
		for lang in ["zh_TW", "zh_CN", "en"]:
			TranslationServer.set_locale(lang)
			if TranslationServer.translate(k) == k:
				missing += 1
	h.check(missing == 0, "每個鍵三語齊全（缺 %d）" % missing)
	UiText.set_lang("zh-TW")

	# ---- 純函式 ----
	var board := sample_board()
	var rows := Sidebar.tree_rows(board)
	var companies := rows.filter(func(r: Dictionary) -> bool: return r["echelon"] == "company")
	var platoons := rows.filter(func(r: Dictionary) -> bool: return r["echelon"] == "platoon")
	h.check(rows.size() == board["orbat"].size() and companies.size() == 1 and platoons.size() == rows.size() - 1 and platoons[0]["parent"] == "co-A", "tree_rows：連 %d、排 %d、排掛在連底下" % [companies.size(), platoons.size()])
	h.check(Sidebar.strength_bar(0.8) == "████░ 0.80" and Sidebar.strength_bar(0.0) == "░░░░░ 0.00" and Sidebar.strength_bar(1.0) == "█████ 1.00", "戰力條")
	h.check(Sidebar.task_text({"type": "seize", "target": "C3"}) == "奪取 C3" and Sidebar.task_text({}) == "—" and Sidebar.task_text({"type": "nuke", "target": "C3"}) == "nuke C3" and Sidebar.state_text("routed") == "潰散" and Sidebar.state_text("weird") == "weird", "任務／狀態文字（未知任務不漏鍵名）")
	h.check(Sidebar.event_color({"kind": "info", "text": "推翻後果：t1 plt-A1 hold B2 → 👍"}) == Sidebar.COLOR_GOOD and Sidebar.event_color({"kind": "info", "text": "… → 👎"}) == Sidebar.COLOR_BAD and Sidebar.event_color({"kind": "info", "text": "… → ➖"}) == Sidebar.COLOR_NEUTRAL, "推翻後果 👍綠 👎紅 ➖灰")
	h.check(Sidebar.event_color({"kind": "order", "text": "參謀長令 …"}) == Sidebar.COLOR_ORDER and Sidebar.event_color({"kind": "seized", "text": ""}) == Sidebar.COLOR_SEIZED and Sidebar.event_color({"kind": "routed", "text": ""}) == Sidebar.COLOR_BAD and Sidebar.event_color({"kind": "weather", "text": ""}) == Sidebar.COLOR_WEATHER and Sidebar.event_color({"kind": "info", "text": "x"}) == Sidebar.COLOR_INFO, "其他事件上色")
	var evs: Array = []
	for i in 20:
		evs.append({"t": i, "kind": "info", "text": "e[%d]" % i})
	var bb := Sidebar.events_bbcode(evs)
	h.check(bb.split("\n").size() == 12 and bb.contains("19s e［19］") and not bb.contains("]7s e") and bb.begins_with("[color=#"), "事件流最近 12 筆、舊→新、方括號跳脫")
	h.check(Sidebar.events_bbcode([]) == "（還沒有事件）", "沒有事件的文字")
	var ot := Sidebar.objectives_text(board)
	h.check(ot.begins_with("我 8：敵 3") and ot.contains("O1（3 分，B2）✔") and ot.contains("O2（5 分，C3）✔") and ot.contains("O3（3 分，D4）✘") and ot.split("\n").size() == 2, "據點與分數（兩行）：%s" % ot.split("\n")[0])
	var ct := Sidebar.conditions_text(board)
	h.check(ct == "晴｜日間｜t=120 秒｜剩 180 秒" and Sidebar.conditions_text(board, 600).ends_with("剩 480 秒"), "天氣／時段／時間：%s（會戰長度可傳入）" % ct)
	h.check(Sidebar.chief_text({"state": "off"}) == "參謀長離線（劇本／空白鍵）" and Sidebar.chief_text({"state": "starting"}) == "參謀長服務啟動中…", "參謀長區：離線／啟動中")
	var ctext := Sidebar.chief_text({"state": "online", "line": "參謀長：先搶城鎮", "busy_s": 3.2, "orders": ["plt-A1 奪取 C3"]})
	h.check(Array(ctext.split("\n")) == ["參謀長：先搶城鎮", "參謀長思考中 3 秒…", "最近命令：plt-A1 奪取 C3"], "參謀長區：研判／思考中／最近命令（同一行）")
	h.check(Sidebar.chief_text({"state": "online", "line": "x", "orders": []}).ends_with("（還沒有命令）"), "參謀長區：還沒有命令")

	# ---- 節點：建樹、更新、直轄、殲滅移除、收合、選取 ----
	var sb := Sidebar.new()
	get_root().add_child(sb)
	sb.refresh(board, {"state": "online", "line": "參謀長：就位", "cost": 0.0123, "ticks": 4})
	h.check(sb.unit_count() == board["orbat"].size() and sb.tree.get_root().get_child_count() == 1 and sb.tree.get_root().get_child(0).get_child_count() == board["orbat"].size() - 1, "樹：1 個連、%d 個排掛在底下" % (board["orbat"].size() - 1))
	var a1: TreeItem = sb._items["plt-A1"]
	h.check(a1.get_text(0) == "A1 步兵排" and a1.get_text(1) == Sidebar.strength_bar(0.93) and a1.get_text(3) == "奪取 C3", "排的欄位：%s｜%s｜%s" % [a1.get_text(0), a1.get_text(1), a1.get_text(3)])
	h.check(sb.cost_label.text == "$0.0123｜第 4 拍" and sb.conditions_label.text.ends_with("｜$0.0123｜第 4 拍") and sb.chief_label.text.begins_with("參謀長：就位") and sb.events_label.text != "", "費用併在天氣行／參謀長／事件區有字")
	var b2 := sample_board()
	for u in b2["orbat"]:
		if u["id"] == "plt-A1":
			u["controlled_by"] = "player"
		if u["id"] == "plt-A2":
			u["state"] = "routed"
			u["strength"] = 0.2
	b2["orbat"] = b2["orbat"].filter(func(u: Dictionary) -> bool: return u["id"] != "plt-A5")   # A5 殲滅後不在板上
	b2["events"].append({"t": 125, "kind": "info", "text": "推翻後果：t1 plt-A1 hold B2 → 👍"})
	sb.refresh(b2, {"state": "online", "line": "參謀長：守住", "busy_s": 2.0, "orders": ["co-A 固守 C3"], "cost": 0.02, "ticks": 5, "ended": false})
	h.check(sb.unit_count() == b2["orbat"].size() and not sb._items.has("plt-A5") and sb._items["plt-A1"] == a1, "更新：板上消失的單位移除、既有 item 不重建")
	# 版面：1280×720、參謀長上線＋兩行研判＋三條命令（M2 常態）→ 內容裝進捲動區、樹至少 5 列高
	await process_frame
	await process_frame
	var body_h := sb.body.get_combined_minimum_size().y
	h.check(sb.get_global_rect() == Rect2(840.0, 0.0, 440.0, 720.0) and body_h <= sb.scroll.size.y and sb.scroll.horizontal_scroll_mode == ScrollContainer.SCROLL_MODE_DISABLED, "側欄 (840,0,440,720)；內容最小高 %d ≤ 捲動區 %d" % [int(body_h), int(sb.scroll.size.y)])
	h.check(sb.tree.size.y >= 200.0 and sb.tree.size.y > sb.events_label.size.y, "樹 %d px（≥ 5 列、比事件流高）" % int(sb.tree.size.y))
	h.check(sb.tree.get_column_width(0) >= 130 and sb.tree.get_column_width(1) >= 98, "名稱欄 %d px（放得下「A1 步兵排 ★直轄」）、戰力欄 %d px" % [sb.tree.get_column_width(0), sb.tree.get_column_width(1)])
	sb.toggle()
	await process_frame
	h.check(sb.collapsed and sb.get_global_rect().size.y < 100.0 and sb.get_global_rect().position.x > 1100.0, "收合後只剩按鈕那塊（%s），不佔整條右邊" % str(sb.get_global_rect()))
	sb.toggle()
	await process_frame
	h.check(not sb.collapsed and sb.get_global_rect() == Rect2(840.0, 0.0, 440.0, 720.0), "展開回整條")
	h.check(sb.toggle_btn.focus_mode == Control.FOCUS_NONE and sb.tree.focus_mode == Control.FOCUS_NONE and sb.events_label.focus_mode == Control.FOCUS_NONE, "按鈕、樹、事件流都不搶鍵盤焦點（空白鍵留給遊戲）")
	# 使用者收合連 → 下次 refresh 不會被展開
	var co_item: TreeItem = sb._items["co-A"]
	co_item.set_collapsed(true)
	sb.refresh(b2, {"state": "online", "line": "參謀長：守住", "busy_s": 2.0, "orders": ["co-A 固守 C3"], "cost": 0.02, "ticks": 5, "ended": false})
	h.check(co_item.collapsed and sb.selected_unit == "", "refresh 尊重使用者的收合")
	# 排在連之前出現也掛得到連
	var b3 := sample_board()
	var co_row: Dictionary = b3["orbat"].pop_front()
	b3["orbat"].append(co_row)
	var sb2 := Sidebar.new()
	get_root().add_child(sb2)
	sb2.refresh(b3)
	h.check(sb2.tree.get_root().get_child_count() == 1 and sb2._items["plt-A1"].get_parent() == sb2._items["co-A"], "板上排排在連前面：仍掛到連底下")
	# 連消失、排還在：不炸、排重掛到 root
	var b4 := sample_board()
	b4["orbat"] = b4["orbat"].filter(func(u: Dictionary) -> bool: return u["id"] != "co-A")
	sb2.refresh(b4)
	h.check(sb2.unit_count() == b4["orbat"].size() and not sb2._items.has("co-A") and is_instance_valid(sb2._items["plt-A1"]) and sb2._items["plt-A1"].get_parent() == sb2.tree.get_root(), "連從板上消失：子排不懸空、重掛到根")
	sb2.refresh(sample_board())                      # 連回來了
	var b5 := sample_board()
	b5["orbat"] = b5["orbat"].filter(func(u: Dictionary) -> bool: return not (u["id"] in ["co-A", "plt-A1", "plt-A2"]))   # 連＋兩個排同時消失
	sb2.refresh(b5)
	sb2.refresh(b5)
	h.check(sb2.unit_count() == b5["orbat"].size() and sb2._items.values().all(func(it) -> bool: return is_instance_valid(it)) and sb2.tree.get_root().get_child_count() == b5["orbat"].size(), "連與子排同時消失：不炸、表裡沒有已釋放的項、剩下的排掛到根")
	sb2.queue_free()
	h.check(a1.get_text(0) == "A1 步兵排 ★直轄" and a1.get_custom_color(0) == Sidebar.COLOR_PLAYER and sb._items["plt-A2"].get_text(2) == "潰散" and sb._items["plt-A2"].get_custom_color(0) == Sidebar.COLOR_BAD, "直轄標記與潰散上色")
	h.check(sb.events_label.text.contains(Sidebar.COLOR_GOOD.to_html(false)) and sb.chief_label.text.contains("思考中 2 秒"), "事件流有綠色的 👍、參謀長區有思考中")
	var got := []
	sb.unit_selected.connect(func(uid: String) -> void: got.append(uid))
	h.check(sb.select_unit("plt-A3") and got == ["plt-A3"] and sb.selected_unit == "plt-A3" and not sb.select_unit("nope"), "點樹 → unit_selected")
	sb.toggle()
	h.check(sb.collapsed and not sb.body.visible and sb.toggle_btn.text == "◀ 戰情", "收合")
	sb.toggle()
	h.check(not sb.collapsed and sb.body.visible and sb.offset_left == -Sidebar.WIDTH, "展開")
	sb.queue_free()

	# ---- Battle 場景：側欄跟著板、點排移攝影機 ----
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var battle: Battle = scene.instantiate()
	battle.auto_advance = false
	battle.use_cmdline_args = false
	battle.board_out = ""
	battle.snapshot_dir = ""
	battle.chief_autostart = false
	battle.friendly_path = "m0://samples/orders_v1_assault.json"
	get_root().add_child(battle)
	await process_frame
	await physics_frame
	await physics_frame
	h.check(battle.sidebar != null and battle.sidebar.unit_count() == battle.writer.to_dict()["orbat"].size() and battle.sidebar.refreshes == 1, "Battle 的 HUD 有側欄，開局就建好樹")
	h.check(battle.hud_label.autowrap_mode == TextServer.AUTOWRAP_WORD_SMART and battle.hud_text_width() == 816.0 and battle.hud_label.custom_minimum_size.x == 816.0 and battle.chief_label.position.y > battle.hud_label.position.y, "HUD 兩行寬 816（1280 − 440 − 24）在側欄左邊換行")
	get_root().size = Vector2i(1024, 768)
	await process_frame
	h.check(battle.hud_text_width() == 560.0 and battle.hud_label.custom_minimum_size.x == 560.0, "視窗縮到 1024 → HUD 寬重算 560（不再蓋到側欄）")
	get_root().size = Vector2i(1280, 720)
	await process_frame
	h.check(battle.battle_seconds() == 300 and battle.sidebar.battle_seconds == 300 and not battle.mouse_over_ui(), "會戰長度來自導演常數；滑鼠 (0,0) 不在側欄上 → 邊緣捲動照常")
	for i in 60 * 40:
		battle.director.tick(1.0 / 60.0)
	battle.sidebar.refresh(battle.writer.to_dict(), battle.chief_sidebar_info())
	h.check(battle.sidebar.conditions_label.text.contains("t=40 秒") and battle.sidebar.events_label.text.contains("參謀長令") and battle.sidebar.chief_label.text == "參謀長離線（劇本／空白鍵）", "40 秒後：時間、劇本命令事件、參謀長離線（chief_autostart=false 且 state off）")
	var before := battle.camera_rig.position
	var target := battle.unit_world_position("plt-A1")
	battle.sidebar.select_unit("plt-A1")
	h.check(target != Vector3.INF and battle.camera_rig.position != before and battle.camera_rig.position.distance_to(Vector3(target.x, battle.camera_rig.position.y, target.z)) < 30.0, "點 A1 排 → 攝影機移到它附近")
	var co := battle.unit_world_position("co-A")
	h.check(co != Vector3.INF and battle.unit_world_position("nope") == Vector3.INF, "連的位置＝下級排平均；不存在 → INF")
	battle.queue_free()
	await process_frame
	h.finish()
