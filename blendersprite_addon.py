"""
blendersprite_addon.py — BlenderSprite Blender Addon

Install via: Edit > Preferences > Add-ons > Install... > select this file

Adds a "BlenderSprite" tab in the 3D Viewport N-panel with a
"Render All" button that runs the full render pipeline.
"""

bl_info = {
    "name": "BlenderSprite",
    "author": "",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderSprite",
    "description": "Render modular character sprite sheets for all actions, layers, and directions",
    "category": "Render",
}

import math
import os
import re

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
    print(f"[BlenderSprite] {msg}", flush=True)


def _resolve_view_layers(scene, filter_str):
    """Return view layer objects to render. Uses all scene layers if filter_str is empty."""
    if filter_str.strip():
        names = [n.strip() for n in filter_str.split(",") if n.strip()]
        layers = [scene.view_layers.get(n) for n in names]
        missing = [n for n, vl in zip(names, layers) if vl is None]
        if missing:
            _log(f"WARNING: View layers not found and will be skipped: {', '.join(missing)}")
        return [vl for vl in layers if vl is not None]
    return list(scene.view_layers)


def _resolve_path(prop_value, blend_relative_default):
    """Return an absolute path from a settings string, falling back to blend-relative default."""
    if prop_value:
        return bpy.path.abspath(prop_value)
    if bpy.data.filepath:
        return os.path.join(os.path.dirname(bpy.path.abspath(bpy.data.filepath)), blend_relative_default)
    return ""


def _count_existing_frames(export_root, action_name, layer_name, direction_name):
    if not os.path.isdir(export_root):
        return 0
    prefix = f"{action_name}_{layer_name}_{direction_name}_"
    return len([f for f in os.listdir(export_root) if f.startswith(prefix) and f.lower().endswith(".png")])


def _numeric_sort_key(filename):
    numbers = re.findall(r"\d+", filename)
    return int(numbers[0]) if numbers else 0


def _pack_folder(np, spritesheet_root, action_name, layer_name, direction_name, filepaths):
    """Pack a list of PNG filepaths into a sprite sheet using bpy. Returns True on success."""
    import json

    filepaths = sorted(filepaths, key=lambda p: _numeric_sort_key(os.path.basename(p)))
    if not filepaths:
        _log(f"  WARNING: No PNG frames for {action_name}_{layer_name}_{direction_name} — skipping.")
        return False

    frame_count = len(filepaths)
    sheet_name = f"{action_name}_{layer_name}_{direction_name}"
    sheet_png = os.path.join(spritesheet_root, f"{sheet_name}.png")
    sheet_json = os.path.join(spritesheet_root, f"{sheet_name}.json")

    _log(f"  Packing {sheet_name}: {frame_count} frame(s)")

    sheet_arr = np.zeros((FRAME_HEIGHT, FRAME_WIDTH * frame_count, 4), dtype=np.float32)
    frames_meta = []

    for i, filepath in enumerate(filepaths):
        filename = os.path.basename(filepath)
        try:
            img = bpy.data.images.load(filepath)
        except Exception as exc:
            _log(f"    WARNING: Could not load {filename}: {exc} — skipping frame.")
            continue

        if img.size[0] != FRAME_WIDTH or img.size[1] != FRAME_HEIGHT:
            _log(f"    WARNING: {filename} is {img.size[0]}x{img.size[1]}, "
                 f"expected {FRAME_WIDTH}x{FRAME_HEIGHT}.")

        # pixels is a flat RGBA float array, row-major, bottom-left origin
        arr = np.array(img.pixels, dtype=np.float32).reshape(img.size[1], img.size[0], 4)
        bpy.data.images.remove(img)

        x = i * FRAME_WIDTH
        sheet_arr[:, x:x + FRAME_WIDTH, :] = arr[:FRAME_HEIGHT, :FRAME_WIDTH, :]

        duration = FRAME_DURATION_OVERRIDES.get(action_name, FRAME_DURATION_MS)
        frames_meta.append({
            "filename": f"{sheet_name}_{i}",
            "frame": {"x": x, "y": 0, "w": FRAME_WIDTH, "h": FRAME_HEIGHT},
            "duration": duration,
        })

    sheet_img = bpy.data.images.new(
        sheet_name, width=FRAME_WIDTH * frame_count, height=FRAME_HEIGHT, alpha=True
    )
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
        "meta": {
            "image": os.path.basename(sheet_png),
            "size": {"w": FRAME_WIDTH * frame_count, "h": FRAME_HEIGHT},
            "frameSize": {"w": FRAME_WIDTH, "h": FRAME_HEIGHT},
            "action": action_name,
            "layer": layer_name,
            "direction": direction_name,
            "frameCount": frame_count,
        },
        "frames": frames_meta,
    }
    try:
        with open(sheet_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception as exc:
        _log(f"  ERROR writing {sheet_json}: {exc}")
        return False

    return True


def _run_pack(export_root, spritesheet_root):
    """Pack all rendered frames into sprite sheets. Returns (generated, skipped, errors)."""
    import numpy as np
    from collections import defaultdict

    if not os.path.isdir(export_root):
        _log(f"  WARNING: export root not found: {export_root}")
        return 0, 0, 0

    os.makedirs(spritesheet_root, exist_ok=True)
    generated = 0
    skipped = 0
    errors = 0

    # Group flat PNGs by their action_layer_direction prefix.
    # Filename format: {action}_{layer}_{direction}_{frame:04d}.png
    groups = defaultdict(list)
    for fname in os.listdir(export_root):
        if not fname.lower().endswith(".png"):
            continue
        stem = fname[:-4]  # strip .png
        parts = stem.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
            groups[parts[0]].append(os.path.join(export_root, fname))

    for key in sorted(groups):
        # key is "{action}_{layer}_{direction}"
        # action = first token (starts with "chr_"), direction = last token, layer = middle
        parts = key.split("_")
        if len(parts) < 3:
            _log(f"  WARNING: unexpected filename prefix '{key}', skipping.")
            skipped += 1
            continue
        action_name = parts[0]
        direction_name = parts[-1]
        layer_name = "_".join(parts[1:-1])
        if _pack_folder(np, spritesheet_root, action_name, layer_name, direction_name, groups[key]):
            generated += 1
        else:
            errors += 1

    return generated, skipped, errors



def _get_cloth_objects_in_layer(view_layer):
    """Return mesh objects with a Cloth modifier that are renderable in this view layer."""
    return [
        obj for obj in view_layer.objects
        if not obj.hide_render
        and any(m.type == 'CLOTH' for m in obj.modifiers)
    ]


def _bake_cloth_for_action(context, view_layers, action, warmup_frames):
    """
    Bake cloth for a single action. Each action gets a fresh bake so cloth
    simulation doesn't carry state from the previous action.
    Frame range: action.frame_start - warmup_frames  to  action.frame_end.
    Returns number of objects baked.
    """
    bake_start = int(action.frame_range[0]) - warmup_frames
    bake_end   = int(action.frame_range[1])
    _log(f"  Cloth bake '{action.name}': frames {bake_start}→{bake_end} (warmup: {warmup_frames})")

    cloth_objs = []
    seen = set()
    for vl in view_layers:
        for obj in _get_cloth_objects_in_layer(vl):
            if obj.name not in seen:
                cloth_objs.append(obj)
                seen.add(obj.name)

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
    settings = scene.blendersprite

    armature_obj = settings.armature
    if armature_obj is None:
        return None, "No armature selected"

    camera_rig = settings.camera_rig
    if camera_rig is None:
        return None, "No camera rig selected"

    chr_actions = [a for a in bpy.data.actions if a.name.startswith("chr_")]
    if not chr_actions:
        return None, "No actions found with prefix 'chr_'"

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
        frames = list(range(frame_start, frame_end + 1, frame_step))
        expected_frames = len(frames)
        action_has_jobs = False
        action_jobs = []
        os.makedirs(export_root, exist_ok=True)
        for vl in view_layers:
            for direction_name, angle_radians in directions:
                prefix = f"{action.name}_{vl.name}_{direction_name}"
                if not overwrite and _count_existing_frames(export_root, action.name, vl.name, direction_name) >= expected_frames:
                    _log(f"  SKIP  {prefix} ({expected_frames} frames exist)")
                    skipped += 1
                    continue
                if overwrite:
                    for f in os.listdir(export_root):
                        if f.startswith(prefix + "_") and f.lower().endswith(".png"):
                            os.remove(os.path.join(export_root, f))
                    _log(f"  CLEAR {prefix}")
                action_has_jobs = True
                for frame in frames:
                    action_jobs.append({
                        "type": "render",
                        "action": action,
                        "vl_name": vl.name,
                        "direction_name": direction_name,
                        "angle_radians": angle_radians,
                        "out_path": os.path.join(export_root, f"{prefix}_{frame:04d}.png"),
                        "frame": frame,
                        "frame_start": frame_start,
                        "frame_end": frame_end,
                        "armature_obj": armature_obj,
                        "camera_rig": camera_rig,
                    })
        if action_has_jobs and settings.bake_cloth:
            jobs.append({"type": "bake", "action": action, "view_layers": view_layers})
        jobs.extend(action_jobs)
    return jobs, skipped


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class BlenderSpriteSettings(bpy.types.PropertyGroup):
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
    overwrite_frames: bpy.props.BoolProperty(  # type: ignore
        name="Overwrite Existing Frames",
        description="Re-render and overwrite frames that already exist on disk (instead of skipping them)",
        default=False,
    )
    progress: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})  # type: ignore
    progress_factor: bpy.props.FloatProperty(default=0.0, options={'SKIP_SAVE'})  # type: ignore
    last_result: bpy.props.StringProperty(default="")  # type: ignore
    export_root: bpy.props.StringProperty(  # type: ignore
        name="Export Root",
        description="Folder for rendered frames. Leave blank to use <blend file dir>/export",
        subtype='DIR_PATH',
        default="",
    )
    spritesheet_root: bpy.props.StringProperty(  # type: ignore
        name="Spritesheet Root",
        description="Folder for packed sprite sheets. Leave blank to use <blend file dir>/spritesheets",
        subtype='DIR_PATH',
        default="",
    )


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class BLENDERSPRITE_OT_RenderAll(bpy.types.Operator):
    """Render all chr_ actions × view layers × directions to disk"""

    bl_idname = "blendersprite.render_all"
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
        settings = context.scene.blendersprite
        self._export_root = _resolve_path(settings.export_root, "export")
        self._spritesheet_root = _resolve_path(settings.spritesheet_root, "spritesheets")

        if not self._export_root:
            self.report({"ERROR"}, "Save the .blend file first, or set an explicit Export Root path.")
            return {"CANCELLED"}

        _log("=== BlenderSprite: Render All started ===")
        _log(f"Export root     : {self._export_root}")
        _log(f"Spritesheet root: {self._spritesheet_root}")

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

        context.scene.blendersprite.last_result = ""
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
            settings = context.scene.blendersprite
            context.scene.blendersprite.progress = f"Baking cloth: {action.name}..."
            for area in context.screen.areas:
                area.tag_redraw()
            _log(f"=== Baking cloth for '{action.name}' ===")
            armature_obj = settings.armature
            if armature_obj and armature_obj.animation_data:
                armature_obj.animation_data.action = action
            _bake_cloth_for_action(context, job["view_layers"], action, settings.cloth_warmup_frames)
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
        scene.blendersprite.progress = (
            f"{label}  frame {frame_num}/{frame_total}  "
            f"({self._rendered + 1}/{self._render_total})"
        )
        scene.blendersprite.progress_factor = self._rendered / self._render_total if self._render_total else 0.0
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
        settings = context.scene.blendersprite
        if settings.camera_rig and self._orig_camera_rig_z is not None:
            settings.camera_rig.rotation_euler.z = self._orig_camera_rig_z

    def cancel(self, context):
        _log("=== BlenderSprite: Cancelled ===")
        self._restore_scene(context)
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            context.window_manager.progress_end()
        context.scene.blendersprite.progress = ""
        context.scene.blendersprite.progress_factor = 0.0
        context.scene.blendersprite.last_result = (
            f"Cancelled after {self._rendered} rendered, {self._skipped} skipped, {self._errors} errors"
        )
        return {"CANCELLED"}

    def _finish(self, context):
        self._restore_scene(context)
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            context.window_manager.progress_end()
        context.scene.blendersprite.progress = ""
        context.scene.blendersprite.progress_factor = 0.0

        _log(f"\n=== Render complete — rendered {self._rendered}, skipped {self._skipped}, errors {self._errors} ===")
        _log("=== BlenderSprite: Packing sprites ===")

        packed, pack_skipped, pack_errors = _run_pack(self._export_root, self._spritesheet_root)

        _log(f"=== Pack complete — generated {packed}, skipped {pack_skipped}, errors {pack_errors} ===")

        total_errors = self._errors + pack_errors
        context.scene.blendersprite.last_result = "\n".join([
            f"Rendered: {self._rendered}  Skipped: {self._skipped}  Errors: {self._errors}",
            f"Sheets: {packed}  Skipped: {pack_skipped}  Errors: {pack_errors}",
        ])
        self.report({"WARNING"} if total_errors > 0 else {"INFO"},
                    f"Render {self._rendered} | Pack {packed} | Errors {total_errors}")


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class BLENDERSPRITE_PT_Main(bpy.types.Panel):
    """BlenderSprite main sidebar panel"""

    bl_label = "BlenderSprite"
    bl_idname = "BLENDERSPRITE_PT_Main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderSprite"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.blendersprite
        scene = context.scene

        layout.prop(settings, "armature")
        layout.prop(settings, "camera_rig")
        row = layout.row(align=True)
        row.prop(settings, "bake_cloth")
        if settings.bake_cloth:
            row.prop(settings, "cloth_warmup_frames")
        layout.prop(settings, "num_directions")
        layout.prop(settings, "frame_step")
        layout.prop(settings, "overwrite_frames")
        layout.prop(settings, "view_layers_filter")
        layout.prop(settings, "export_root")
        layout.prop(settings, "spritesheet_root")

        # --- Validation warnings ---
        issues = []

        if settings.armature is None:
            issues.append(("ERROR", "No armature selected"))
        if settings.camera_rig is None:
            issues.append(("ERROR", "No camera rig selected"))
            issues.append(("INFO", "Hint: parent your camera to an Empty"))

        chr_actions = [a for a in bpy.data.actions if a.name.startswith("chr_")]
        if not chr_actions:
            issues.append(("ERROR", "No actions found with prefix 'chr_'"))
            issues.append(("INFO", "Hint: rename actions to e.g. chr_walk, chr_idle"))

        active_layers = _resolve_view_layers(scene, settings.view_layers_filter)
        if not active_layers:
            issues.append(("ERROR", "No view layers to render"))
        else:
            issues.append(("INFO", f"Layers: {', '.join(vl.name for vl in active_layers)}"))

        if not settings.export_root and not bpy.data.filepath:
            issues.append(("ERROR", "No export path — save the .blend file first"))
            issues.append(("INFO", "Hint: or set an explicit Export Root above"))


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
            row.operator("blendersprite.render_all", icon="RENDER_ANIMATION")

        if settings.last_result:
            layout.separator()
            for line in settings.last_result.split("\n"):
                layout.label(text=line)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_classes = (
    BlenderSpriteSettings,
    BLENDERSPRITE_OT_RenderAll,
    BLENDERSPRITE_PT_Main,
)


@bpy.app.handlers.persistent
def _set_default_armature(_):
    for scene in bpy.data.scenes:
        settings = scene.blendersprite
        settings.progress = ""
        settings.progress_factor = 0.0
        if settings.armature is None:
            rig = bpy.data.objects.get("rig")
            if rig and rig.type == 'ARMATURE':
                settings.armature = rig
        if settings.camera_rig is None:
            cam = scene.camera
            if cam and cam.parent and cam.parent.type == 'EMPTY':
                settings.camera_rig = cam.parent


def _purge_render_handlers():
    """Remove any leftover BlenderSprite render handlers (e.g. from a failed previous run)."""
    for handler_list in (bpy.app.handlers.render_complete, bpy.app.handlers.render_cancel):
        for h in list(handler_list):
            if getattr(h, "__qualname__", "").startswith("BLENDERSPRITE_OT_RenderAll"):
                handler_list.remove(h)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.blendersprite = bpy.props.PointerProperty(type=BlenderSpriteSettings)
    bpy.app.handlers.load_post.append(_set_default_armature)
    _purge_render_handlers()
    # Also apply to any scenes already open
    _set_default_armature(None)


def unregister():
    _purge_render_handlers()
    bpy.app.handlers.load_post.remove(_set_default_armature)
    del bpy.types.Scene.blendersprite
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
