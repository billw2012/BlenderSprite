"""
spriteloom_render.py — SpriteLoom CLI entry point

Run with:
    blender --background myfile.blend --python spriteloom_render.py
"""

import os
import sys

import bpy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import spriteloom_addon

spriteloom_addon.register()
bpy.ops.spriteloom.render_all()
