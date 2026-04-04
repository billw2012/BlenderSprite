"""
spriteloom_addon.py — SpriteLoom Blender Addon

Install via: Edit > Preferences > Add-ons > Install... > select this file

Adds a "SpriteLoom" tab in the 3D Viewport N-panel with a
"Render All" button that runs the full render pipeline.
"""

import math
import os

# ---------------------------------------------------------------------------
# CONFIGURATION — edit these values before rendering
# ---------------------------------------------------------------------------

# All 16 directions in order — subsets are taken by stepping through this list
_ALL_DIRECTIONS = [
    ("south",     math.pi),
    ("southwest", 5 * math.pi / 4),
    ("west",      3 * math.pi / 2),
    ("northwest", 7 * math.pi / 4),
    ("north",     0),
    ("northeast", math.pi / 4),
    ("east",      math.pi / 2),
    ("southeast", 3 * math.pi / 4),
    ("ssw",       9 * math.pi / 8),
    ("wsw",       11 * math.pi / 8),
    ("wnw",       13 * math.pi / 8),
    ("nnw",       15 * math.pi / 8),
    ("nne",       math.pi / 8),
    ("ene",       3 * math.pi / 8),
    ("ese",       5 * math.pi / 8),
    ("sse",       7 * math.pi / 8),
]

_DIRECTION_COUNTS = {
    "1":  [("south", math.pi)],
    "4":  [("south", math.pi), ("west", 3*math.pi/2), ("north", 0), ("east", math.pi/2)],
    "8":  [("south", math.pi), ("southwest", 5*math.pi/4), ("west", 3*math.pi/2),
           ("northwest", 7*math.pi/4), ("north", 0), ("northeast", math.pi/4),
           ("east", math.pi/2), ("southeast", 3*math.pi/4)],
    "16": _ALL_DIRECTIONS,
}


def _get_directions(num_directions_str):
    return _DIRECTION_COUNTS.get(num_directions_str, _DIRECTION_COUNTS["8"])

FRAME_WIDTH = 64
FRAME_HEIGHT = 64
FRAME_DURATION_MS = 100
FRAME_DURATION_OVERRIDES = {}  # e.g. {"chr_run": 80, "chr_idle": 150}

# ---------------------------------------------------------------------------
# END CONFIGURATION
# ---------------------------------------------------------------------------

import bpy


def _log(msg):
    print(f"[SpriteLoom] {msg}", flush=True)


def _resolve_view_layers(scene, filter_str):
    """Return view layer objects to render. filter_str is a CSV of EXCLUDED layers; empty = all included."""
    if filter_str.strip():
        excluded = {n.strip() for n in filter_str.split(",") if n.strip()}
        return [vl for vl in scene.view_layers if vl.name not in excluded]
    return list(scene.view_layers)


def _resolve_path(prop_value):
    """Return an absolute path. Supports // Blender-relative paths. Returns '' if unresolvable."""
    if not prop_value:
        return ""
    if prop_value.startswith("//") and not bpy.data.filepath:
        return ""
    return bpy.path.abspath(prop_value)


def _frame_filename(action_name, layer_name, direction_name, frame):
    """Canonical flat filename for a rendered frame. Uses -- to separate semantic parts."""
    return f"{action_name}--{layer_name}--{direction_name}--{frame:04d}.png"


def _count_existing_frames(export_root, action_name, layer_name, direction_name):
    if not os.path.isdir(export_root):
        return 0
    prefix = f"{action_name}--{layer_name}--{direction_name}--"
    return len([f for f in os.listdir(export_root) if f.startswith(prefix) and f.lower().endswith(".png")])



def _row_key(f, row_split_by_action, row_split_by_layer, row_split_by_direction):
    parts = []
    if row_split_by_action:    parts.append(f["action"])
    if row_split_by_layer:     parts.append(f["layer"])
    if row_split_by_direction: parts.append(f["direction"])
    return tuple(parts)


def _pack_sheet(np, spritesheet_root, sheet_name, frames,
                row_split_by_action, row_split_by_layer, row_split_by_direction):
    """
    Pack a list of frame dicts into one sprite sheet, optionally split into rows.
    Each frame dict: {"filepath": str, "action": str, "layer": str, "direction": str, "frame_num": int}
    Returns True on success.
    """
    import json

    frames = sorted(frames, key=lambda f: (f["action"], f["layer"], f["direction"], f["frame_num"]))
    if not frames:
        _log(f"  WARNING: No frames for sheet '{sheet_name}' — skipping.")
        return False

    # Group into rows
    rows_ordered = []
    rows_map = {}
    for f in frames:
        key = _row_key(f, row_split_by_action, row_split_by_layer, row_split_by_direction)
        if key not in rows_map:
            rows_map[key] = []
            rows_ordered.append(key)
        rows_map[key].append(f)

    num_rows = len(rows_ordered)
    cols = max(len(rows_map[k]) for k in rows_ordered)
    sheet_w = FRAME_WIDTH * cols
    sheet_h = FRAME_HEIGHT * num_rows

    sheet_png = os.path.join(spritesheet_root, f"{sheet_name}.png")
    sheet_json = os.path.join(spritesheet_root, f"{sheet_name}.json")
    _log(f"  Packing {sheet_name}: {len(frames)} frame(s) in {num_rows} row(s) × {cols} col(s)")

    sheet_arr = np.zeros((sheet_h, sheet_w, 4), dtype=np.float32)
    frames_meta = {}

    for row_idx, key in enumerate(rows_ordered):
        y_px = row_idx * FRAME_HEIGHT
        for col_idx, f in enumerate(rows_map[key]):
            filepath = f["filepath"]
            filename = os.path.basename(filepath)
            try:
                img = bpy.data.images.load(filepath)
            except Exception as exc:
                _log(f"    WARNING: Could not load {filename}: {exc} — skipping.")
                continue

            if img.size[0] != FRAME_WIDTH or img.size[1] != FRAME_HEIGHT:
                _log(f"    WARNING: {filename} is {img.size[0]}x{img.size[1]}, "
                     f"expected {FRAME_WIDTH}x{FRAME_HEIGHT}.")

            arr = np.array(img.pixels, dtype=np.float32).reshape(img.size[1], img.size[0], 4)
            bpy.data.images.remove(img)

            x_px = col_idx * FRAME_WIDTH
            sheet_arr[y_px:y_px + FRAME_HEIGHT, x_px:x_px + FRAME_WIDTH, :] = arr[:FRAME_HEIGHT, :FRAME_WIDTH, :]

            sprite_name = f"{f['action']}_{f['layer']}_{f['direction']}_{f['frame_num']:04d}"
            frames_meta[sprite_name] = {
                "frame": {"x": x_px, "y": y_px, "w": FRAME_WIDTH, "h": FRAME_HEIGHT},
                "rotated": False,
                "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": FRAME_WIDTH, "h": FRAME_HEIGHT},
                "sourceSize": {"w": FRAME_WIDTH, "h": FRAME_HEIGHT},
                "duration": FRAME_DURATION_OVERRIDES.get(f["action"], FRAME_DURATION_MS),
            }

    sheet_img = bpy.data.images.new(sheet_name, width=sheet_w, height=sheet_h, alpha=True)
    sheet_img.pixels = sheet_arr.flatten().tolist()
    sheet_img.filepath_raw = sheet_png
    sheet_img.file_format = "PNG"
    try:
        sheet_img.save()
    except Exception as exc:
        _log(f"  ERROR saving {sheet_png}: {exc}")
        bpy.data.images.remove(sheet_img)
        return False
    bpy.data.images.remove(sheet_img)

    meta = {
        "frames": frames_meta,
        "meta": {
            "app": "SpriteLoom",
            "image": os.path.basename(sheet_png),
            "format": "RGBA8888",
            "size": {"w": sheet_w, "h": sheet_h},
            "scale": "1",
        },
    }
    try:
        with open(sheet_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception as exc:
        _log(f"  ERROR writing {sheet_json}: {exc}")
        return False

    return True


def _format_sheet_name(fmt, blendfile="", action="", layer="", direction=""):
    """Substitute placeholders and clean up empty segments."""
    import re
    name = fmt
    name = name.replace("{blendfile}", blendfile)
    name = name.replace("{action}", action)
    name = name.replace("{layer}", layer)
    name = name.replace("{direction}", direction)
    name = re.sub(r'[-_\s]{2,}', lambda m: m.group(0)[0], name)
    name = name.strip("-_ ")
    return name or "spritesheet"


def _run_pack(export_root, spritesheet_root, sheet_name_format,
              split_by_action, split_by_layer, split_by_direction,
              row_split_by_action, row_split_by_layer, row_split_by_direction):
    """Pack all rendered frames into sprite sheets. Returns (generated, skipped, errors)."""
    import numpy as np

    if not os.path.isdir(export_root):
        _log(f"  WARNING: export root not found: {export_root}")
        return 0, 0, 0

    os.makedirs(spritesheet_root, exist_ok=True)
    generated = 0
    errors = 0

    blendfile = os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else "untitled"

    # Parse all flat PNGs: {action}--{layer}--{direction}--{frame:04d}.png
    all_frames = []
    for fname in os.listdir(export_root):
        if not fname.lower().endswith(".png"):
            continue
        stem = fname[:-4]
        parts = stem.split("--")
        if len(parts) != 4 or not parts[3].isdigit():
            continue
        all_frames.append({
            "filepath": os.path.join(export_root, fname),
            "action": parts[0],
            "layer": parts[1],
            "direction": parts[2],
            "frame_num": int(parts[3]),
        })

    if not all_frames:
        _log("  WARNING: No frames found to pack.")
        return 0, 0, 0

    # Group frames into sheets based on split settings
    sheets = {}
    for f in all_frames:
        key = tuple([
            f["action"] if split_by_action else "",
            f["layer"] if split_by_layer else "",
            f["direction"] if split_by_direction else "",
        ])
        sheets.setdefault(key, []).append(f)

    for (action_key, layer_key, direction_key), frames in sorted(sheets.items()):
        sheet_name = _format_sheet_name(
            sheet_name_format,
            blendfile=blendfile,
            action=action_key,
            layer=layer_key,
            direction=direction_key,
        )
        if _pack_sheet(np, spritesheet_root, sheet_name, frames,
                       row_split_by_action, row_split_by_layer, row_split_by_direction):
            generated += 1
        else:
            errors += 1

    return generated, 0, errors



def _get_cloth_objects_in_layer(view_layer):
    """Return mesh objects with a Cloth modifier that are renderable in this view layer."""
    return [
        obj for obj in view_layer.objects
        if not obj.hide_render
        and any(m.type == 'CLOTH' for m in obj.modifiers)
    ]


def _bake_cloth_for_layer_action(context, view_layer, action, warmup_frames):
    """
    Bake cloth for a single (view_layer, action) combination.
    Sets the view layer active so cloth objects are correctly resolved.
    Returns number of objects baked.
    """
    context.window.view_layer = view_layer

    bake_start = int(action.frame_range[0]) - warmup_frames
    bake_end   = int(action.frame_range[1])
    _log(f"  Cloth bake '{action.name}' / '{view_layer.name}': frames {bake_start}→{bake_end} (warmup: {warmup_frames})")

    cloth_objs = _get_cloth_objects_in_layer(view_layer)
    for obj in cloth_objs:
        for mod in obj.modifiers:
            if mod.type != 'CLOTH':
                continue
            mod.point_cache.frame_start = bake_start
            mod.point_cache.frame_end   = bake_end
            with context.temp_override(point_cache=mod.point_cache):
                bpy.ops.ptcache.free_bake()
                bpy.ops.ptcache.bake(bake=True)
        _log(f"    Baked '{obj.name}'")

    return len(cloth_objs)


def _build_job_queue(context, export_root):
    """
    Build the full list of render jobs. Each job is a single frame to render.
    Entire action/layer/direction combos are skipped if all frames already exist.
    Returns (jobs, skipped_count) or (None, error_message) on failure.
    """
    scene = context.scene
    settings = scene.spriteloom

    armature_obj = settings.armature
    if armature_obj is None:
        return None, "No armature selected"

    camera_rig = settings.camera_rig
    if camera_rig is None:
        return None, "No camera rig selected"

    excluded_actions = {n.strip() for n in settings.actions_filter.split(",") if n.strip()}
    chr_actions = [a for a in bpy.data.actions if a.name not in excluded_actions]
    if not chr_actions:
        return None, "No actions to render (none in file or all excluded)"

    view_layers = _resolve_view_layers(scene, settings.view_layers_filter)
    if not view_layers:
        return None, "No view layers to render"

    directions = _get_directions(settings.num_directions)
    frame_step = settings.frame_step
    overwrite = settings.overwrite_frames

    _log(f"Found {len(chr_actions)} action(s): {[a.name for a in chr_actions]}")
    _log(f"View layers : {[vl.name for vl in view_layers]}")
    _log(f"Directions  : {[d[0] for d in directions]}  ({len(directions)})")
    _log(f"Frame step  : {frame_step}")
    _log(f"Overwrite   : {overwrite}")

    jobs = []
    skipped = 0
    for action in chr_actions:
        frame_start = int(action.frame_range[0])
        frame_end = int(action.frame_range[1])
        loop_end = frame_end if action.use_cyclic else frame_end + 1
        frames = list(range(frame_start, loop_end, frame_step))
        expected_frames = len(frames)
        action_has_jobs = False
        action_jobs = []
        os.makedirs(export_root, exist_ok=True)
        for vl in view_layers:
            for direction_name, angle_radians in directions:
                prefix = f"{action.name}--{vl.name}--{direction_name}--"
                if not overwrite and _count_existing_frames(export_root, action.name, vl.name, direction_name) >= expected_frames:
                    _log(f"  SKIP  {action.name}/{vl.name}/{direction_name} ({expected_frames} frames exist)")
                    skipped += 1
                    continue
                if overwrite:
                    for f in os.listdir(export_root):
                        if f.startswith(prefix) and f.lower().endswith(".png"):
                            os.remove(os.path.join(export_root, f))
                    _log(f"  CLEAR {action.name}/{vl.name}/{direction_name}")
                action_has_jobs = True
                for frame in frames:
                    action_jobs.append({
                        "type": "render",
                        "action": action,
                        "vl_name": vl.name,
                        "direction_name": direction_name,
                        "angle_radians": angle_radians,
                        "out_path": os.path.join(export_root, _frame_filename(action.name, vl.name, direction_name, frame)),
                        "frame": frame,
                        "frame_start": frame_start,
                        "frame_end": frame_end,
                        "armature_obj": armature_obj,
                        "camera_rig": camera_rig,
                    })
        if action_has_jobs and settings.bake_cloth:
            for vl in view_layers:
                jobs.append({"type": "bake", "action": action, "vl_name": vl.name})
        jobs.extend(action_jobs)
    return jobs, skipped


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class SpriteLoomSettings(bpy.types.PropertyGroup):
    armature: bpy.props.PointerProperty(  # type: ignore
        name="Armature",
        description="Armature to render actions from",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )
    camera_rig: bpy.props.PointerProperty(  # type: ignore
        name="Camera Rig",
        description="Empty (or object) to rotate for direction changes",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'EMPTY',
    )
    num_directions: bpy.props.EnumProperty(  # type: ignore
        name="Directions",
        description="Number of render directions",
        items=[
            ("1",  "1 — South only",  ""),
            ("4",  "4 — Cardinal",    ""),
            ("8",  "8 — Octagonal",   ""),
            ("16", "16 — Full",       ""),
        ],
        default="8",
    )
    actions_filter: bpy.props.StringProperty(  # type: ignore
        name="Actions",
        description="Comma-separated action names to EXCLUDE from rendering. Leave blank to render all",
        default="",
    )
    frame_step: bpy.props.IntProperty(  # type: ignore
        name="Frame Step",
        description="Render every Nth frame (1 = all frames)",
        default=1,
        min=1,
        max=64,
    )
    view_layers_filter: bpy.props.StringProperty(  # type: ignore
        name="View Layers",
        description="Comma-separated view layers to render. Leave blank to render all",
        default="",
    )
    bake_cloth: bpy.props.BoolProperty(  # type: ignore
        name="Bake Cloth",
        description="Bake cloth simulations before rendering",
        default=False,
    )
    cloth_warmup_frames: bpy.props.IntProperty(  # type: ignore
        name="Warmup Frames",
        description="Extra frames before the first action frame for cloth to settle",
        default=20,
        min=0,
        max=500,
    )
    clean_output: bpy.props.BoolProperty(  # type: ignore
        name="Clean Before Render",
        description="Delete all files in the export directory before starting a new render",
        default=False,
    )
    overwrite_frames: bpy.props.BoolProperty(  # type: ignore
        name="Overwrite Existing Frames",
        description="Re-render and overwrite frames that already exist on disk (instead of skipping them)",
        default=False,
    )
    sheet_name_format: bpy.props.StringProperty(  # type: ignore
        name="Name Format",
        description="Filename format for sprite sheets. Placeholders: {blendfile} {action} {layer} {direction}",
        default="{blendfile}-{layer}-{action}-{direction}",
    )
    split_by_action: bpy.props.BoolProperty(  # type: ignore
        name="Action",
        description="Generate a separate sprite sheet per action",
        default=True,
    )
    split_by_layer: bpy.props.BoolProperty(  # type: ignore
        name="Layer",
        description="Generate a separate sprite sheet per view layer",
        default=True,
    )
    split_by_direction: bpy.props.BoolProperty(  # type: ignore
        name="Direction",
        description="Generate a separate sprite sheet per direction",
        default=False,
    )
    row_split_by_action: bpy.props.BoolProperty(  # type: ignore
        name="Action",
        description="Each action gets its own row",
        default=False,
    )
    row_split_by_layer: bpy.props.BoolProperty(  # type: ignore
        name="Layer",
        description="Each view layer gets its own row",
        default=False,
    )
    row_split_by_direction: bpy.props.BoolProperty(  # type: ignore
        name="Direction",
        description="Each direction gets its own row",
        default=True,
    )
    show_scene_setup: bpy.props.BoolProperty(default=True)  # type: ignore
    show_render: bpy.props.BoolProperty(default=True)  # type: ignore
    show_output: bpy.props.BoolProperty(default=True)  # type: ignore
    show_sheet_layout: bpy.props.BoolProperty(default=True)  # type: ignore
    progress: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})  # type: ignore
    progress_factor: bpy.props.FloatProperty(default=0.0, options={'SKIP_SAVE'})  # type: ignore
    last_result: bpy.props.StringProperty(default="")  # type: ignore
    export_root: bpy.props.StringProperty(  # type: ignore
        name="Export Root",
        description="Folder for rendered frames. // paths are relative to the .blend file",
        subtype='DIR_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'},
        default="//export",
    )
    spritesheet_root: bpy.props.StringProperty(  # type: ignore
        name="Spritesheet Root",
        description="Folder for packed sprite sheets. // paths are relative to the .blend file",
        subtype='DIR_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'},
        default="//spritesheets",
    )


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class SPRITELOOM_OT_RenderAll(bpy.types.Operator):
    """Render all chr_ actions × view layers × directions to disk"""

    bl_idname = "spriteloom.render_all"
    bl_label = "Render All"
    bl_options = {"REGISTER"}

    _timer = None
    _jobs = []
    _job_index = 0
    _render_total = 0
    _skipped = 0
    _rendered = 0
    _errors = 0
    _export_root = ""
    _spritesheet_root = ""

    def execute(self, context):
        settings = context.scene.spriteloom
        self._export_root = _resolve_path(settings.export_root)
        self._spritesheet_root = _resolve_path(settings.spritesheet_root)

        if not self._export_root:
            self.report({"ERROR"}, "Save the .blend file first, or set an explicit Export Root path.")
            return {"CANCELLED"}

        _log("=== SpriteLoom: Render All started ===")
        _log(f"Export root     : {self._export_root}")
        _log(f"Spritesheet root: {self._spritesheet_root}")

        if settings.clean_output and os.path.isdir(self._export_root):
            removed = 0
            for fname in os.listdir(self._export_root):
                fpath = os.path.join(self._export_root, fname)
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    removed += 1
            _log(f"Clean: removed {removed} file(s) from {self._export_root}")

        jobs, result = _build_job_queue(context, self._export_root)
        if jobs is None:
            self.report({"ERROR"}, result)
            return {"CANCELLED"}

        self._jobs = jobs
        self._skipped = result
        self._job_index = 0
        self._render_total = sum(1 for j in jobs if j["type"] == "render")
        self._rendered = 0
        self._errors = 0
        self._orig_frame = context.scene.frame_current
        self._orig_camera_rig_z = settings.camera_rig.rotation_euler.z if settings.camera_rig else None

        if not jobs:
            _log("Nothing to render — all jobs skipped.")
            self._finish(context)
            return {"FINISHED"}

        context.scene.spriteloom.last_result = ""
        context.window_manager.progress_begin(0, self._render_total)
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        # Redraw the panel each tick so progress updates are visible
        for area in context.screen.areas:
            area.tag_redraw()

        if event.type == "ESC":
            return self.cancel(context)

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._job_index >= len(self._jobs):
            self._finish(context)
            return {"FINISHED"}

        job = self._jobs[self._job_index]

        if job["type"] == "bake":
            action = job["action"]
            settings = context.scene.spriteloom
            context.scene.spriteloom.progress = f"Baking cloth: {action.name}..."
            for area in context.screen.areas:
                area.tag_redraw()
            _log(f"=== Baking cloth for '{action.name}' ===")
            armature_obj = settings.armature
            if armature_obj and armature_obj.animation_data:
                armature_obj.animation_data.action = action
            view_layer = context.scene.view_layers.get(job["vl_name"])
            if view_layer:
                _bake_cloth_for_layer_action(context, view_layer, action, settings.cloth_warmup_frames)
            _log(f"=== Cloth bake done ===")
            self._job_index += 1
            return {"RUNNING_MODAL"}

        scene = context.scene
        action = job["action"]
        armature_obj = job["armature_obj"]
        camera_rig = job["camera_rig"]
        frame = job["frame"]
        frame_num = frame - job["frame_start"] + 1
        frame_total = job["frame_end"] - job["frame_start"] + 1

        label = f"{action.name} / {job['vl_name']} / {job['direction_name']}"
        scene.spriteloom.progress = (
            f"{label}  frame {frame_num}/{frame_total}  "
            f"({self._rendered + 1}/{self._render_total})"
        )
        scene.spriteloom.progress_factor = self._rendered / self._render_total if self._render_total else 0.0
        context.window_manager.progress_update(self._rendered)

        if armature_obj.animation_data is None:
            armature_obj.animation_data_create()
        armature_obj.animation_data.action = action

        camera_rig.rotation_euler.z = job["angle_radians"]
        scene.frame_set(frame)
        out_path = job["out_path"]

        _log(
            f"  RENDER  action={action.name}  layer={job['vl_name']}  "
            f"dir={job['direction_name']}  frame={frame}  "
            f"cam_z={camera_rig.rotation_euler.z:.3f}"
        )

        fmt = scene.render.image_settings
        orig_filepath = scene.render.filepath
        orig_media_type = fmt.media_type
        orig_file_format = fmt.file_format

        # Point all R_LAYERS compositor nodes at the target view layer
        nt = scene.compositing_node_group
        rl_orig = {}
        if nt:
            for node in nt.nodes:
                if node.type == 'R_LAYERS':
                    rl_orig[node.name] = node.layer
                    node.layer = job["vl_name"]

        try:
            scene.render.filepath = out_path
            fmt.media_type = "IMAGE"
            fmt.file_format = "PNG"
            bpy.ops.render.render("EXEC_DEFAULT", write_still=True, layer=job["vl_name"])
            _log(f"    OK  saved={out_path}")
            self._rendered += 1
        except Exception as exc:
            _log(f"    ERROR {label} frame {frame}: {exc}")
            self._errors += 1
        finally:
            scene.render.filepath = orig_filepath
            fmt.media_type = orig_media_type
            fmt.file_format = orig_file_format
            if nt:
                for node in nt.nodes:
                    if node.type == 'R_LAYERS' and node.name in rl_orig:
                        node.layer = rl_orig[node.name]

        self._job_index += 1
        return {"RUNNING_MODAL"}

    def _restore_scene(self, context):
        context.scene.frame_set(self._orig_frame)
        settings = context.scene.spriteloom
        if settings.camera_rig and self._orig_camera_rig_z is not None:
            settings.camera_rig.rotation_euler.z = self._orig_camera_rig_z

    def cancel(self, context):
        _log("=== SpriteLoom: Cancelled ===")
        self._restore_scene(context)
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            context.window_manager.progress_end()
        context.scene.spriteloom.progress = ""
        context.scene.spriteloom.progress_factor = 0.0
        context.scene.spriteloom.last_result = (
            f"Cancelled after {self._rendered} rendered, {self._skipped} skipped, {self._errors} errors"
        )
        return {"CANCELLED"}

    def _finish(self, context):
        self._restore_scene(context)
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            context.window_manager.progress_end()
        context.scene.spriteloom.progress = ""
        context.scene.spriteloom.progress_factor = 0.0

        _log(f"\n=== Render complete — rendered {self._rendered}, skipped {self._skipped}, errors {self._errors} ===")
        _log("=== SpriteLoom: Packing sprites ===")

        settings = context.scene.spriteloom
        packed, pack_skipped, pack_errors = _run_pack(
            self._export_root, self._spritesheet_root,
            settings.sheet_name_format,
            settings.split_by_action, settings.split_by_layer, settings.split_by_direction,
            settings.row_split_by_action, settings.row_split_by_layer, settings.row_split_by_direction,
        )

        _log(f"=== Pack complete — generated {packed}, skipped {pack_skipped}, errors {pack_errors} ===")

        total_errors = self._errors + pack_errors
        context.scene.spriteloom.last_result = "\n".join([
            f"Rendered: {self._rendered}  Skipped: {self._skipped}  Errors: {self._errors}",
            f"Sheets: {packed}  Skipped: {pack_skipped}  Errors: {pack_errors}",
        ])
        self.report({"WARNING"} if total_errors > 0 else {"INFO"},
                    f"Render {self._rendered} | Pack {packed} | Errors {total_errors}")


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class SPRITELOOM_PT_Main(bpy.types.Panel):
    """SpriteLoom main sidebar panel"""

    bl_label = "SpriteLoom"
    bl_idname = "SPRITELOOM_PT_Main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SpriteLoom"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.spriteloom
        scene = context.scene

        if settings.armature is None or settings.camera_rig is None:
            if not bpy.app.timers.is_registered(_auto_detect_all):
                bpy.app.timers.register(_auto_detect_all, first_interval=0.0)

        # --- Scene Setup ---
        box = layout.box()
        row = box.row()
        row.prop(settings, "show_scene_setup", icon="TRIA_DOWN" if settings.show_scene_setup else "TRIA_RIGHT", emboss=False, text="Scene Setup", icon_only=False)
        row.label(icon="SCENE_DATA")
        if settings.show_scene_setup:
            box.prop(settings, "armature")
            box.prop(settings, "camera_rig")

        # --- Render Settings ---
        box = layout.box()
        row = box.row()
        row.prop(settings, "show_render", icon="TRIA_DOWN" if settings.show_render else "TRIA_RIGHT", emboss=False, text="Render", icon_only=False)
        row.label(icon="RENDER_ANIMATION")
        if settings.show_render:
            box.prop(settings, "num_directions")
            box.prop(settings, "frame_step")
            actions_box = box.box()
            actions_box.label(text="Actions", icon="ACTION")
            all_actions = list(bpy.data.actions)
            if all_actions:
                excluded_actions = {n.strip() for n in settings.actions_filter.split(",") if n.strip()}
                col = actions_box.column(align=True)
                col.scale_y = 0.75
                for a in all_actions:
                    frame_start = int(a.frame_range[0])
                    frame_end = int(a.frame_range[1])
                    loop_end = frame_end if a.use_cyclic else frame_end + 1
                    frame_count = len(range(frame_start, loop_end, settings.frame_step))
                    is_on = a.name not in excluded_actions
                    loop_suffix = "  \u21ba" if a.use_cyclic else ""
                    row = col.row(align=True)
                    op = row.operator("spriteloom.toggle_action",
                                      text=f"{a.name}  ({frame_count} frames){loop_suffix}",
                                      icon='CHECKBOX_HLT' if is_on else 'CHECKBOX_DEHLT',
                                      emboss=False)
                    op.action_name = a.name
                    nav = row.operator("spriteloom.focus_action", text="", icon='LINKED', emboss=False)
                    nav.action_name = a.name
            else:
                actions_box.label(text="No actions in file", icon='INFO')
            row = box.row(align=True)
            row.prop(settings, "bake_cloth")
            if settings.bake_cloth:
                row.prop(settings, "cloth_warmup_frames")

        # --- Output Paths ---
        box = layout.box()
        row = box.row()
        row.prop(settings, "show_output", icon="TRIA_DOWN" if settings.show_output else "TRIA_RIGHT", emboss=False, text="Output", icon_only=False)
        row.label(icon="FILE_FOLDER")
        if settings.show_output:
            layers_box = box.box()
            layers_box.label(text="View Layers", icon="RENDERLAYERS")
            excluded = {n.strip() for n in settings.view_layers_filter.split(",") if n.strip()}
            col = layers_box.column(align=True)
            col.scale_y = 0.75
            for vl in scene.view_layers:
                is_on = vl.name not in excluded
                row = col.row(align=True)
                op = row.operator("spriteloom.toggle_view_layer",
                                   text=vl.name,
                                   icon='CHECKBOX_HLT' if is_on else 'CHECKBOX_DEHLT',
                                   emboss=False)
                op.layer_name = vl.name
                act = row.operator("spriteloom.activate_view_layer", text="", icon='LINKED', emboss=False)
                act.layer_name = vl.name
            box.prop(settings, "export_root")
            box.prop(settings, "spritesheet_root")
            box.prop(settings, "clean_output")
            box.prop(settings, "overwrite_frames")

        # --- Sheet Layout ---
        box = layout.box()
        row = box.row()
        row.prop(settings, "show_sheet_layout", icon="TRIA_DOWN" if settings.show_sheet_layout else "TRIA_RIGHT", emboss=False, text="Sheet Layout", icon_only=False)
        row.label(icon="IMAGE_DATA")
        if settings.show_sheet_layout:
            box.label(text="File splits:")
            row = box.row(align=True)
            row.prop(settings, "split_by_layer")
            row.prop(settings, "split_by_action")
            row.prop(settings, "split_by_direction")

            box.label(text="Row splits:")
            row = box.row(align=True)
            sub = row.row()
            sub.enabled = not settings.split_by_layer
            sub.prop(settings, "row_split_by_layer")
            sub = row.row()
            sub.enabled = not settings.split_by_action
            sub.prop(settings, "row_split_by_action")
            sub = row.row()
            sub.enabled = not settings.split_by_direction
            sub.prop(settings, "row_split_by_direction")

            box.separator(factor=0.5)
            box.prop(settings, "sheet_name_format")
            col = box.column(align=True)
            col.scale_y = 0.7
            col.label(text="{blendfile}  {action}  {layer}  {direction}", icon='INFO')

            box.separator(factor=0.5)
            box.label(text="Example output:")
            blendfile = os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else "untitled"
            _ex_excluded = {n.strip() for n in settings.actions_filter.split(",") if n.strip()}
            example_actions = [a.name for a in bpy.data.actions if a.name not in _ex_excluded] or ["chr_walk", "chr_idle"]
            example_layers = [vl.name for vl in _resolve_view_layers(scene, settings.view_layers_filter)] or ["Layer"]
            example_directions = [d[0] for d in _get_directions(settings.num_directions)]
            seen = []
            for action in example_actions:
                for layer in example_layers:
                    for direction in (example_directions if settings.split_by_direction else [""]):
                        name = _format_sheet_name(
                            settings.sheet_name_format,
                            blendfile=blendfile,
                            action=action if settings.split_by_action else "",
                            layer=layer if settings.split_by_layer else "",
                            direction=direction if settings.split_by_direction else "",
                        )
                        if name not in seen:
                            seen.append(name)
            col = box.column(align=True)
            col.scale_y = 0.75
            for name in seen[:5]:
                col.label(text=f"{name}.png", icon='FILE_IMAGE')
            if len(seen) > 5:
                col.label(text=f"+{len(seen) - 5} more…", icon='BLANK1')

        # --- Validation warnings ---
        issues = []

        if settings.armature is None:
            issues.append(("ERROR", "No armature selected"))
        if settings.camera_rig is None:
            issues.append(("ERROR", "No camera rig selected"))
            issues.append(("INFO", "Hint: parent your camera to an Empty"))

        _excluded = {n.strip() for n in settings.actions_filter.split(",") if n.strip()}
        chr_actions = [a for a in bpy.data.actions if a.name not in _excluded]
        if not chr_actions:
            issues.append(("ERROR", "No actions to render (none in file or all excluded)"))
            if bpy.data.actions:
                issues.append(("INFO", "Hint: uncheck at least one action above"))

        active_layers = _resolve_view_layers(scene, settings.view_layers_filter)
        if not active_layers:
            issues.append(("ERROR", "No view layers to render"))

        if not _resolve_path(settings.export_root):
            issues.append(("ERROR", "Export path is relative — save the .blend file first"))
            issues.append(("INFO", "Hint: or set an absolute Export Root path above"))


        if issues:
            layout.separator()
            for icon, text in issues:
                layout.label(text=text, icon=icon)

        layout.separator()
        if settings.progress:
            layout.progress(factor=settings.progress_factor, type="BAR", text=settings.progress)
            layout.label(text="Press ESC to cancel", icon="X")
        else:
            blocking = any(icon == "ERROR" for icon, _ in issues)
            row = layout.row()
            row.enabled = not blocking
            row.operator("spriteloom.render_all", icon="RENDER_ANIMATION")

        if settings.last_result:
            result_box = layout.box()
            result_box.label(text="Last Render", icon="INFO")
            for line in settings.last_result.split("\n"):
                result_box.label(text=line)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class SPRITELOOM_OT_FocusAction(bpy.types.Operator):
    """Set this action on the armature and switch to the Animation workspace"""
    bl_idname = "spriteloom.focus_action"
    bl_label = "Focus Action"

    action_name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        action = bpy.data.actions.get(self.action_name)
        armature = context.scene.spriteloom.armature
        if not action:
            self.report({'WARNING'}, f"Action not found: {self.action_name}")
            return {'CANCELLED'}
        if not armature:
            self.report({'WARNING'}, "No armature set")
            return {'CANCELLED'}
        for obj in context.scene.objects:
            obj.select_set(False)
        armature.select_set(True)
        context.view_layer.objects.active = armature
        if not armature.animation_data:
            armature.animation_data_create()
        armature.animation_data.action = action
        ws = bpy.data.workspaces.get("Animation")
        if ws:
            context.window.workspace = ws
        return {'FINISHED'}


class SPRITELOOM_OT_ActivateViewLayer(bpy.types.Operator):
    """Set this as the active view layer"""
    bl_idname = "spriteloom.activate_view_layer"
    bl_label = "Activate View Layer"

    layer_name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        vl = context.scene.view_layers.get(self.layer_name)
        if not vl:
            self.report({'WARNING'}, f"View layer not found: {self.layer_name}")
            return {'CANCELLED'}
        context.window.view_layer = vl
        return {'FINISHED'}


class SPRITELOOM_OT_ToggleAction(bpy.types.Operator):
    """Toggle an action on/off for rendering"""
    bl_idname = "spriteloom.toggle_action"
    bl_label = "Toggle Action"

    action_name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        settings = context.scene.spriteloom
        all_names = [a.name for a in bpy.data.actions]
        excluded = {n.strip() for n in settings.actions_filter.split(",") if n.strip()}
        if self.action_name in excluded:
            excluded.discard(self.action_name)
        else:
            excluded.add(self.action_name)
        settings.actions_filter = ", ".join(n for n in all_names if n in excluded)
        return {'FINISHED'}


class SPRITELOOM_OT_ToggleViewLayer(bpy.types.Operator):
    """Toggle a view layer on/off for rendering"""
    bl_idname = "spriteloom.toggle_view_layer"
    bl_label = "Toggle View Layer"

    layer_name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        settings = context.scene.spriteloom
        all_layers = [vl.name for vl in context.scene.view_layers]
        excluded = {n.strip() for n in settings.view_layers_filter.split(",") if n.strip()}
        if self.layer_name in excluded:
            excluded.discard(self.layer_name)
        else:
            excluded.add(self.layer_name)
        settings.view_layers_filter = ", ".join(n for n in all_layers if n in excluded)
        return {'FINISHED'}


_classes = (
    SpriteLoomSettings,
    SPRITELOOM_OT_RenderAll,
    SPRITELOOM_OT_FocusAction,
    SPRITELOOM_OT_ActivateViewLayer,
    SPRITELOOM_OT_ToggleAction,
    SPRITELOOM_OT_ToggleViewLayer,
    SPRITELOOM_PT_Main,
)


def _auto_detect_all():
    for scene in bpy.data.scenes:
        _auto_detect(scene)
    return None  # don't repeat


def _auto_detect(scene):
    """Auto-fill armature and camera_rig from scene objects if not already set."""
    settings = scene.spriteloom
    if settings.armature is None:
        armatures = [o for o in scene.objects if o.type == 'ARMATURE']
        if len(armatures) == 1:
            settings.armature = armatures[0]
        elif armatures:
            by_name = {o.name.lower(): o for o in armatures}
            for name in ("rig", "armature", "metarig"):
                if name in by_name:
                    settings.armature = by_name[name]
                    break

    if settings.camera_rig is None:
        cameras = [o for o in scene.objects if o.type == 'CAMERA']
        if scene.camera:
            cameras = [scene.camera] + [c for c in cameras if c is not scene.camera]
        for cam in cameras:
            if cam.parent and cam.parent.type == 'EMPTY':
                settings.camera_rig = cam.parent
                break


@bpy.app.handlers.persistent
def _set_default_armature(_):
    for scene in bpy.data.scenes:
        settings = scene.spriteloom
        settings.progress = ""
        settings.progress_factor = 0.0
        _auto_detect(scene)


def _purge_render_handlers():
    """Remove any leftover SpriteLoom render handlers (e.g. from a failed previous run)."""
    for handler_list in (bpy.app.handlers.render_complete, bpy.app.handlers.render_cancel):
        for h in list(handler_list):
            if getattr(h, "__qualname__", "").startswith("SPRITELOOM_OT_RenderAll"):
                handler_list.remove(h)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.spriteloom = bpy.props.PointerProperty(type=SpriteLoomSettings)
    bpy.app.handlers.load_post.append(_set_default_armature)
    _purge_render_handlers()
    # Also apply to any scenes already open (skipped during install when bpy.data is restricted)
    try:
        _set_default_armature(None)
    except AttributeError:
        pass


def unregister():
    _purge_render_handlers()
    bpy.app.handlers.load_post.remove(_set_default_armature)
    del bpy.types.Scene.spriteloom
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
