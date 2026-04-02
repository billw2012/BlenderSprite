# Blender Sprite Sheet Pipeline — Claude Code Handoff

## Project Goal

Automate rendering of a 2D character with modular clothing layers and multiple animations
from Blender, then pack the output into sprite sheets with accompanying JSON metadata
for import into Unreal Engine.

## Blender Scene Structure (manually configured, do not modify)

### Collections (in Outliner)
- `Body` — base character mesh
- `Hat` — hat clothing item
- `Gloves` — gloves clothing item
- *(additional clothing collections follow the same naming convention)*

### Actions (on the armature object)
Named with prefix `chr_` e.g:
- `chr_walk`
- `chr_run`
- `chr_idle`

### View Layers
One per clothing combination. Each layer has:
- The relevant clothing collection set to **normal render**
- The `Body` collection set to **holdout**
- All other clothing collections **excluded**

Named to match clothing e.g:
- `base` — Body normal, all clothing excluded
- `hat` — Hat normal, Body holdout, others excluded
- `gloves` — Gloves normal, Body holdout, others excluded

### Camera Rig
- An Empty object named `CameraRig`
- The scene camera is parented to it
- Rotating `CameraRig.rotation_euler.z` changes the render direction

### Directions
8 directions, evenly spaced at 45° increments:
- Names: `north`, `northeast`, `east`, `southeast`, `south`, `southwest`, `west`, `northwest`
- Rotation values (radians): `0, pi/4, pi/2, 3pi/4, pi, 5pi/4, 3pi/2, 7pi/4`

### Render Settings (manually configured)
- Output format: PNG, RGBA
- Film > Transparent: enabled
- Render passes: Combined, Normal
- Frame size: TBD (power of 2, e.g. 64x64)

---

## Script 1 — `blender_render.py`

Runs inside Blender via `blender --background --python blender_render.py`

### Responsibilities
- Iterate over all actions, view layers, and directions
- For each combination:
  - Set the active action on the armature
  - Set the frame range from the action
  - Set the active view layer
  - Rotate the CameraRig empty to the correct direction
  - Set the output filepath
  - Call `bpy.ops.render.render(animation=True)`

### Output folder structure
```
/export/
  {action}/
    {view_layer}/
      {direction}/
        0001.png
        0002.png
        ...
```

e.g. `/export/chr_walk/hat/north/0001.png`

### Configuration block at top of script
All tuneable values should live in a clearly labelled config block:
```python
EXPORT_ROOT = "/path/to/export"
ARMATURE_NAME = "Armature"
CAMERA_RIG_NAME = "CameraRig"
VIEW_LAYERS = ["base", "hat", "gloves"]
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
```

### Notes
- Actions are discovered automatically by scanning `bpy.data.actions` for names prefixed `chr_`
- Frame range is read from `action.frame_range` on each action
- Skip rendering if output folder already contains the expected number of frames (resume support)

---

## Script 2 — `pack_sprites.py`

Runs standalone (no Blender required). Requires: `Pillow`

### Responsibilities
- Walk the `/export/` directory tree
- For each `{action}/{view_layer}/{direction}/` leaf folder:
  - Read all PNG frames in order
  - Pack into a horizontal sprite sheet
  - Save sprite sheet as `{action}_{view_layer}_{direction}.png`
  - Save accompanying JSON metadata file

### Output location
```
/spritesheets/
  chr_walk_hat_north.png
  chr_walk_hat_north.json
  chr_walk_hat_south.png
  chr_walk_hat_south.json
  ...
```

### JSON format
Compatible with TexturePacker / Aseprite export format for ease of Unreal import:
```json
{
  "meta": {
    "image": "chr_walk_hat_north.png",
    "size": { "w": 512, "h": 64 },
    "frameSize": { "w": 64, "h": 64 },
    "action": "chr_walk",
    "layer": "hat",
    "direction": "north",
    "frameCount": 8
  },
  "frames": [
    {
      "filename": "chr_walk_hat_north_0",
      "frame": { "x": 0, "y": 0, "w": 64, "h": 64 },
      "duration": 100
    }
  ]
}
```

### Configuration block at top of script
```python
EXPORT_ROOT = "/path/to/export"
SPRITESHEET_ROOT = "/path/to/spritesheets"
FRAME_WIDTH = 64
FRAME_HEIGHT = 64
FRAME_DURATION_MS = 100  # default, can be overridden per action via a dict
```

### Notes
- Frames must be sorted numerically (not lexicographically) before packing
- Sprite sheet should be a single horizontal strip (one row)
- Script should be re-runnable — overwrite existing sheets
- Print a summary on completion: how many sheets generated, any folders skipped/errored

---

## Future considerations (do not implement yet, just be aware)

- Normal pass sheets will follow the same structure but in a `/spritesheets_normal/` folder
- A master JSON index file listing all available actions, layers, and directions may be needed
  for Unreal to discover available assets at runtime
- Frame duration may need to vary per action (faster walk vs slower idle)

---

## Constraints

- Both scripts should be self-contained with no dependencies beyond standard library +
  `bpy` (script 1) and `Pillow` (script 2)
- All magic values in config blocks, not hardcoded
- Verbose logging throughout so render progress is visible in terminal
- Scripts should be robust to partial exports (missing folders, zero frames) and log warnings
  rather than crashing