extends SceneTree
## 施工單 21：設定（正規化、存讀、/settings body、啟動引數、金鑰狀態）、費用 HUD（狀態與文字）、設定頁（填入／讀回）、
## 字串表（程式裡用到的每個 UI_ 鍵都在 CSV、三語齊、% 數一致）、Battle：Esc 開關設定頁、儲存 → 語言即時切換（整個 UI 重建）、
## 真的啟動 chief serve：儲存預算 0 → /settings → 下一拍參謀長暫停 → 費用 HUD 變紅。
##   godot --headless --path . -s tests/test_settings.gd

var h: TestHarness

func _initialize() -> void:
	h = TestHarness.new(self, 33, 300.0)
	_run.call_deferred()

func _scan_keys(dir: String, out: Dictionary) -> void:
	for f in DirAccess.get_files_at(dir):
		if f.ends_with(".gd"):
			var text := FileAccess.get_file_as_string(dir.path_join(f))
			var re := RegEx.new()
			re.compile("\"(UI_[A-Za-z0-9_]+)\"")
			for m in re.search_all(text):
				if not m.get_string(1).ends_with("_"):     # "UI_TASK_" + task 這種前綴組合不算
					out[m.get_string(1)] = true
	for d in DirAccess.get_directories_at(dir):
		_scan_keys(dir.path_join(d), out)

func _run() -> void:
	get_root().size = Vector2i(1280, 720)
	UiText.load_csv()
	UiText.set_lang("zh-TW")
	# ---- GameSettings ----
	var n := GameSettings.normalize({"provider": "skynet", "lang": "fr", "budget_usd": "abc", "effort": "max", "model": "  m  ", "extra": 1, "harness": ""})
	h.check(n["provider"] == "fake" and n["lang"] == "zh-TW" and n["budget_usd"] == -1.0 and n["effort"] == "" and n["model"] == "m" and n["harness"] == "default" and not n.has("extra"), "normalize：壞值回預設、多的鍵丟掉")
	var good := GameSettings.normalize({"provider": "anthropic", "model": "claude-haiku-5-5", "lang": "en", "budget_usd": 0.5, "effort": "low", "aar_provider": "anthropic", "aar_model": "claude-sonnet-5-5"})
	h.check(good["provider"] == "anthropic" and good["budget_usd"] == 0.5 and good["effort"] == "low" and good["aar_model"] == "claude-sonnet-5-5", "normalize：合法值原樣")
	var path := "user://settings_test.json"
	h.check(GameSettings.save(good, path) and GameSettings.load(path) == good, "存讀往返")
	var f := FileAccess.open(path, FileAccess.WRITE); f.store_string("{not json"); f.close()
	h.check(GameSettings.load(path) == GameSettings.DEFAULTS and GameSettings.load("user://nope.json") == GameSettings.DEFAULTS, "壞檔／沒檔 → 預設")
	var body := GameSettings.service_body(good)
	h.check(body == {"provider": "anthropic", "lang": "en", "budget_usd": 0.5, "model": "claude-haiku-5-5", "effort": "low", "aar_provider": "anthropic", "aar_model": "claude-sonnet-5-5"}, "/settings body：全欄位")
	var body2 := GameSettings.service_body({"provider": "fake"})
	h.check(body2 == {"provider": "fake", "lang": "zh-TW", "budget_usd": -1.0}, "/settings body：空欄位不送、預算 -1＝取消")
	var args := GameSettings.launch_args(good)
	h.check(Array(args) == ["--harness", "default", "--lang", "en", "--model", "claude-haiku-5-5", "--budget", "0.5", "--effort", "low", "--aar-provider", "anthropic", "--aar-model", "claude-sonnet-5-5"] and Array(GameSettings.launch_args({})) == ["--harness", "default", "--lang", "zh-TW"], "啟動引數")
	h.check(GameSettings.key_status_text("anthropic", {"anthropic": true}) == "已設定（在 m0/.env）" and GameSettings.key_status_text("anthropic", {}) == "未設定（請填 m0/.env）" and GameSettings.key_status_text("fake", {}) == "不需要金鑰" and GameSettings.key_status_text("ollama", {"ollama": false}).begins_with("OLLAMA_HOST 未設定"), "金鑰狀態只有已設定／未設定")
	h.check(GameSettings.is_local_provider("ollama") and GameSettings.is_local_provider("fake") and not GameSettings.is_local_provider("anthropic"), "本地供應商判斷")

	# ---- CostHud ----
	h.check(CostHud.state(0.0, -1.0, false) == "ok" and CostHud.state(0.5, 1.0, false) == "ok" and CostHud.state(0.8, 1.0, false) == "warn" and CostHud.state(1.0, 1.0, false) == "paused" and CostHud.state(0.0, -1.0, true) == "paused", "80% 黃、100%／服務說暫停 → 紅")
	var txt := CostHud.text_for({"cost": 0.0123, "today": 0.5, "month": 2.0, "budget": 1.0, "local": false})
	h.check(txt == "本場 $0.0123｜今天 $0.50｜本月 $2.00｜預算 $1.00", "費用文字：%s" % txt)
	h.check(CostHud.text_for({"cost": 0.0, "today": 0.0, "month": 0.0, "budget": -1.0, "local": true, "tokens": 1234, "latency_s": 2.5}) == "本場 $0.0000｜今天 $0.00｜本月 $0.00｜本地 1234 token／2.5 秒", "本地模型顯示 token 與秒數")
	h.check(CostHud.text_for({"cost": 1.0, "budget": 1.0}).ends_with("已達預算，參謀長暫停") and CostHud.text_for({"cost": 0.85, "budget": 1.0}).ends_with("預算已用 80%"), "暫停／80% 提示文字")
	var hud := CostHud.new()
	get_root().add_child(hud)
	hud.update({"cost": 1.0, "budget": 1.0})
	h.check(hud.last_state == "paused" and hud.get_theme_color("font_color") == CostHud.COLOR_PAUSED, "HUD 顏色紅")
	hud.update({"cost": 0.1, "budget": 1.0})
	h.check(hud.last_state == "ok" and hud.get_theme_color("font_color") == CostHud.COLOR_OK, "HUD 顏色回白")
	hud.queue_free()

	# ---- SettingsPage ----
	var page := SettingsPage.new()
	get_root().add_child(page)
	h.check(not page.visible and page.provider_opt.item_count == GameSettings.PROVIDERS.size() and page.lang_opt.item_count == 3, "設定頁預設隱藏、選項齊")
	page.open(good, {"anthropic": false})
	h.check(page.visible and GameSettings.PROVIDERS[page.provider_opt.selected] == "anthropic" and page.model_edit.text == "claude-haiku-5-5" and page.budget_spin.value == 0.5 and page.key_label.text == "金鑰：未設定（請填 m0/.env）", "open 填入控制項、金鑰狀態")
	page.set_key_flags({"anthropic": true})
	h.check(page.key_label.text == "金鑰：已設定（在 m0/.env）", "/health 的 keys 更新金鑰狀態")
	page.model_edit.text = "  claude-opus-5-5 "
	page.budget_spin.value = 2.0
	page.lang_opt.select(2)
	var got: Array = []
	page.saved.connect(func(s: Dictionary) -> void: got.append(s))
	page.save_btn.pressed.emit()
	h.check(got.size() == 1 and got[0]["model"] == "claude-opus-5-5" and got[0]["budget_usd"] == 2.0 and got[0]["lang"] == "en" and got[0]["provider"] == "anthropic", "儲存 → saved(正規化後的設定)")
	page.close_btn.pressed.emit()
	h.check(not page.visible, "關閉")
	page.queue_free()

	# ---- 字串表：程式用到的鍵都在、三語齊、% 數一致 ----
	var used := {}
	_scan_keys(ProjectSettings.globalize_path("res://scripts"), used)
	var missing: Array[String] = []
	for k in used.keys():
		if not UiText.keys.has(k):
			missing.append(k)
	h.check(used.size() > 80 and missing.is_empty(), "程式用到 %d 個 UI_ 鍵全部在 ui.csv（缺：%s）" % [used.size(), ", ".join(missing)])
	var bad: Array[String] = []
	var re := RegEx.new()
	re.compile("%(?:\\.\\d+)?[dsf]")
	for k in UiText.keys:
		var counts: Array[int] = []
		for lang in ["zh_TW", "zh_CN", "en"]:
			TranslationServer.set_locale(lang)
			var t := TranslationServer.translate(k)
			if t == k:
				bad.append(k + "@" + lang)
			counts.append(re.search_all(t).size())
		if counts[0] != counts[1] or counts[1] != counts[2]:
			bad.append(k + "(%)")
	UiText.set_lang("zh-TW")
	h.check(bad.is_empty(), "每個鍵三語都有、佔位數一致（壞：%s）" % ", ".join(bad))

	# ---- Battle：設定載入、Esc、語言即時切換、費用 HUD ----
	var scene: PackedScene = load("res://scenes/Battle.tscn")
	var b: Battle = scene.instantiate()
	b.auto_advance = false; b.use_cmdline_args = false; b.board_out = ""; b.snapshot_dir = ""; b.chief_autostart = false; b.friendly_path = ""
	b.settings_path = "user://settings_test_battle.json"
	if FileAccess.file_exists(b.settings_path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(b.settings_path))
	get_root().add_child(b)
	await process_frame
	await physics_frame
	await physics_frame
	h.check(b.settings_page != null and not b.settings_page.visible and b.cost_hud != null and b.cost_hud.text.begins_with("本場 $0.0000"), "HUD 有設定頁（隱藏）與費用 HUD")
	h.check(b.hud_label.text.contains("FPS") and b.hud_label.text.contains("剩 300 秒") and b.hud_label.text.ends_with("空白鍵＝A 連奪取 C3｜R 重開｜Esc 設定"), "HUD 狀態行走字串表（zh-TW）")
	b.toggle_settings()
	h.check(b.settings_page.visible and b.flow.unit_id == "", "Esc → 設定頁開")
	b.toggle_settings()
	h.check(not b.settings_page.visible, "再 Esc → 關")
	var en := GameSettings.normalize({"provider": "fake", "lang": "en", "budget_usd": 0.5})
	var old_sidebar := b.sidebar
	await b.apply_settings(en)
	h.check(b.chief_lang == "en" and b.chief_budget == 0.5 and TranslationServer.get_locale().begins_with("en") and GameSettings.load(b.settings_path)["lang"] == "en", "儲存：語言／預算改了、存進檔")
	h.check(b.sidebar != old_sidebar and b.sidebar.toggle_btn.text == "Collapse ▶" and b.panel.task_buttons["seize"].text == "Seize" and b.hud_label.text.contains("300 s left") and b.cost_hud.text.begins_with("This battle"), "整個 UI 重建成英文（側欄、面板、HUD、費用）")
	await b.apply_settings(GameSettings.normalize({"provider": "fake", "lang": "zh-TW"}))
	h.check(b.sidebar.toggle_btn.text == "收合側欄 ▶" and b.chief_budget == -1.0, "切回中文、取消預算")
	b.queue_free()
	await process_frame

	# ---- 真的啟動服務：儲存預算 0 → /settings → 下一拍暫停 → 費用 HUD 紅 ----
	var b2: Battle = scene.instantiate()
	b2.auto_advance = false; b2.use_cmdline_args = false; b2.board_out = ""; b2.snapshot_dir = ""; b2.chief_autostart = false; b2.friendly_path = ""
	b2.settings_path = "user://settings_test_battle2.json"
	b2.chief_provider = "fake"
	b2.chief_extra = PackedStringArray(["--out-root", ProjectSettings.globalize_path("user://settings_test_out"), "--ledger", "none"])
	get_root().add_child(b2)
	await process_frame
	await physics_frame
	await physics_frame
	var started: bool = await b2.start_chief()
	h.check(started and b2.key_flags.has("anthropic") and b2.settings_page.key_label.text.begins_with("金鑰："), "服務上線並拿到金鑰狀態（/health keys）")
	await b2.apply_settings(GameSettings.normalize({"provider": "fake", "lang": "zh-TW", "budget_usd": 0.0}))
	h.check(b2.orbat.events.back()["text"].begins_with("設定已套用"), "儲存 → POST /settings → 事件「設定已套用」")
	b2.director.tick(1.0 / 60.0)
	b2.chief_update()
	while b2.chief.busy or b2.scheduler.in_flight:
		await process_frame
	h.check(b2.chief_ticks == 1 and b2.cost_hud.last_state == "paused" and b2.cost_hud.text.ends_with("已達預算，參謀長暫停"), "預算 0 → 第 1 拍就達預算 → HUD 紅「參謀長暫停」")
	var st: Dictionary = await b2.poll_status()
	h.check(st["code"] == 200 and b2.status_today >= 0.0 and b2.cost_hud.text.contains("今天 $"), "GET /status → 今天／本月進 HUD")
	await b2.chief.stop()
	b2.queue_free()
	await process_frame
	h.finish()
