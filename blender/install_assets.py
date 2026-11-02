"""Install the CC0 MakeHuman asset packs in ../asset_packs into MPFB's user data (one-time setup).

    blender -b --factory-startup -P install_assets.py
"""
import glob
import importlib
import os
import zipfile

import addon_utils
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
MPFB = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb"))
addon_utils.enable(MPFB, default_set=True)
services = importlib.import_module(MPFB + ".services")
AssetService, LocationService = services.AssetService, services.LocationService

packs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "asset_packs")
data_dir = LocationService.get_user_data()
for z in sorted(glob.glob(os.path.join(packs, "*.zip"))):
    check = AssetService.check_asset_pack_zip(z)
    if check is None:
        with zipfile.ZipFile(z) as zf:
            zf.extractall(data_dir)
        result = None
    else:
        result = AssetService.fix_and_extract_asset_pack_zip(z, data_dir)
    print(f"PACK {os.path.basename(z)}: {'ok' if result is None else 'FAILED ' + result}" + (f" (fixed {check})" if check else ""))

AssetService.update_all_asset_lists()
print("PACKS INSTALLED:", AssetService.get_pack_names())
print("SYSTEM ASSETS:", AssetService.system_assets_pack_is_installed())
