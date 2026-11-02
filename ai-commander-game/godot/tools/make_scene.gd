extends SceneTree
## 產生 scenes/Battle.tscn（根節點 Node3D 掛 battle.gd）。用程式產生是為了拿到合法的 uid。
##   godot --headless --path . -s tools/make_scene.gd
func _initialize() -> void:
	var node := Node3D.new()
	node.name = "Battle"
	node.set_script(load("res://scripts/battle/battle.gd"))
	var packed := PackedScene.new()
	packed.pack(node)
	var err := ResourceSaver.save(packed, "res://scenes/Battle.tscn")
	if err == OK and ResourceLoader.get_resource_uid("res://scenes/Battle.tscn") == ResourceUID.INVALID_ID:
		ResourceSaver.set_uid("res://scenes/Battle.tscn", ResourceUID.create_id())   # 讓場景有穩定 uid，編輯器開了不會再改檔
	print("Battle.tscn saved, err=%d" % err)
	quit(0 if err == OK else 1)
