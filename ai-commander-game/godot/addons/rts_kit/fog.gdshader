shader_type spatial;
// The shroud over ground none of your side can see.
//
// One full-screen pass drawn over everything. Each pixel reads the depth buffer
// to find the point in the world it is actually showing, then looks that point
// up in the vision masks. Fogging by the depth buffer rather than by darkening
// the ground shader means units and scenery standing in the dark are shrouded
// too, not lit up like noon on black ground.
//
// Two masks, because "never seen" and "seen a while ago" differ: unexplored
// ground is solid, while remembered ground stays dimly legible so the shape of
// the map you have walked over stays with you.
render_mode unshaded, blend_mix, cull_disabled, depth_draw_never, depth_test_disabled, fog_disabled, shadows_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;
uniform sampler2D visible_tex : filter_linear, repeat_disable, hint_default_white;
uniform sampler2D explored_tex : filter_linear, repeat_disable, hint_default_white;
uniform vec2 world_origin = vec2(-100.0, -100.0);
uniform vec2 world_size = vec2(200.0, 200.0);
uniform float unexplored_alpha : hint_range(0.0, 1.0) = 1.0;
uniform float remembered_alpha : hint_range(0.0, 1.0) = 0.6;
uniform vec3 fog_color : source_color = vec3(0.02, 0.025, 0.03);

void vertex() {
	// A 2x2 quad pinned to the screen, whatever the camera does.
	POSITION = vec4(VERTEX.xy, 1.0, 1.0);
}

void fragment() {
	float depth = texture(depth_tex, SCREEN_UV).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec3 ndc = vec3(SCREEN_UV, depth) * 2.0 - 1.0;
#else
	vec3 ndc = vec3(SCREEN_UV * 2.0 - 1.0, depth);
#endif
	vec4 view = INV_PROJECTION_MATRIX * vec4(ndc, 1.0);
	view.xyz /= view.w;
	vec3 world = (INV_VIEW_MATRIX * vec4(view.xyz, 1.0)).xyz;

	vec2 uv = (world.xz - world_origin) / world_size;
	// Off the map (and the sky) there is nothing to shroud.
	float inside = step(0.0, uv.x) * step(uv.x, 1.0) * step(0.0, uv.y) * step(uv.y, 1.0);

	float seen = texture(visible_tex, uv).r;
	float known = texture(explored_tex, uv).r;
	float a = mix(unexplored_alpha, remembered_alpha, known);
	a = mix(a, 0.0, seen);
	ALBEDO = fog_color;
	ALPHA = a * inside;
}
