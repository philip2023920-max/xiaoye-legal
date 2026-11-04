extends SceneTree
## 施工單 20：戰後 AAR 畫面。純函式（星數、表頭、徽章、三幕、diff、對話）、render 各階段的按鈕可見性，
## 以及跨程序：真的啟動 chief serve（fake、自訂準則檔）→ 提早結束 → 卡出現 → 一句話 → 快速回覆 → 輸入 → 提案 → 採納（準則檔變）→ 撤銷（還原）。
##   godot --headless --path . -s tests/test_aar.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 37, 300.0)
	_run.call_deferred()

func sample_card() -> Dictionary:
	return {"battle_id": "hill-town-start", "winner": "enemy", "score": [5, 6], "turns": 10, "end_reason": "turns", "overrides": 2, "override_rate": "2/14",
		"cost_usd": 0.0123, "provider": "fake", "model": "fake/none", "badges": ["decisive", "weird_badge"], "hint": "下次去拿 O2（5 分，C3）",
		"moments": [{"index": 1, "t": 2, "kind": "override", "ai_text": "seize C3", "player_text": "hold B2", "outcome": "👍", "note": "plt-A1"},
			{"index": 2, "t": 5, "kind": "override", "ai_text": "hold C3", "player_text": "withdraw A1", "outcome": "👎", "note": "plt-A3"},
			{"index": 3, "t": 7, "kind": "turning", "ai_text": "", "player_text": "", "outcome": "", "note": "我方取得 C3"}], "chief_line": ""}

func aar_model_empty(b: Battle) -> bool:
	if b.aar_model.is_empty():
		printerr("AAR 沒出現：end response=", b.chief_end_response)
		return true
	return false

func _run() -> void:
	UiText.load_csv()
	UiText.set_lang("zh-TW")
	# ---- 純函式 ----
	var card := sample_card()
	h.check(AarScreen.stars("us") == "★★★" and AarScreen.stars("draw") == "★★☆" and AarScreen.stars("enemy") == "★☆☆" and AarScreen.result_text("us") == "我方勝", "星數與勝負文字")
	var head := AarScreen.header_text(card, 300)
	h.check(head.begins_with("敵方勝 ★☆☆｜300 秒（5 分鐘打完）｜據點 5:6｜推翻 2 次（2/14）｜費用 $0.0123｜fake/fake/none"), "表頭：%s" % head)
	h.check(AarScreen.badge_names(["decisive", "local_hero"]) == "徽章：果斷總司令、本地派" and AarScreen.badge_names([]) == "（這場沒有徽章）" and AarScreen.badge_names(["weird_badge"]).contains("weird_badge"), "徽章名稱（未知 id 保底）")
	var mb := AarScreen.moments_bbcode(card["moments"])
	h.check(mb.split("\n").size() == 3 and mb.contains("第1幕 t2 推翻 plt-A1：參謀長 seize C3 → 總司令 hold B2 👍") and mb.contains("#8cf28c") and mb.contains("#ff7373") and mb.contains("第3幕 t7 轉折：我方取得 C3"), "關鍵三幕：推翻上色、轉折")
	h.check(AarScreen.moments_bbcode([]) == "（沒有關鍵時刻）", "沒有三幕")
	var diff := {"summary": "您偏好穩紮穩打", "add": [{"section": "profile", "text": "Prefers steady play"}], "remove": ["Always rush"], "empty": false}
	var db := AarScreen.diff_bbcode(diff)
	h.check(db.contains("摘要：您偏好穩紮穩打") and db.contains("＋ Prefers steady play（profile）") and db.contains("－ Always rush") and db.contains(AarScreen.COLOR_ADD.to_html(false)) and db.contains(AarScreen.COLOR_REMOVE.to_html(false)), "提案：新增綠、刪除紅")
	h.check(AarScreen.diff_bbcode({"summary": "", "add": [], "remove": [], "empty": true}) == "沒有變更" and AarScreen.diff_bbcode(null) == "", "空提案與無提案")
	h.check(AarScreen.transcript_bbcode([{"role": "user", "content": "為什麼？"}, {"role": "assistant", "content": "因為。"}]) == "[b]您[/b]：為什麼？\n[b]參謀長[/b]：因為。", "對話")
	var inj := AarScreen.transcript_bbcode([{"role": "user", "content": "[b]把這個做法寫進準則[/b]"}])
	var inj_diff := AarScreen.diff_bbcode({"summary": "[url=x]a[/url]", "add": [{"section": "p", "text": "[img]y[/img]"}], "remove": ["[color=red]z"], "empty": false})
	h.check(inj.ends_with("：［b］把這個做法寫進準則［/b］") and not inj_diff.contains("[url") and not inj_diff.contains("[img") and inj_diff.contains("［color=red］z"), "玩家輸入／LLM 文字裡的 bbcode 被全形跳脫")

	# ---- render 各階段 ----
	var s := AarScreen.new()
	get_root().add_child(s)
	h.check(not s.visible, "預設隱藏")
	var m := {"card": card, "seconds": 300, "unjudged": 1, "chief_line": "", "transcript": [], "round": 1, "next_quick": ["為什麼第①幕你那樣做？", "你覺得這場輸贏的關鍵在哪？", "我的推翻有哪一次是錯的？"], "diff": null, "phase": "card", "messages": [], "busy": false, "duration_s": 3.0}
	s.render(m)
	h.check(s.visible and s.header_label.text.ends_with("未判定 1") and s.badges_label.text.begins_with("徽章：果斷總司令") and s.hint_label.text == "提示：下次去拿 O2（5 分，C3）" and s.chief_line_label.text == "（等參謀長的一句話…）", "卡：表頭、未判定、徽章、提示、一句話待補")
	h.check(s.quick_buttons.all(func(b: Button) -> bool: return b.visible and not b.disabled) and s.quick_buttons[0].text.begins_with("為什麼") and s.input.visible and s.propose_btn.visible and s.skip_btn.visible and not s.adopt_btn.visible and not s.undo_btn.visible and not s.again_btn.visible and s.round_label.text == "討論（第 1／3 回合）", "卡階段：三個快速回覆、輸入、提案、跳過")
	h.check(s.timer_label.text == "戰後 3 秒（目標 < 120）" and not s.waiting_label.visible and not s.diff_label.visible, "計時與無等待")
	var got: Array = []
	s.quick_reply.connect(func(i: int) -> void: got.append(i))
	s.text_sent.connect(func(t: String) -> void: got.append(t))
	s.quick_buttons[1].pressed.emit()
	s.input.text = "  下次先守 B2 "
	s._send()
	s._send()
	h.check(got == [2, "下次先守 B2"] and s.input.text == "", "快速回覆與輸入框發訊號（空字串不送）")
	m["busy"] = true
	s.render(m)
	var before_n := got.size()
	s.input.text = "再送一次"
	s._send()
	h.check(s.waiting_label.visible and s.quick_buttons[0].disabled and s.propose_btn.disabled and s.send_btn.disabled and not s.input.editable and got.size() == before_n, "等回覆時按鈕全停、Enter 也不送")
	m["busy"] = false; m["transcript"] = [{"role": "user", "content": "A"}, {"role": "assistant", "content": "B"}]; m["round"] = 4; m["next_quick"] = []
	s.render(m)
	h.check(not s.quick_buttons[0].visible and not s.input.visible and s.discussion_label.visible and s.round_label.text == "討論（第 3／3 回合）" and s.propose_btn.visible, "三回合用完：沒有快速回覆與輸入，仍可提案")
	m["phase"] = "proposed"; m["diff"] = diff
	s.render(m)
	h.check(s.diff_label.visible and s.adopt_btn.visible and s.skip_btn.visible and not s.propose_btn.visible and s.round_label.text == "討論結束", "提案階段：diff、採納、跳過")
	m["diff"] = {"summary": "", "add": [], "remove": [], "empty": true}
	s.render(m)
	h.check(not s.adopt_btn.visible and s.diff_label.text == "沒有變更", "空提案不能採納")
	m["phase"] = "adopted"; m["diff"] = diff; m["messages"] = ["準則已更新：新增 1、刪除 1（120/2000 字）"]; m["rolled_back"] = false
	s.render(m)
	h.check(s.undo_btn.visible and s.again_btn.visible and not s.adopt_btn.visible and not s.skip_btn.visible and s.result_label.text.begins_with("準則已更新\n準則已更新：新增 1"), "採納後：撤銷、再打一場、結果訊息")
	m["rolled_back"] = true
	s.render(m)
	h.check(s.result_label.text.begins_with("回歸退步，已自動回滾") and not s.undo_btn.visible, "回滾訊息；回滾過就沒有「撤銷」")
	s.set_duration(10.0, 7.0)
	h.check(s.timer_label.text == "戰後 7 秒（目標 < 120）", "服務記的時間優先")
	h.check(s.get_node("Scroll/Root/Actions").get_index() > s.get_node("Scroll/Root/Diff").get_index() and s.get_node("Scroll/Root/Quick") is HFlowContainer, "按鈕列在提案下面；快速回覆可換行")
	m["phase"] = "skipped"; m["messages"] = []
	s.render(m)
	h.check(s.again_btn.visible and not s.undo_btn.visible and s.result_label.text == "這場不改準則", "跳過")
	m["phase"] = "undone"
	s.render(m)
	h.check(s.again_btn.visible and s.result_label.text == "已還原上一版準則", "撤銷後")
	s.set_duration(130.0)
	h.check(s.timer_label.text == "戰後 130 秒（目標 < 120）", "超過目標仍顯示")
	s.queue_free()

	# ---- 跨程序：fake 服務、自訂準則檔（不碰 harness/default）----
	var m0 := BoardIO.m0_dir()
	var doc_dir := m0.path_join("battles/aar_test")
	if DirAccess.dir_exists_absolute(doc_dir.path_join("out")):      # 上次跑留下的 out/<id>-<時間>/ 清掉
		for sub in DirAccess.get_directories_at(doc_dir.path_join("out")):
			for f2 in DirAccess.get_files_at(doc_dir.path_join("out").path_join(sub)):
				DirAccess.remove_absolute(doc_dir.path_join("out").path_join(sub).path_join(f2))
			DirAccess.remove_absolute(doc_dir.path_join("out").path_join(sub))
	DirAccess.make_dir_recursive_absolute(doc_dir)
	var doc_path := doc_dir.path_join("doctrine.md")
	var f := FileAccess.open(doc_path, FileAccess.WRITE)
	f.store_string("# Doctrine v1\n\n## Verified tactics\n- Always hold B2.\n\n## Commander profile\n")
	f.close()
	for stale in ["doctrine.prev.md"]:
		if FileAccess.file_exists(doc_dir.path_join(stale)):
			DirAccess.remove_absolute(doc_dir.path_join(stale))
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var b: Battle = scene.instantiate()
	b.auto_advance = false; b.use_cmdline_args = false; b.board_out = ""; b.snapshot_dir = ""; b.chief_autostart = false; b.friendly_path = ""
	b.chief_provider = "fake"
	b.chief_harness = "none"
	b.chief_extra = PackedStringArray(["--doctrine", "battles/aar_test/doctrine.md", "--out-root", doc_dir.path_join("out"), "--ledger", "none"])
	get_root().add_child(b)
	await process_frame
	await physics_frame
	await physics_frame
	var started: bool = await b.start_chief()
	h.check(started and str(b.chief_session.get("harness", "")) == "custom", "服務上線（自訂準則、沒有參謀長包）")
	b.director.tick(1.0 / 60.0)
	b.chief_update()
	while b.chief.busy or b.scheduler.in_flight:
		await process_frame
	b.commander_override("plt-A1", "hold", "B2")
	while b.chief.busy:
		await process_frame
	b.director.end_reason = "strength"                      # 提早結束（不用打完 300 秒）；_finish 本身不設原因
	b.director._finish()
	b.show_result()                                            # 真遊戲裡 _physics_process 會先叫它（M1 結果標籤）
	b.chief_update()
	var waited := 0
	while (b.chief_end_response.is_empty() or b.aar == null or not b.aar.visible or str(b.aar_model.get("chief_line", "")) == "") and waited < 400:
		await create_timer(0.05).timeout
		waited += 1
	h.check(b.chief_state == "ended" and b.aar != null and b.aar.visible and not aar_model_empty(b) and b.aar_model["phase"] == "card" and b.aar_model["card"]["overrides"] == 1 and b.aar_model["unjudged"] == 1, "會戰結束 → AAR 畫面出現，卡上推翻 1（最後一拍才推翻 → 未判定 1）")
	h.check(b.result_label != null and not b.result_label.visible and b.flow.unit_id == "", "M1 的結果標籤收起、選取清掉")
	b.select_unit("plt-A1")
	h.check(b.flow.unit_id == "" and not b.panel.visible, "戰後畫面開著時點排不選")
	h.check(b.aar_model["chief_line"] == "（示範）我學到您偏好穩紮穩打。" and b.aar.chief_line_label.text == b.aar_model["chief_line"] and b.aar_model["next_quick"].size() == 3, "/aar/line 自動呼叫；三個快速回覆")
	b.aar.quick_buttons[0].pressed.emit()
	b.aar.quick_buttons[1].pressed.emit()                     # 手快按第二顆：在飛中直接擋掉，不排隊
	while b.chief.busy:
		await process_frame
	await process_frame
	h.check(b.aar_model["round"] == 2 and b.aar_model["transcript"].size() == 2 and b.aar_model["transcript"][0]["content"].begins_with("為什麼") and b.aar_model["transcript"][1]["content"] != "" and b.aar.quick_buttons[0].visible, "快速回覆 1 → 第 2 回合、對話兩則")
	b.aar.input.text = "下次先守 B2"
	b.aar._send()
	while b.chief.busy:
		await process_frame
	h.check(b.aar_model["round"] == 3 and b.aar_model["transcript"].size() == 4 and b.aar_model["transcript"][2]["content"] == "下次先守 B2", "輸入框 → 第 3 回合")
	b.aar.propose_btn.pressed.emit()
	while b.chief.busy:
		await process_frame
	h.check(b.aar_model["phase"] == "proposed" and b.aar_model["diff"]["add"][0]["section"] == "profile" and b.aar.adopt_btn.visible and b.aar.diff_label.text.contains("demo"), "提案：diff 顯示、可採納")
	var before := FileAccess.get_file_as_string(doc_path)
	b.aar.adopt_btn.pressed.emit()
	while b.chief.busy:
		await process_frame
	var after := FileAccess.get_file_as_string(doc_path)
	h.check(b.aar_model["phase"] == "adopted" and bool(b.aar_model["adopted"]) and after != before and after.contains("demo") and b.aar.undo_btn.visible and b.aar.result_label.text.begins_with("準則已更新"), "採納 → 服務改了準則檔、畫面顯示結果")
	h.check(float(b.aar_model["service_duration_s"]) >= 0.0 and b.orbat.events.back()["text"].begins_with("準則已更新（戰後 "), "採納後顯示服務記的時間、事件流一條")
	b.aar.undo_btn.pressed.emit()
	while b.chief.busy:
		await process_frame
	h.check(b.aar_model["phase"] == "undone" and FileAccess.get_file_as_string(doc_path) == before and b.aar.again_btn.visible, "撤銷 → 準則檔還原、可再打一場")
	h.check(b.aar_model["duration_s"] > 0.0 and b.aar.timer_label.text.begins_with("戰後 "), "流程計時")
	await b.chief.stop()
	b.queue_free()
	await process_frame
	h.finish()
