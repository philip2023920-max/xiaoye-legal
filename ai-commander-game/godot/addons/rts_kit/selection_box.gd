extends Control
## Draws the drag box for an [RTSSelection]. Created by it; not used directly.

var selection: RTSSelection
var _was_dragging: bool = false

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)

func _process(_delta: float) -> void:
	var dragging := selection != null and selection.is_dragging()
	if dragging or _was_dragging:
		queue_redraw()
	_was_dragging = dragging

func _draw() -> void:
	if selection == null or not selection.is_dragging():
		return
	var rect := selection.drag_rect()
	draw_rect(rect, selection.box_fill, true)
	draw_rect(rect, selection.box_border, false, 1.5)
