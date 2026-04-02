# BlenderSprite

Blender addon for rendering modular 2D character sprite sheets across all actions, clothing layers, and directions, ready for import into Unreal Engine.

## Features

- Renders all `chr_` prefixed actions automatically
- Iterates all view layers (or a filtered subset) and 8 directions
- Packs rendered frames into horizontal sprite sheets with JSON metadata
- Resume support — skips folders that already have the expected frame count
- N-panel UI with validation warnings and per-run summary

## Requirements

- Blender 3.0+
- numpy (bundled with Blender)

## Installation

1. In Blender: **Edit > Preferences > Add-ons > Install...**
2. Select `blendersprite_addon.py`
3. Enable the addon
4. Open the **3D Viewport**, press **N**, select the **BlenderSprite** tab

## Scene Setup

### Armature
Actions must be named with the prefix `chr_`, e.g. `chr_walk`, `chr_run`, `chr_idle`.

### Camera Rig
Parent your camera to an Empty. The addon will auto-detect it. Rotating this Empty changes the render direction.

### View Layers
One view layer per clothing layer. The addon renders all view layers by default, or a comma-separated subset if specified in the panel.

## Usage

Configure the panel fields, then click **Render All**:

| Field | Description |
|---|---|
| Armature | Armature to read actions from (defaults to `rig`) |
| Camera Rig | Empty to rotate for direction changes (auto-detected from camera parent) |
| View Layers | Comma-separated layer names, or blank for all |
| Export Root | Rendered frames output folder (defaults to `<blend dir>/export`) |
| Spritesheet Root | Packed sheets output folder (defaults to `<blend dir>/spritesheets`) |

## Output Structure

```
export/
  chr_walk/
    LayerName/
      north/  northeast/  east/ ...
        0001.png  0002.png ...

spritesheets/
  chr_walk_LayerName_north.png
  chr_walk_LayerName_north.json
  ...
```

## CLI Usage

```
blender --background myfile.blend --python blender_render.py
```

## JSON Format

Sprite sheet metadata is compatible with TexturePacker / Aseprite export format:

```json
{
  "meta": {
    "image": "chr_walk_LayerName_north.png",
    "size": { "w": 512, "h": 64 },
    "frameSize": { "w": 64, "h": 64 },
    "action": "chr_walk",
    "layer": "LayerName",
    "direction": "north",
    "frameCount": 8
  },
  "frames": [
    { "filename": "chr_walk_LayerName_north_0", "frame": { "x": 0, "y": 0, "w": 64, "h": 64 }, "duration": 100 }
  ]
}
```
