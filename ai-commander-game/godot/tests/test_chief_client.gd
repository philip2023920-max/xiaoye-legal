extends SceneTree
## 施工單 17：節拍排程器（純邏輯）、客戶端失敗路徑（沒有服務）、跨程序整合（Godot 真的啟動 m0 的
## `uv run chief serve --provider fake`，打完一場 5 分鐘會戰：至少 10 拍、事件流有「參謀長令」、費用 0、戰報卡、關機）。
##   godot --headless --path . -s tests/test_chief_client.gd
## 需要 uv 在 PATH、m0/.venv 已 sync（uv run 會自己處理）。

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 35, 600.0)
	_run.call_deferred()

func wipe(real: String) -> void:
	if not DirAccess.dir_exists_absolute(real):
		return
	for sub in DirAccess.get_directories_at(real):
		wipe(real.path_join(sub))
		DirAccess.remove_absolute(real.path_join(sub))
	for f in DirAccess.get_files_at(real):
		DirAccess.remove_absolute(real.path_join(f))

func _call_into(client: ChiefClient, box: Dictionary) -> void:
	box["r"] = await client.call_api("POST", "/tick", {"t": 0, "board": {}}, 30.0)

func _run() -> void:
	# ---- 1. 排程器 ----
	var s := TickScheduler.new()
	h.check(s.due(0.0, []), "t=0 立即一拍")
	s.mark_sent(0.0)
	h.check(not s.due(10.0, []) and not s.due(25.0, []), "在飛中不送（即使過了 20 秒）")
	s.mark_done()
	h.check(s.due(25.0, []) and s.next_regular() == 20.0, "回覆到了、已過期 → 立刻補送")
	s.mark_sent(25.0); s.mark_done()
	h.check(not s.due(44.9, []) and s.due(45.0, []), "規律節拍：上次送出 + 20 秒")
	s.mark_sent(45.0); s.mark_done()
	var evs: Array = [{"t": 48, "kind": "contact", "text": "接觸"}]
	h.check(not s.due(48.0, evs) and not s.due(52.9, evs) and s.due(53.0, evs), "事件觸發但與上次至少隔 8 秒（45 → 53）")
	s.mark_sent(53.0); s.mark_done()
	evs.append({"t": 55, "kind": "order", "text": "x"}); evs.append({"t": 55, "kind": "info", "text": "y"})
	h.check(not s.due(62.0, evs), "order／info 事件不觸發；舊事件不會重複觸發")
	evs.append({"t": 63, "kind": "routed", "text": "潰散"})
	s.mark_sent(63.0)                       # 事件來時剛好在飛
	h.check(not s.due(64.0, evs), "在飛期間的事件先記著")
	s.mark_done()
	h.check(not s.due(70.0, evs) and s.due(71.0, evs) and s.ticks_sent == 5, "回覆後等滿 8 秒再補送事件拍")

	# ---- 2. 失敗路徑：沒有服務 ----
	var dead := ChiefClient.new()
	get_root().add_child(dead)
	dead.connect_to("http://127.0.0.1:%d/" % ChiefClient.free_port())
	var t0 := Time.get_ticks_msec()
	var ok: bool = await dead.wait_online(1.5)
	h.check(not ok and not dead.online and Time.get_ticks_msec() - t0 < 6000 and dead.last_error.contains("沒起來"), "連不上 → 離線、人話")
	var r0: Dictionary = await dead.call_api("POST", "/tick", {}, 2.0)
	h.check(r0["code"] == 0 and r0["error"] != "" and not dead.busy, "請求失敗回 code 0 與人話、busy 歸零")
	dead.queue_free()

	# ---- 3. 整合：啟動服務（fake）、打完 5 分鐘 ----
	var out_dir := ProjectSettings.globalize_path("user://chief_test")
	wipe(out_dir)
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var battle: Battle = scene.instantiate()
	battle.auto_advance = false
	battle.use_cmdline_args = false
	battle.board_out = ""
	battle.snapshot_dir = ""
	battle.friendly_path = ""
	battle.difficulty = "normal"
	battle.chief_provider = "fake"
	battle.chief_autostart = false
	battle.chief_extra = PackedStringArray(["--out-root", out_dir, "--ledger", "none", "--idle-exit", "120"])
	get_root().add_child(battle)
	await process_frame
	await physics_frame
	await physics_frame
	t0 = Time.get_ticks_msec()
	var started: bool = await battle.start_chief()
	var boot_ms := Time.get_ticks_msec() - t0
	h.check(started and battle.chief_state == "online" and battle.chief.pid > 0 and battle.chief.online, "uv run chief serve 啟動、/health 通、開局（%d ms）" % boot_ms)
	h.check(boot_ms < 10000, "10 秒內上線")
	h.check(str(battle.chief_session.get("provider", "")) == "fake" and battle.chief_session.has("opening_line") and battle.chief_line.begins_with("參謀長"), "開局回應含供應商與引用句；HUD 第二行是參謀長")
	h.check(battle.orbat.events.any(func(ev: Dictionary) -> bool: return ev["kind"] == "info" and ev["text"].begins_with("參謀長")), "開局寫進事件流")
	var hud_before := battle.chief_hud_text()
	# 驅動：每個物理步推進導演再問節拍；請求在飛就等回覆（真遊戲不等；測試要確定性）
	var dt := 1.0 / 60.0
	var guard := 0
	var saw_thinking := false
	var first_tick_sec := -1
	while not battle.director.finished and guard < 100000:
		battle.director.tick(dt)
		battle.chief_update()
		if battle.chief.busy:
			if first_tick_sec < 0:
				first_tick_sec = battle.orbat.second()
			saw_thinking = saw_thinking or battle.chief_hud_text().contains("思考中")
			await battle.chief.replied
			while battle.scheduler.in_flight:   # 回覆套用完（mark_done）才繼續推進
				await process_frame
		guard += 1
	battle.show_result()
	battle.chief_update()                   # 結束 → /battle/end
	var waited := 0
	while battle.chief_end_response.is_empty() and waited < 600:
		await create_timer(0.05).timeout
		waited += 1
	var r: Dictionary = battle.director.result
	h.check(not r.is_empty() and r["seconds"] > 0, "會戰打完（%s，%d 秒，%s）" % [r.get("winner", "?"), r.get("seconds", 0), r.get("end_reason", "?")])
	h.check(first_tick_sec == 0 and battle.chief_ticks >= 10 and battle.scheduler.ticks_sent == battle.chief_ticks, "t=0 立即一拍、共 %d 拍（≥10）、全部有回覆" % battle.chief_ticks)
	h.check(saw_thinking, "在飛時 HUD 顯示「參謀長思考中」")
	var order_events := battle.orbat.events.filter(func(ev: Dictionary) -> bool: return ev["kind"] == "order" and ev["text"].begins_with("參謀長令"))
	h.check(order_events.size() >= 3 and order_events[0]["t"] == 0, "事件流有「參謀長令 …」（%d 條，第一條在第 0 秒）" % order_events.size())
	var reply_events := battle.orbat.events.filter(func(ev: Dictionary) -> bool: return ev["kind"] == "info" and ev["text"].begins_with("參謀長回覆："))
	h.check(reply_events.size() == battle.chief_ticks and reply_events[0]["text"].contains("延遲"), "每拍一條「參謀長回覆：n 條命令（延遲 n 秒）」")
	h.check(battle.chief_line.begins_with("參謀長：") and hud_before != battle.chief_hud_text() and battle.chief_hud_text().contains("費用 $0.0000"), "HUD 第二行有研判／摘要與費用 0")
	h.check(battle.chief_cost == 0.0, "fake 供應商費用 0")
	var er: Dictionary = battle.chief_end_response
	h.check(er["code"] == 200 and er["body"].has("card") and er["body"]["card"]["winner"] == r["winner"] and er["body"].has("unjudged"), "/battle/end 回戰報卡，勝負與導演一致")
	h.check(battle.chief_state == "ended" and battle.orbat.events.any(func(ev: Dictionary) -> bool: return ev["text"].begins_with("戰報卡已產生")), "結束後狀態 ended、事件流有戰報卡")
	var st: Dictionary = await battle.chief.status()
	h.check(st["code"] == 200 and st["body"]["ended"] == true and st["body"]["turn"] == battle.chief_ticks and float(st["body"]["cost_usd"]) == 0.0, "/status：拍數與費用一致")
	# 服務端檔案：battles/<id>-<時間>/ 有 t0.json、llm_log.jsonl（每拍一行）、aar.json
	var dirs: Array = Array(DirAccess.get_directories_at(out_dir))
	var svc_dir := out_dir.path_join(dirs[0]) if dirs.size() == 1 else ""
	var llm_lines := 0
	if svc_dir != "" and FileAccess.file_exists(svc_dir.path_join("llm_log.jsonl")):
		llm_lines = FileAccess.get_file_as_string(svc_dir.path_join("llm_log.jsonl")).strip_edges().split("\n").size()
	h.check(dirs.size() == 1 and FileAccess.file_exists(svc_dir.path_join("t0.json")) and FileAccess.file_exists(svc_dir.path_join("aar.json")) and llm_lines == battle.chief_ticks, "服務端每場一個資料夾：t0.json、aar.json、llm_log 每拍一行")
	var last_snap := svc_dir.path_join("t%d.json" % battle.chief_ticks)
	var snap: Variant = JSON.parse_string(FileAccess.get_file_as_string(last_snap)) if FileAccess.file_exists(last_snap) else null
	h.check(snap is Dictionary and snap["t"] == r["seconds"] and snap["time_unit"] == "second", "最終板存成 t<拍數>.json（t＝結束那秒、秒制）")
	# 已直轄的排：參謀長的令不套用（服務 V2 會擋；客戶端保險）
	battle.orbat.platoons["plt-A1"].controlled_by = "player"
	h.check(battle._is_player_controlled("plt-A1") and not battle._is_player_controlled("plt-A2") and not battle._is_player_controlled("nope"), "直轄判斷")
	# 關機：服務自己退出、子程序消失
	var pid: int = battle.chief.pid
	await battle.chief.stop()
	h.check(pid > 0 and not OS.is_process_running(pid) and battle.chief.pid == -1 and not battle.chief.online, "stop()：/shutdown 後程序結束")
	var r1: Dictionary = await battle.chief.call_api("GET", "/health", {}, 1.0)
	h.check(r1["code"] == 0, "關機後連不上")
	battle.queue_free()
	await process_frame

	# ---- 3b. 孤兒：客戶端沒 stop() 就被拆（編輯器停止、當掉）→ 服務靠 --parent-pid 不會留下來 ----
	# 這裡拆的是 ChiefClient 節點（kill 到 uv 外殼）；Python 服務要自己發現啟動者消失才退出。
	# 沙盒裡 Godot 本身還活著，所以模擬「啟動者消失」的方式是：用一個很快結束的假父程序 pid。
	var orphan := ChiefClient.new()
	get_root().add_child(orphan)
	# 假父程序要「真的消失」而不是變殭屍（Godot 不會 wait 它開的子程序），所以用 sh 背景起一個 sleep 再讓 sh 自己退出
	var fake_parent := -1
	if OS.get_name() != "Windows":
		var out: Array = []
		OS.execute("sh", ["-c", "sleep 3 >/dev/null 2>&1 & echo $!"], out)
		fake_parent = int(str(out[0]).strip_edges()) if out.size() > 0 else -1
	if fake_parent > 0:
		orphan.launch("fake", PackedStringArray(["--out-root", out_dir, "--ledger", "none", "--parent-pid", str(fake_parent)]))
		var up: bool = await orphan.wait_online(10.0)
		var url := orphan.base_url
		var tok := orphan.token
		orphan.queue_free()
		await process_frame
		var probe := ChiefClient.new()
		get_root().add_child(probe)
		probe.connect_to(url, tok)
		var gone := false
		var t1 := Time.get_ticks_msec()
		while Time.get_ticks_msec() - t1 < 12000:
			var hr: Dictionary = await probe.call_api("GET", "/health", {}, 1.0)
			if hr["code"] == 0:
				gone = true
				break
			await create_timer(0.5).timeout
		h.check(up and gone, "啟動者消失 → 服務 %d 秒內自己退出（--parent-pid）" % int((Time.get_ticks_msec() - t1) / 1000))
		probe.queue_free()
	else:
		h.check(true, "（Windows 沙盒略過孤兒測試）")

	# ---- 3c. 關機不等在飛的請求：對一個只接受連線、永不回覆的埠送 /tick，stop() 要在 3 秒內回來 ----
	var sink := TCPServer.new()
	sink.listen(0, "127.0.0.1")
	var hang := ChiefClient.new()
	get_root().add_child(hang)
	hang.connect_to("http://127.0.0.1:%d" % sink.get_local_port())
	hang.online = true
	var box := {}
	_call_into(hang, box)                      # 不 await：讓它在飛
	await create_timer(0.3).timeout
	if sink.is_connection_available():
		sink.take_connection()                 # 接受但永不回覆
	var t2 := Time.get_ticks_msec()
	await hang.stop()
	while not box.has("r"):
		await process_frame
	var cancelled: Dictionary = box["r"]
	h.check(Time.get_ticks_msec() - t2 < 5000 and cancelled["code"] == 0 and cancelled["error"].contains("取消") and not hang.busy, "stop() 取消在飛的請求（%d ms）；該請求回「已取消」" % (Time.get_ticks_msec() - t2))
	sink.stop()
	hang.queue_free()
	await process_frame

	# ---- 4. 離線模式：找不到 uv ----
	var b2: Battle = scene.instantiate()
	b2.auto_advance = false; b2.use_cmdline_args = false; b2.board_out = ""; b2.snapshot_dir = ""
	b2.chief_provider = "fake"; b2.chief_autostart = false; b2.chief_uv = "/nonexistent/uv-not-here"
	get_root().add_child(b2)
	await process_frame
	await physics_frame
	await physics_frame
	var ok2: bool = await b2.start_chief()
	h.check(not ok2 and b2.chief_state == "offline" and b2.chief_line.contains("離線模式") and b2.chief_hud_text().contains("沒起來"), "找不到 uv → 離線模式、HUD 說明")
	h.check(b2.chief.last_error.contains("找不到 uv") and (b2.chief.pid == -1 or not OS.is_process_running(b2.chief.pid)), "錯誤訊息提到 uv（Unix 是 exec 失敗、Windows 是 pid<=0 兩條路都進這句）")
	b2.chief_update()
	h.check(b2.scheduler.ticks_sent == 0 and b2.orbat.apply_orders("us", [Order.make("co-A", "seize", "C3", "player", "偵錯")]).is_empty(), "離線時不送節拍；空白鍵命令照常")
	b2.chief_provider = "off"
	h.check(not b2.chief_enabled() and b2.chief_hud_text().contains("離線"), "chief=off 關掉參謀長")
	b2.queue_free()
	await process_frame
	h.finish()
