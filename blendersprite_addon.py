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

DIRECTIONS = {
    "north":     0,
    "northeast": math.pi / 4,
    "east":      math.pi / 2,
    "southeast": 3 * math.pi / 4,
    "south":     math.pi,
    "southwest": 5 * math.pi / 4,
    "west":      3 * math.pi / 2,
    "northwest": 7 * math.pi / 4,
}

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


def _count_existing_frames(folder, expected_count):
    if not os.path.isdir(folder):
        return 0
    return len([f for f in os.listdir(folder) if f.lower().endswith(".png")])


def _numeric_sort_key(filename):
    numbers = re.findall(r"\d+", filename)
    return int(numbers[0]) if numbers else 0


def _pack_folder(np, spritesheet_root, action_name, layer_name, direction_name, folder_path):
    """Pack PNGs in folder_path into a sprite sheet using bpy. Returns True on success."""
    import json

    png_files = sorted(
        [f for f in os.listdir(folder_path) if f.lower().endswith(".png")],
        key=_numeric_sort_key,
    )
    if not png_files:
        _log(f"  WARNING: No PNG frames in {folder_path} — skipping.")
        return False

    frame_count = len(png_files)
    sheet_name = f"{action_name}_{layer_name}_{direction_name}"
    sheet_png = os.path.join(spritesheet_root, f"{sheet_name}.png")
    sheet_json = os.path.join(spritesheet_root, f"{sheet_name}.json")

    _log(f"  Packing {sheet_name}: {frame_count} frame(s)")

    sheet_arr = np.zeros((FRAME_HEIGHT, FRAME_WIDTH * frame_count, 4), dtype=np.float32)
    frames_meta = []

    for i, filename in enumerate(png_files):
        filepath = os.path.join(folder_path, filename)
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

    os.makedirs(spritesheet_root, exist_ok=True)
    generated = 0
    skipped = 0
    errors = 0

    os.makedirs(export_root, exist_ok=True)

    for action_name in sorted(os.listdir(export_root)):
        action_path = os.path.join(export_root, action_name)
        if not os.path.isdir(action_path):
            continue
        for layer_name in sorted(os.listdir(action_path)):
            layer_path = os.path.join(action_path, layer_name)
            if not os.path.isdir(layer_path):
                continue
            for direction_name in sorted(os.listdir(layer_path)):
                dir_path = os.path.join(layer_path, direction_name)
                if not os.path.isdir(dir_path):
                    continue
                if _pack_folder(np, spritesheet_root, action_name, layer_name, direction_name, dir_path):
                    generated += 1
                else:
                    skipped += 1

    return generated, skipped, errors


def _run_render(context, export_root):
    """
    Core render logic. Returns a (rendered, skipped, errors) tuple.
    """
    scene = context.scene

    armature_obj = context.scene.blendersprite.armature
    if armature_obj is None:
        _log("ERROR: No armature selected in the BlenderSprite panel.")
        return 0, 0, 1

    camera_rig = context.scene.blendersprite.camera_rig
    if camera_rig is None:
        _log("ERROR: No camera rig selected in the BlenderSprite panel.")
        return 0, 0, 1

    chr_actions = [a for a in bpy.data.actions if a.name.startswith("chr_")]
    if not chr_actions:
        _log("WARNING: No actions found with prefix 'chr_'. Nothing to render.")
        return 0, 0, 0

    view_layers = _resolve_view_layers(scene, context.scene.blendersprite.view_layers_filter)
    if not view_layers:
        _log("WARNING: No view layers to render.")
        return 0, 0, 0

    _log(f"Found {len(chr_actions)} action(s): {[a.name for a in chr_actions]}")
    _log(f"View layers : {[vl.name for vl in view_layers]}")
    _log(f"Directions  : {list(DIRECTIONS.keys())}")

    rendered = 0
    skipped = 0
    errors = 0

    for action in chr_actions:
        action_name = action.name
        frame_start = int(action.frame_range[0])
        frame_end = int(action.frame_range[1])
        expected_frames = frame_end - frame_start + 1

        _log(f"\n--- Action: {action_name}  frames {frame_start}–{frame_end} ({expected_frames} frames) ---")

        if armature_obj.animation_data is None:
            armature_obj.animation_data_create()
        armature_obj.animation_data.action = action

        scene.frame_start = frame_start
        scene.frame_end = frame_end

        for vl in view_layers:
            context.window.view_layer = vl

            for direction_name, angle_radians in DIRECTIONS.items():
                out_folder = os.path.join(
                    export_root, action_name, vl.name, direction_name
                )

                existing = _count_existing_frames(out_folder, expected_frames)
                if existing >= expected_frames:
                    _log(f"  SKIP  {action_name}/{vl.name}/{direction_name} "
                         f"({existing}/{expected_frames} frames already exist)")
                    skipped += 1
                    continue

                _log(f"  RENDER {action_name}/{vl.name}/{direction_name}  "
                     f"angle={math.degrees(angle_radians):.0f}°")

                camera_rig.rotation_euler.z = angle_radians

                os.makedirs(out_folder, exist_ok=True)
                scene.render.filepath = out_folder + "/"

                try:
                    bpy.ops.render.render(animation=True)
                    rendered += 1
                    _log(f"    Done — {expected_frames} frame(s) written to {out_folder}")
                except Exception as exc:
                    _log(f"    ERROR rendering {action_name}/{vl.name}/{direction_name}: {exc}")
                    errors += 1

    return rendered, skipped, errors


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class BlenderSpriteSettings(bpy.types.PropertyGroup):
    armature: bpy.props.PointerProperty(
        name="Armature",
        description="Armature to render actions from",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )
    camera_rig: bpy.props.PointerProperty(
        name="Camera Rig",
        description="Empty (or object) to rotate for direction changes",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'EMPTY',
    )
    view_layers_filter: bpy.props.StringProperty(
        name="View Layers",
        description="Comma-separated view layers to render. Leave blank to render all",
        default="",
    )
    last_result: bpy.props.StringProperty(default="")
    export_root: bpy.props.StringProperty(
        name="Export Root",
        description="Folder for rendered frames. Leave blank to use <blend file dir>/export",
        subtype='DIR_PATH',
        default="",
    )
    spritesheet_root: bpy.props.StringProperty(
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

    def execute(self, context):
        settings = context.scene.blendersprite
        export_root = _resolve_path(settings.export_root, "export")
        spritesheet_root = _resolve_path(settings.spritesheet_root, "spritesheets")

        if not export_root:
            self.report({"ERROR"}, "Save the .blend file first, or set an explicit Export Root path.")
            return {"CANCELLED"}

        _log("=== BlenderSprite: Render All started ===")
        _log(f"Export root     : {export_root}")
        _log(f"Spritesheet root: {spritesheet_root}")

        rendered, skipped, errors = _run_render(context, export_root)

        _log(f"\n=== Render complete — rendered {rendered}, skipped {skipped}, errors {errors} ===")
        _log(f"\n=== BlenderSprite: Packing sprites ===")

        packed, pack_skipped, pack_errors = _run_pack(export_root, spritesheet_root)

        _log(f"\n=== Pack complete — generated {packed}, skipped {pack_skipped}, errors {pack_errors} ===")

        total_errors = errors + pack_errors
        lines = [
            f"Rendered: {rendered}  Skipped: {skipped}  Errors: {errors}",
            f"Sheets: {packed}  Skipped: {pack_skipped}  Errors: {pack_errors}",
        ]
        context.scene.blendersprite.last_result = "\n".join(lines)

        summary = f"Render {rendered} | Pack {packed} | Errors {total_errors}"
        self.report({"WARNING"} if total_errors > 0 else {"INFO"}, summary)

        return {"FINISHED"}


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

        # Disable button if any blocking issues exist
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
        if settings.armature is None:
            rig = bpy.data.objects.get("rig")
            if rig and rig.type == 'ARMATURE':
                settings.armature = rig
        if settings.camera_rig is None:
            cam = scene.camera
            if cam and cam.parent and cam.parent.type == 'EMPTY':
                settings.camera_rig = cam.parent


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.blendersprite = bpy.props.PointerProperty(type=BlenderSpriteSettings)
    bpy.app.handlers.load_post.append(_set_default_armature)
    # Also apply to any scenes already open
    _set_default_armature(None)


def unregister():
    bpy.app.handlers.load_post.remove(_set_default_armature)
    del bpy.types.Scene.blendersprite
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
