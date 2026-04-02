"""
blender_render.py — BlenderSprite CLI entry point

Run with:
    blender --background myfile.blend --python blender_render.py
"""

import os
import sys

import bpy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import blendersprite_addon

blendersprite_addon.register()
bpy.ops.blendersprite.render_all()
