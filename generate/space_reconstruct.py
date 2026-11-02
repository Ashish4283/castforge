"""CastForge reconstruct stage: one front photo -> 6 generated views (incl. back) -> textured mesh.

Runs PSHuman on a free Hugging Face ZeroGPU Space, so nothing heavy runs locally.
Quota: the Space bills GPU seconds to your HF account (free tier ~3.5 min/day,
PRO 40 min/day); one character asks for two 140 s calls.

    .venv/Scripts/python generate/space_reconstruct.py photo.png out_dir [--views-only] [--from-views views.zip]

--views-only stops after the multiview step so the generated back/side views can be
checked (and edited) before meshing; --from-views uploads an edited set and meshes it.
"""
import argparse
import os
import pathlib
import shutil
import sys
import time

from gradio_client import Client, handle_file

# The original fffiloni/PSHuman fails on ZeroGPU's newer GPUs; this copy carries the fix
# and splits generation and meshing into separate GPU calls.
SPACE = "painter3000/PSHuman"

ap = argparse.ArgumentParser()
ap.add_argument("photo")
ap.add_argument("out")
ap.add_argument("--views-only", action="store_true")
ap.add_argument("--from-views", help="edited views zip to mesh instead of generating")
ap.add_argument("--keep-bg", action="store_true", help="photo already has a transparent background")
args = ap.parse_args()

token_file = pathlib.Path.home() / ".cache/huggingface/token"
token = os.environ.get("HF_TOKEN") or (token_file.read_text().strip() if token_file.exists() else None)
if not token:
    sys.exit("no Hugging Face token: run `huggingface-cli login` (anonymous quota is too small for one run)")

out = pathlib.Path(args.out)
(out / "views").mkdir(parents=True, exist_ok=True)
client = Client(SPACE, token=token, verbose=False)


def path_of(f):
    if isinstance(f, dict):
        f = f.get("image") or f.get("video") or f.get("path")
        if isinstance(f, dict):
            f = f["path"]
    return f


def call(label, **kw):
    t = time.time()
    try:
        r = client.predict(**kw)
    except Exception as e:
        msg = str(e)
        if "ZeroGPU quota" in msg:
            sys.exit(f"{label}: out of ZeroGPU quota. {msg}")
        sys.exit(f"{label} failed: {msg}")
    print(f"{label}: {time.time() - t:.0f}s")
    return r


if args.from_views:
    session, status, gallery = call("upload views", upload_zip=handle_file(args.from_views),
                                    session_dir="", api_name="/process_upload_set")
else:
    session, status, gallery = call("generate views", input_pil=handle_file(args.photo),
                                    remove_bg=not args.keep_bg, api_name="/process_generate")
print(status)
for g in gallery:
    p = path_of(g)
    shutil.copy(p, out / "views" / os.path.basename(p))
zip_path, _ = call("download views", session_dir=session, api_name="/process_download_set")
shutil.copy(path_of(zip_path), out / "views.zip")

if args.views_only:
    print(f"views in {out / 'views'}; edit and rerun with --from-views {out / 'views.zip'}")
    sys.exit(0)

status, video, mesh, mesh_colored, _ = call("reconstruct", session_dir=session, keep_session=False,
                                            api_name="/process_reconstruct")
print(status)
for f, name in ((video, "turntable.mp4"), (mesh, "mesh.obj"), (mesh_colored, "mesh_colored.obj")):
    if f:
        shutil.copy(path_of(f), out / name)
print(f"done: {out}")
