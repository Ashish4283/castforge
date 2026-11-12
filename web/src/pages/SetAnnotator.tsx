// The set region editor: mark each object on the set picture as a mask, not just a box. Tools: select (move and
// resize with handles), box, magic wand (similar colours), lasso, brush, eraser, and a "hidden part" brush for
// where the object continues behind something else. Undo/redo, zoom and pan. Saves sets/<set>/masks/<id>.png
// (255 seen, 128 hidden) and the object's box (picture_rect).
import {PointerEvent as RPE, useCallback, useEffect, useMemo, useRef, useState} from "react";
import {Brush, Eraser, EyeOff, Hand, Lasso, MousePointer2, Redo2, Save, Square, Trash2, Undo2, Wand2, X,
  ZoomIn, ZoomOut, Maximize, Sparkles, Plus} from "lucide-react";
import {form, Json, post} from "../api";
import {useStore} from "../app/store";
import {Badge, Button, Select} from "../components/ui";
import {COLORS} from "./episodes/SceneSetup";

type Tool = "select" | "box" | "wand" | "lasso" | "brush" | "hidden" | "eraser" | "pan";
type Mode = "replace" | "add" | "subtract";
type Box = [number, number, number, number];      // x0, y0, x1, y1 in work pixels (x1/y1 exclusive)
const SEEN = 255, HIDDEN = 128;
const TOOLS: [Tool, string, typeof Brush, string][] = [
  ["select", "Select, move and resize", MousePointer2, "V"], ["box", "Box", Square, "R"],
  ["wand", "Magic wand: similar colours", Wand2, "W"], ["lasso", "Lasso: click corners, double-click to close", Lasso, "L"],
  ["brush", "Brush: paint the object", Brush, "B"], ["hidden", "Hidden part: where it continues behind something", EyeOff, "H"],
  ["eraser", "Eraser", Eraser, "E"], ["pan", "Pan (or hold Space)", Hand, "Space"],
];

function bboxOf(m: Uint8Array, w: number, h: number): Box | null {
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) if (m[row + x]) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; y1 = y; }
  }
  return x1 < 0 ? null : [x0, y0, x1 + 1, y1 + 1];
}

export function SetAnnotator({movie, setName, picture, props, focus, onApply, onClose}: {
  movie: string; setName: string; picture: string; props: Json[]; focus: number | null;
  onApply: (props: Json[]) => Promise<void>; onClose: () => void;
}) {
  const {schema, toast} = useStore();
  const [objs, setObjs] = useState<Json[]>(() => structuredClone(props));
  const [sel, setSel] = useState(focus ?? 0);
  const [tool, setTool] = useState<Tool>("wand");
  const [mode, setMode] = useState<Mode>("add");
  const [tol, setTol] = useState(14);
  const [size, setSize] = useState(18);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({x: 0, y: 0});
  const [dims, setDims] = useState<{w: number; h: number} | null>(null);
  const [lasso, setLasso] = useState<[number, number][]>([]);
  const [hist, setHist] = useState({undo: 0, redo: 0});
  const [rev, setRev] = useState(0);
  const [saving, setSaving] = useState(false);
  const [filled, setFilled] = useState<string | null>(null);
  const [newType, setNewType] = useState("chair");
  const base = useRef<HTMLCanvasElement>(null);
  const over = useRef<HTMLCanvasElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const pixels = useRef<Uint8ClampedArray | null>(null);
  const masks = useRef(new Map<string, Uint8Array>());
  const dirty = useRef(new Set<string>());
  const undo = useRef<{id: string; data: Uint8Array}[]>([]);
  const redo = useRef<{id: string; data: Uint8Array}[]>([]);
  const drag = useRef<Json>(null);
  const space = useRef(false);

  const W = dims?.w || 1, H = dims?.h || 1;
  const cur = objs[sel];
  const maskOf = useCallback((id: string) => {
    let m = masks.current.get(id);
    if (!m) { m = new Uint8Array(W * H); masks.current.set(id, m); }
    return m;
  }, [W, H]);

  // --- load the picture and every object's mask (or its old box) ------------------------------------------
  useEffect(() => {
    const img = new Image();
    img.onload = async () => {
      const w = Math.min(img.naturalWidth, 1600), h = Math.round(img.naturalHeight * w / img.naturalWidth);
      const c = base.current!;
      c.width = w; c.height = h;
      const g = c.getContext("2d", {willReadFrequently: true})!;
      g.drawImage(img, 0, 0, w, h);
      pixels.current = g.getImageData(0, 0, w, h).data;
      for (const p of objs) {
        const m = new Uint8Array(w * h);
        if (p.picture_mask) {
          try {
            const mi = new Image();
            mi.src = `/media/${encodeURIComponent(movie)}/sets/${encodeURIComponent(setName)}/${p.picture_mask}?t=${Date.now()}`;
            await mi.decode();
            const t = document.createElement("canvas");
            t.width = w; t.height = h;
            const tg = t.getContext("2d")!;
            tg.imageSmoothingEnabled = false;
            tg.drawImage(mi, 0, 0, w, h);
            const d = tg.getImageData(0, 0, w, h).data;
            for (let i = 0; i < w * h; i++) m[i] = d[i * 4] > 191 ? SEEN : d[i * 4] > 63 ? HIDDEN : 0;
          } catch { /* fall back to the box */ }
        }
        if (!m.some(v => v) && Array.isArray(p.picture_rect)) {
          const [l, t, r, b] = p.picture_rect;
          for (let y = Math.floor(t * h); y < Math.ceil(b * h); y++) m.fill(SEEN, y * w + Math.floor(l * w), y * w + Math.ceil(r * w));
        }
        masks.current.set(p.id, m);
      }
      setDims({w, h});
      fit(w, h);
    };
    img.src = picture;
  }, []);   // once: the editor works on its own copy until Apply

  const fit = (w = W, h = H) => {
    const r = stage.current!.getBoundingClientRect();
    const z = Math.min((r.width - 40) / w, (r.height - 40) / h);
    setZoom(z);
    setPan({x: (r.width - w * z) / 2, y: (r.height - h * z) / 2});
  };

  // --- overlay: every object tinted in its colour, hidden parts striped ------------------------------------
  useEffect(() => {
    if (!dims) return;
    const c = over.current!;
    c.width = W; c.height = H;
    const g = c.getContext("2d")!;
    const out = g.createImageData(W, H), d = out.data;
    objs.forEach((p, k) => {
      const m = masks.current.get(p.id);
      if (!m) return;
      const hex = COLORS[k % COLORS.length], r = parseInt(hex.slice(1, 3), 16), gg = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
      const a = k === sel ? 120 : 60;
      for (let i = 0; i < m.length; i++) {
        if (!m[i]) continue;
        const j = i * 4;
        if (m[i] === HIDDEN) {
          const x = i % W, y = (i / W) | 0;
          if (((x + y) >> 2) % 2) { d[j] = 255; d[j + 1] = 190; d[j + 2] = 60; d[j + 3] = 150; }
          else { d[j] = r; d[j + 1] = gg; d[j + 2] = b; d[j + 3] = a / 2; }
        } else { d[j] = r; d[j + 1] = gg; d[j + 2] = b; d[j + 3] = a; }
      }
    });
    g.putImageData(out, 0, 0);
  }, [rev, sel, objs, dims]);   // rev bumps on every mask change

  const box = useMemo(() => (cur && dims ? bboxOf(maskOf(cur.id), W, H) : null), [rev, sel, dims, cur]);   // the selected object's box

  // --- history ---------------------------------------------------------------------------------------------
  const snapshot = (id: string) => {
    undo.current.push({id, data: maskOf(id).slice()});
    if (undo.current.length > 60) undo.current.shift();
    redo.current = [];
    setHist({undo: undo.current.length, redo: 0});
  };
  const changed = (id: string) => { dirty.current.add(id); setRev(r => r + 1); };
  const step = (from: typeof undo, to: typeof undo) => {
    const s = from.current.pop();
    if (!s) return;
    to.current.push({id: s.id, data: maskOf(s.id).slice()});
    masks.current.set(s.id, s.data);
    const k = objs.findIndex(o => o.id === s.id);
    if (k >= 0) setSel(k);
    changed(s.id);
    setHist({undo: undo.current.length, redo: redo.current.length});
  };

  // --- painting tools ------------------------------------------------------------------------------------------
  const apply = (m: Uint8Array, region: (i: number) => boolean, how: Mode) => {
    for (let i = 0; i < m.length; i++) {
      const inside = region(i);
      if (how === "replace") m[i] = inside ? SEEN : 0;
      else if (inside) m[i] = how === "add" ? SEEN : 0;
    }
  };
  const wand = (sx: number, sy: number) => {
    const px = pixels.current!, seen = new Uint8Array(W * H), stack = [sy * W + sx];
    const s = (sy * W + sx) * 4, R = px[s], G = px[s + 1], B = px[s + 2], lim = (tol * 2.6) ** 2, edge = (tol * 0.9) ** 2;
    seen[sy * W + sx] = 1;
    while (stack.length) {
      const i = stack.pop()!, x = i % W, y = (i / W) | 0;
      for (const n of [x > 0 ? i - 1 : -1, x < W - 1 ? i + 1 : -1, y > 0 ? i - W : -1, y < H - 1 ? i + W : -1]) {
        if (n < 0 || seen[n]) continue;
        const j = n * 4, dr = px[j] - R, dg = px[j + 1] - G, db = px[j + 2] - B;
        const k = i * 4, er = px[j] - px[k], eg = px[j + 1] - px[k + 1], eb = px[j + 2] - px[k + 2];
        // close to the clicked colour, and no sharp edge between neighbours (a door frame, a chair outline)
        if (dr * dr + dg * dg + db * db <= lim && er * er + eg * eg + eb * eb <= edge) { seen[n] = 1; stack.push(n); }
      }
    }
    return seen;
  };
  const dab = (m: Uint8Array, cx: number, cy: number, value: number) => {
    const r = size / 2, r2 = r * r;
    for (let y = Math.max(0, Math.floor(cy - r)); y < Math.min(H, Math.ceil(cy + r)); y++)
      for (let x = Math.max(0, Math.floor(cx - r)); x < Math.min(W, Math.ceil(cx + r)); x++) {
        if ((x - cx) ** 2 + (y - cy) ** 2 > r2) continue;
        const i = y * W + x;
        if (value === HIDDEN) { if (m[i] !== SEEN) m[i] = HIDDEN; } else m[i] = value;
      }
  };
  const stroke = (m: Uint8Array, a: [number, number], b: [number, number], value: number) => {
    const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / Math.max(1, size / 4)));
    for (let k = 0; k <= n; k++) dab(m, a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n, value);
  };
  const fillPolygon = (pts: [number, number][], how: Mode) => {
    const t = document.createElement("canvas");
    t.width = W; t.height = H;
    const g = t.getContext("2d")!;
    g.beginPath();
    pts.forEach(([x, y], k) => (k ? g.lineTo(x, y) : g.moveTo(x, y)));
    g.closePath();
    g.fill();
    const d = g.getImageData(0, 0, W, H).data;
    snapshot(cur.id);
    apply(maskOf(cur.id), i => d[i * 4 + 3] > 127, how);
    changed(cur.id);
    setLasso([]);
  };
  // resample the selected object's mask from one box into another (move / resize)
  const reshape = (from: Uint8Array, a: Box, b: Box) => {
    const m = new Uint8Array(W * H);
    const bw = Math.max(1, b[2] - b[0]), bh = Math.max(1, b[3] - b[1]), aw = a[2] - a[0], ah = a[3] - a[1];
    for (let y = Math.max(0, b[1]); y < Math.min(H, b[3]); y++)
      for (let x = Math.max(0, b[0]); x < Math.min(W, b[2]); x++) {
        const sx = a[0] + Math.floor((x - b[0]) * aw / bw), sy = a[1] + Math.floor((y - b[1]) * ah / bh);
        m[y * W + x] = from[sy * W + sx];
      }
    masks.current.set(cur.id, m);
  };

  const at = (e: {clientX: number; clientY: number}): [number, number] => {
    const r = over.current!.getBoundingClientRect();
    return [Math.max(0, Math.min(W - 1, Math.floor((e.clientX - r.left) / r.width * W))),
            Math.max(0, Math.min(H - 1, Math.floor((e.clientY - r.top) / r.height * H)))];
  };
  const how = (e: RPE): Mode => (e.altKey ? "subtract" : e.shiftKey ? "add" : mode);

  const down = (e: RPE) => {
    if (!dims) return;
    if (e.button === 1 || tool === "pan" || space.current) {
      drag.current = {kind: "pan", x: e.clientX, y: e.clientY, pan};
      (e.target as Element).setPointerCapture(e.pointerId);
      return;
    }
    if (e.button !== 0 || !cur) return;
    const p = at(e);
    (e.target as Element).setPointerCapture(e.pointerId);
    if (tool === "select") {
      const handle = (e.target as HTMLElement).dataset.handle;
      if (handle && box) { snapshot(cur.id); drag.current = {kind: "resize", handle, from: maskOf(cur.id).slice(), box, start: p}; return; }
      if (box && p[0] >= box[0] && p[0] < box[2] && p[1] >= box[1] && p[1] < box[3]) {
        snapshot(cur.id); drag.current = {kind: "move", from: maskOf(cur.id).slice(), box, start: p}; return;
      }
      const hit = objs.findIndex(o => masks.current.get(o.id)?.[p[1] * W + p[0]]);
      if (hit >= 0) setSel(hit);
      return;
    }
    if (tool === "wand") {
      const region = wand(p[0], p[1]);
      snapshot(cur.id);
      apply(maskOf(cur.id), i => region[i] === 1, how(e));
      changed(cur.id);
      return;
    }
    if (tool === "lasso") {
      if (lasso.length > 2 && Math.hypot(p[0] - lasso[0][0], p[1] - lasso[0][1]) < 10 / zoom) return fillPolygon(lasso, how(e));
      setLasso(l => [...l, p]);
      return;
    }
    if (tool === "box") { drag.current = {kind: "box", start: p, now: p, how: how(e)}; return; }
    snapshot(cur.id);
    const value = tool === "brush" ? (e.altKey ? 0 : SEEN) : tool === "hidden" ? (e.altKey ? 0 : HIDDEN) : 0;
    drag.current = {kind: "paint", last: p, value};
    stroke(maskOf(cur.id), p, p, value);
    changed(cur.id);
  };
  const move = (e: RPE) => {
    const d = drag.current;
    if (!d) return;
    if (d.kind === "pan") { setPan({x: d.pan.x + e.clientX - d.x, y: d.pan.y + e.clientY - d.y}); return; }
    const p = at(e);
    if (d.kind === "paint") { stroke(maskOf(cur.id), d.last, p, d.value); d.last = p; changed(cur.id); }
    else if (d.kind === "box") { d.now = p; setRev(r => r + 1); }
    else if (d.kind === "move" || d.kind === "resize") {
      const [x0, y0, x1, y1] = d.box as Box, dx = p[0] - d.start[0], dy = p[1] - d.start[1];
      let b: Box = [x0, y0, x1, y1];
      if (d.kind === "move") b = [x0 + dx, y0 + dy, x1 + dx, y1 + dy];
      else {
        const hnd: string = d.handle;
        if (hnd.includes("w")) b[0] = Math.min(x0 + dx, x1 - 2);
        if (hnd.includes("e")) b[2] = Math.max(x1 + dx, x0 + 2);
        if (hnd.includes("n")) b[1] = Math.min(y0 + dy, y1 - 2);
        if (hnd.includes("s")) b[3] = Math.max(y1 + dy, y0 + 2);
      }
      reshape(d.from, d.box, b);
      changed(cur.id);
    }
  };
  const up = () => {
    const d = drag.current;
    drag.current = null;
    if (d?.kind === "box") {
      const [ax, ay] = d.start, [bx, by] = d.now;
      if (Math.abs(bx - ax) > 2 && Math.abs(by - ay) > 2) {
        const x0 = Math.min(ax, bx), x1 = Math.max(ax, bx), y0 = Math.min(ay, by), y1 = Math.max(ay, by);
        snapshot(cur.id);
        apply(maskOf(cur.id), i => { const x = i % W, y = (i / W) | 0; return x >= x0 && x <= x1 && y >= y0 && y <= y1; }, d.how);
        changed(cur.id);
      } else setRev(r => r + 1);
    }
  };

  const zoomAt = (factor: number, cx?: number, cy?: number) => {
    const r = stage.current!.getBoundingClientRect();
    const x = cx ?? r.left + r.width / 2, y = cy ?? r.top + r.height / 2;
    const z = Math.max(0.1, Math.min(12, zoom * factor)), k = z / zoom;
    setPan(p => ({x: x - r.left - (x - r.left - p.x) * k, y: y - r.top - (y - r.top - p.y) * k}));
    setZoom(z);
  };
  useEffect(() => {
    const el = stage.current!;
    const wheel = (e: WheelEvent) => { e.preventDefault(); zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY); };
    el.addEventListener("wheel", wheel, {passive: false});
    return () => el.removeEventListener("wheel", wheel);
  });

  const clear = () => { if (!cur) return; snapshot(cur.id); maskOf(cur.id).fill(0); changed(cur.id); };
  useEffect(() => {
    const keys: Record<string, Tool> = {v: "select", r: "box", w: "wand", l: "lasso", b: "brush", h: "hidden", e: "eraser"};
    const kd = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, select, textarea")) return;
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === "z") { e.preventDefault(); return e.shiftKey ? step(redo, undo) : step(undo, redo); }
      if ((e.ctrlKey || e.metaKey) && k === "y") { e.preventDefault(); return step(redo, undo); }
      if (e.ctrlKey || e.metaKey) return;
      if (e.key === " ") { space.current = true; e.preventDefault(); return; }
      if (e.key === "Escape") { if (lasso.length) setLasso([]); else onClose(); return; }
      if (e.key === "Enter" && lasso.length > 2) return fillPolygon(lasso, mode);
      if (e.key === "Delete" || e.key === "Backspace") return clear();
      if (e.key === "[") return setSize(s => Math.max(2, Math.round(s / 1.25)));
      if (e.key === "]") return setSize(s => Math.min(200, Math.round(s * 1.25)));
      if (e.key === "+" || e.key === "=") return zoomAt(1.25);
      if (e.key === "-") return zoomAt(0.8);
      if (e.key === "0") return fit();
      if (keys[k]) setTool(keys[k]);
    };
    const ku = (e: KeyboardEvent) => { if (e.key === " ") space.current = false; };
    addEventListener("keydown", kd);
    addEventListener("keyup", ku);
    return () => { removeEventListener("keydown", kd); removeEventListener("keyup", ku); };
  });

  // --- saving: every changed mask goes up as a PNG; the box comes back ----------------------------------------
  const png = (m: Uint8Array) => new Promise<Blob>(res => {
    const t = document.createElement("canvas");
    t.width = W; t.height = H;
    const g = t.getContext("2d")!, img = g.createImageData(W, H);
    for (let i = 0; i < m.length; i++) { const j = i * 4; img.data[j] = img.data[j + 1] = img.data[j + 2] = m[i]; img.data[j + 3] = 255; }
    g.putImageData(img, 0, 0);
    t.toBlob(b => res(b!), "image/png");
  });
  const save = async (close: boolean) => {
    setSaving(true);
    try {
      const next = structuredClone(objs);
      for (const p of next) {
        if (!dirty.current.has(p.id)) continue;
        const m = maskOf(p.id);
        if (!m.some(v => v)) { delete p.picture_rect; delete p.picture_mask; continue; }
        const r = await form<{mask: string; rect: number[]}>("/api/set/mask", {movie, set: setName, id: p.id, mask: await png(m)});
        p.picture_rect = r.rect;
        p.picture_mask = r.mask;
      }
      await onApply(next);
      setObjs(next);
      dirty.current.clear();
      toast("Regions saved");
      if (close) onClose();
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setSaving(false); }
  };
  const fill = async () => {
    if (!cur) return;
    if (dirty.current.size) await save(false);
    try { setFilled((await post<{url: string}>("/api/set/fill", {movie, set: setName, id: cur.id})).url); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const addObject = () => {
    const base = newType.replace(/[^a-z0-9_]/g, "_");
    let n = 1;
    while (objs.some(o => o.id === `${base}_${n}`)) n++;
    const id = `${base}_${n}`;
    masks.current.set(id, new Uint8Array(W * H));
    setObjs(o => [...o, {id, make: newType, position: [0, 0], rotation: 0, size: [...(schema?.props[newType]?.size || [1, 1, 1])]}]);
    setSel(objs.length);
    dirty.current.add(id);
  };

  const d = drag.current;
  const live = d?.kind === "box" ? [Math.min(d.start[0], d.now[0]), Math.min(d.start[1], d.now[1]), Math.abs(d.now[0] - d.start[0]), Math.abs(d.now[1] - d.start[1])] : null;
  const hsize = 9 / zoom;
  const cursor = tool === "pan" || space.current ? "grab" : tool === "select" ? "default" : "crosshair";
  const types = Object.keys(schema?.props || {}).filter(n => n !== "picture_road");
  return (
    <div className="annot">
      <div className="annot-top">
        <b>Regions · {setName}</b>
        <span className="muted small">Mark exactly what belongs to each object. Hidden parts tell the build where the object continues behind something.</span>
        <div className="spacer" />
        <Button size="sm" variant="ghost" square icon={<Undo2 size={15} />} disabled={!hist.undo} onClick={() => step(undo, redo)} title="Undo (Ctrl+Z)" />
        <Button size="sm" variant="ghost" square icon={<Redo2 size={15} />} disabled={!hist.redo} onClick={() => step(redo, undo)} title="Redo (Ctrl+Shift+Z)" />
        <Button size="sm" variant="ghost" square icon={<ZoomOut size={15} />} onClick={() => zoomAt(0.8)} title="Zoom out (-)" />
        <span className="small dim" style={{width: 44, textAlign: "center"}}>{Math.round(zoom * 100)}%</span>
        <Button size="sm" variant="ghost" square icon={<ZoomIn size={15} />} onClick={() => zoomAt(1.25)} title="Zoom in (+)" />
        <Button size="sm" variant="ghost" square icon={<Maximize size={15} />} onClick={() => fit()} title="Fit (0)" />
        <Button size="sm" icon={<Save size={14} />} busy={saving} onClick={() => save(false)}>Save</Button>
        <Button size="sm" variant="primary" busy={saving} onClick={() => save(true)}>Save and close</Button>
        <Button size="sm" variant="ghost" square icon={<X size={16} />} onClick={onClose} aria-label="Close" />
      </div>
      <div className="annot-body">
        <div className="annot-tools">
          {TOOLS.map(([t, tip, Icon, key]) => (
            <button key={t} className={`tool ${tool === t ? "on" : ""}`} title={`${tip} (${key})`} onClick={() => setTool(t)}><Icon size={17} /></button>
          ))}
        </div>
        <div ref={stage} className="annot-stage" style={{cursor}} onPointerDown={down} onPointerMove={move} onPointerUp={up}
             onDoubleClick={() => { if (tool === "lasso" && lasso.length > 2) fillPolygon(lasso, mode); }}>
          <div className="annot-canvas" style={{width: W, height: H, transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`}}>
            <canvas ref={base} />
            <canvas ref={over} className="layer" />
            {dims && (
              <svg className="layer" viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
                {live && <rect x={live[0]} y={live[1]} width={live[2]} height={live[3]} className="sel-box" style={{strokeWidth: 1.5 / zoom}} />}
                {lasso.length > 0 && <polyline points={lasso.map(p => p.join(",")).join(" ")} className="lasso" style={{strokeWidth: 1.5 / zoom}} />}
                {lasso.length > 0 && <circle cx={lasso[0][0]} cy={lasso[0][1]} r={5 / zoom} className="lasso-start" />}
                {tool === "select" && box && (
                  <g>
                    <rect x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]} className="sel-box" style={{strokeWidth: 1.5 / zoom}} />
                    {[["nw", box[0], box[1]], ["n", (box[0] + box[2]) / 2, box[1]], ["ne", box[2], box[1]], ["e", box[2], (box[1] + box[3]) / 2],
                      ["se", box[2], box[3]], ["s", (box[0] + box[2]) / 2, box[3]], ["sw", box[0], box[3]], ["w", box[0], (box[1] + box[3]) / 2]].map(([h, x, y]) => (
                      <rect key={h as string} data-handle={h} x={(x as number) - hsize / 2} y={(y as number) - hsize / 2} width={hsize} height={hsize}
                            className={`handle h-${h}`} style={{strokeWidth: 1.5 / zoom}} />
                    ))}
                  </g>
                )}
              </svg>
            )}
          </div>
          {!dims && <div className="vp-empty"><span className="spinner" /></div>}
        </div>
        <aside className="annot-side">
          <div className="annot-section">
            <h4>Tool</h4>
            {["box", "wand", "lasso"].includes(tool) && (
              <div className="segmented" style={{width: "100%"}}>
                {(["replace", "add", "subtract"] as Mode[]).map(m => <button key={m} className={mode === m ? "on" : ""} style={{flex: 1}} onClick={() => setMode(m)}>{m}</button>)}
              </div>
            )}
            {tool === "wand" && <label className="slider">Similarity <input type="range" min={2} max={90} value={tol} onChange={e => setTol(+e.target.value)} /><span>{tol}</span></label>}
            {["brush", "hidden", "eraser"].includes(tool) && <label className="slider">Size <input type="range" min={2} max={200} value={size} onChange={e => setSize(+e.target.value)} /><span>{size}</span></label>}
            <p className="hint">{{
              select: "Click an object to select it. Drag inside its box to move it; drag a handle to resize.",
              box: "Drag a box. Shift adds to the region, Alt subtracts.",
              wand: "Click the object: neighbouring pixels of similar colour are selected. Click again to add the parts it missed (Shift), Alt-click to remove.",
              lasso: "Click around the outline; click the first point, double-click or press Enter to close. Esc cancels.",
              brush: "Paint the object. Alt paints it away. [ and ] change the size.",
              hidden: "Paint where the object continues behind something (a chair leg behind the table). The build fills it with the object's own colours.",
              eraser: "Remove parts of the region.",
              pan: "Drag to move the picture. The mouse wheel zooms.",
            }[tool]}</p>
          </div>
          <div className="annot-section" style={{flex: 1, minHeight: 0, overflowY: "auto"}}>
            <h4>Objects</h4>
            {objs.map((o, k) => {
              const m = masks.current.get(o.id), any = m?.some(v => v), hid = m?.some(v => v === HIDDEN);
              return (
                <button key={o.id} className={`obj ${k === sel ? "on" : ""}`} onClick={() => { setSel(k); setFilled(null); }}>
                  <i style={{background: COLORS[k % COLORS.length]}} />
                  <span>{o.id}<small>{(o.make || "").replace(/_/g, " ")}</small></span>
                  {any ? <Badge kind="ok">marked</Badge> : <Badge>empty</Badge>}
                  {hid && <Badge kind="warn">hidden</Badge>}
                </button>
              );
            })}
            <div className="row nowrap" style={{marginTop: 8}}>
              <Select className="sm" value={newType} onChange={setNewType} options={types} />
              <Button size="sm" icon={<Plus size={14} />} onClick={addObject}>Add</Button>
            </div>
          </div>
          {cur && (
            <div className="annot-section">
              <h4>{cur.id}</h4>
              <div className="row">
                <Button size="sm" icon={<Sparkles size={14} />} onClick={fill} title="Saves, then fills the hidden parts">Preview hidden fill</Button>
                <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={clear}>Clear</Button>
              </div>
              {filled && <img src={filled} alt="filled object" className="filled" />}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
