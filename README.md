# SpriteLoom

Blender addon for rendering modular 2D character sprite sheets across all actions, clothing layers, and directions, ready for import into Unreal Engine.

![SpriteLoom UI](screenshots/main-ui.png)

## Features

- Renders all actions matching a configurable prefix (default `chr_`)
- Looping animation support — actions ending with a configurable tag (default `_loop`) exclude the duplicate last frame
- Per-action clickable list shows frame count and jumps to the Animation workspace
- View layer selection via checkboxes (one per layer, all enabled by default)
- 1 / 4 / 8 / 16 direction rendering via camera rig rotation
- Configurable file and row splits: separate sheets per action, layer, and/or direction
- Configurable sheet naming via placeholders: `{blendfile}`, `{action}`, `{layer}`, `{direction}`
- Live example output preview in the Sheet Layout panel
- Cloth simulation baking per view layer / action combination before rendering
- Resume support — skips frames that already exist on disk
- Auto-detects armature and camera rig from the scene
- N-panel UI with validation warnings and per-run summary

## Requirements

- Blender 4.2+
- numpy (bundled with Blender)

## Installation

1. Build the zip: `python build_extension.py`
2. In Blender: **Edit > Preferences > Extensions > Install from Disk...**
3. Select `spriteloom.zip`
4. Open the **3D Viewport**, press **N**, select the **SpriteLoom** tab

## Scene Setup

### Armature
The addon auto-detects a single armature in the scene, or falls back to common names (`rig`, `armature`, `metarig`). You can override it in the panel.

### Camera Rig
Parent your scene camera to an Empty. The addon auto-detects it and rotates it to render each direction.

### Actions
Name actions with a common prefix (default `chr_`), e.g. `chr_walk`, `chr_run`, `chr_idle`. For looping animations that should not repeat the last frame, add the loop tag suffix (default `_loop`), e.g. `chr_walk_loop`.

### View Layers
Use one view layer per clothing/equipment layer (e.g. `Guy` for the base body, `Coat` for an overcoat). Within each view layer, configure object visibility and holdout to control exactly what appears in that render pass:

- **Visible**: objects that should appear in this layer's output (e.g. the body and the coat in the `Coat` layer)
- **Holdout**: objects that should punch a hole through everything behind them (e.g. the body in the `Coat` layer, so the coat is correctly masked against the character silhouette rather than the background)

This lets each layer produce a correctly composited RGBA image that can be layered in-engine.

All view layers are rendered by default; deselect individual layers in the panel to exclude them.

### Compositor
SpriteLoom renders via Blender's compositor. Set up the compositor with a **Render Layers** (View Layer) input node connected to your output. SpriteLoom automatically updates the View Layer input to the current layer before each render, so a single compositor graph handles all layers correctly without any manual switching.

The simplest setup: **Render Layers → Composite**. Any colour correction, alpha-over, or other nodes between them will be applied consistently to every layer and direction.

## Panel Reference

### Scene Setup
| Field | Description |
|---|---|
| Armature | Armature to read actions from |
| Camera Rig | Empty to rotate for direction changes |

### Render
| Field | Description |
|---|---|
| Directions | Number of render directions: 1 / 4 / 8 / 16 |
| Frame Step | Render every Nth frame |
| Action Prefix | Only actions starting with this prefix are rendered |
| Action Loop Tag | Actions ending with this suffix exclude the last frame |
| Bake Cloth | Bake cloth simulations before rendering (per layer/action) |
| Warmup Frames | Extra frames baked before the action start |

### Output
| Field | Description |
|---|---|
| View Layers | Checkboxes to include/exclude individual layers |
| Export Root | Folder for rendered frames (supports `//` blend-relative paths) |
| Spritesheet Root | Folder for packed sprite sheets |

### Sheet Layout
| Field | Description |
|---|---|
| File splits | Separate files per Action / Layer / Direction |
| Row splits | Separate rows per Action / Layer / Direction within a sheet |
| Name Format | Filename template using `{blendfile}`, `{action}`, `{layer}`, `{direction}` |

## Output

Rendered frames are written flat into the export folder:
```
export/
  {action}--{layer}--{direction}--{frame:04d}.png
```

Packed sprite sheets:
```
spritesheets/
  {name}.png
  {name}.json
```

## JSON Format

Sprite sheet metadata compatible with TexturePacker / Aseprite:

```json
{
  "meta": {
    "image": "myfile-Coat-chr_walk-south.png",
    "size": { "w": 512, "h": 64 },
    "frameSize": { "w": 64, "h": 64 },
    "action": "chr_walk",
    "layer": "Coat",
    "direction": "south",
    "frameCount": 8
  },
  "frames": [
    { "filename": "myfile-Coat-chr_walk-south_0", "frame": { "x": 0, "y": 0, "w": 64, "h": 64 }, "duration": 100 }
  ]
}
```

## CLI Usage

```
blender --background myfile.blend --python spriteloom_render.py
```
