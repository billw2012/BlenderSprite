"""Build spriteloom.zip and hot-deploy to Blender's extension directory."""
import zipfile
import os
import shutil
import glob

files = [
    "blender_manifest.toml",
    "__init__.py",
    "spriteloom_addon.py",
    "spriteloom_render.py",
]

# Build zip
output = "spriteloom.zip"
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        zf.write(f)
print(f"Built {output}")

# Deploy to Blender extension directories (all installed versions)
pattern = os.path.expandvars(
    r"%APPDATA%\Blender Foundation\Blender\*\extensions\user_default\spriteloom"
)
install_dirs = glob.glob(pattern)

if not install_dirs:
    print("No installed spriteloom extension found — install from zip first")
else:
    for install_dir in install_dirs:
        for f in files:
            shutil.copy2(f, os.path.join(install_dir, f))
        print(f"Deployed to {install_dir}")
    print("Reload in Blender: F3 > 'Reload Scripts'")
