"""Storyboard contact sheets: one still per shot with its number, time, shot size and the line being spoken.

scene_kit.py --storyboard renders the stills and writes storyboard.json next to them; this module lays them out
(per scene, and for a whole episode) so a scene can be judged in a minute instead of after an hour of render.
"""
import json
import os
import textwrap

from core.finish import _font, chapter_stamp

BG, INK, MUTED = (17, 17, 19), (236, 232, 224), (150, 146, 138)


def contact_sheet(sections, out, columns=3, tile=420):
    """sections: [(heading, [{"image", "caption", "text"}])]; writes a JPEG and returns its path."""
    from PIL import Image, ImageDraw
    pad, text_h, head_h = 14, 64, 44
    rows = []
    for heading, tiles in sections:
        rows.append(("head", heading))
        for i in range(0, len(tiles), columns):
            rows.append(("tiles", tiles[i:i + columns]))
    sample = next((t["image"] for _, tiles in sections for t in tiles if os.path.exists(t["image"])), None)
    aspect = 9 / 16
    if sample:
        with Image.open(sample) as im:
            aspect = im.height / im.width
    img_h = int(tile * aspect)
    width = pad + columns * (tile + pad)
    height = pad + sum(head_h if kind == "head" else img_h + text_h + pad for kind, _ in rows)
    sheet = Image.new("RGB", (width, max(height, 1)), BG)
    d = ImageDraw.Draw(sheet)
    big, small = _font(22, True), _font(15)
    y = pad
    for kind, content in rows:
        if kind == "head":
            d.text((pad, y + head_h - 14), content, font=big, fill=INK, anchor="ls")
            y += head_h
            continue
        for n, t in enumerate(content):
            x = pad + n * (tile + pad)
            if os.path.exists(t["image"]):
                with Image.open(t["image"]) as im:
                    sheet.paste(im.convert("RGB").resize((tile, img_h)), (x, y))
            d.text((x, y + img_h + 18), t["caption"], font=small, fill=INK, anchor="ls")
            if t.get("text"):
                line = textwrap.shorten(t["text"], width=58, placeholder="...")
                d.text((x, y + img_h + 40), f"“{line}”", font=small, fill=MUTED, anchor="ls")
        y += img_h + text_h + pad
    sheet.save(out, quality=88)
    return out


def scene_tiles(folder):
    """Tiles from a scene's storyboard.json (written by scene_kit.py --storyboard)."""
    meta = json.load(open(os.path.join(folder, "storyboard.json"), encoding="utf-8"))
    return [{"image": os.path.join(folder, s["image"]),
             "caption": f"{n}  {chapter_stamp(s['time'])}  {s['kind'].replace('_', ' ')}"
                        + (f"  {', '.join(s['on'])}" if s.get("on") else ""),
             "text": s.get("text", "")}
            for n, s in enumerate(meta["shots"], 1)]
