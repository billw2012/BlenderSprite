bl_info = {
    "name": "SpriteLoom",
    "author": "billw2012",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > SpriteLoom",
    "description": "Render modular character sprite sheets for all actions, layers, and directions",
    "category": "Render",
}

from . import spriteloom_addon

def register():
    spriteloom_addon.register()

def unregister():
    spriteloom_addon.unregister()

if __name__ == "__main__":
    register()
