// The live body beside the sliders: it changes as you drag, so nothing has to be agreed to unseen.
// It shows the SHAPE only - hair, beard, clothes and skin come from a build - and says so.
import {useEffect, useRef, useState} from "react";
import {Camera, Check, Grid3x3, Lightbulb, Loader2, Maximize2, Move3d, RefreshCw, Rotate3d,
        Scaling, SunMoon, X} from "lucide-react";
import * as THREE from "three";
import {api, Json, post, Schema} from "../../api";
import {Button, Segmented} from "../../components/ui";
import {BodyView, CostumeLook, Kit, PartSpec, RING_SPIN, RING_TIP, ViewLook, Worn, WornSpec}
  from "./bodyview";

const get = (d: Json, key: string) => key.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), d);

/** Which morph targets a design asks for: the browser's half of core/appearance.targets_for. */
export function targetsFor(design: Json, schema: Schema): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [key, pair] of Object.entries(schema.slider_targets || {})) {
    const raw = Number(get(design, key) || 0);
    if (!raw) continue;
    const value = Math.max(-1, Math.min(1, raw));
    for (const name of value > 0 ? pair.plus : pair.minus) out[name] = (out[name] || 0) + Math.abs(value);
  }
  const shape = get(design, "face.head_shape") as string;
  const target = schema.head_shapes?.[shape];
  if (target) out[target] = Math.max(out[target] || 0, 1);
  return out;
}

interface WearItem extends WornSpec { json: string; bin: string }

/** The colour a worn thing takes from the design, or none (then its own texture shows as it is). */
function tintOf(design: Json, tint: string | null): string | undefined {
  if (!tint) return undefined;
  const value = get(design, tint);
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : undefined;
}

/** One dial in the part bar. Double-click puts it back to the middle, like every other slider here. */
function Dial({label, value, min, max, step, middle, show, onChange}: {
  label: string; value: number; min: number; max: number; step: number; middle: number;
  show: (v: number) => string; onChange: (v: number) => void;
}) {
  return (
    <label className={`part-dial ${Math.abs(value - middle) > 1e-9 ? "set" : ""}`}>
      <span>{label}</span>
      <input type="range" min={min} max={max} step={step} value={value}
             onChange={e => onChange(Number(e.target.value))} onDoubleClick={() => onChange(middle)} />
      <i>{show(value)}</i>
    </label>
  );
}

const at = (v: [number, number, number] | undefined, i: number) => (v ? v[i] : 0);
const put = (v: [number, number, number] | undefined, i: number, x: number) => {
  const out: [number, number, number] = v ? [...v] as [number, number, number] : [0, 0, 0];
  out[i] = x;
  return out;
};
const cm = (v: number) => `${v > 0 ? "+" : ""}${Math.round(v * 100)} cm`;
const deg = (v: number) => `${v > 0 ? "+" : ""}${Math.round(v)}°`;

const partName = (on: string) => ({body: "body", hat: "hat", top: "top", bottom: "trousers",
                                   outfit: "outfit", shoes: "shoes", hair: "hair", beard: "beard"}[on] || on);

export function LivePreview({design, schema, focus, onParts, touching}: {
  design: Json; schema: Schema; focus: "whole" | "face" | "body";
  onParts?: (parts: PartSpec[]) => void;
  touching?: string | null;              // the slider the hand is on, so the view can show what it moves
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const view = useRef<BodyView | null>(null);
  const [state, setState] = useState<"off" | "making" | "ready" | "failed">("off");
  const [note, setNote] = useState("");
  const [rings, setRings] = useState(true);
  const [dressing, setDressing] = useState(false);
  const [picking, setPicking] = useState(false);          // a click chooses a part instead of turning
  const [look, setLook] = useState<ViewLook>({light: "studio", background: "dark",
                                              wireframe: false, turntable: false});
  const [draft, setDraft] = useState<PartSpec | null>(null);
  const [cover, setCover] = useState(0);                  // how much of the thing the part covers
  const saved: PartSpec[] = Array.isArray(get(design, "parts")) ? (get(design, "parts") as PartSpec[]) : [];
  const wornRef = useRef<{spec: WornSpec; bin: ArrayBuffer; texture: THREE.Texture | null}[]>([]);
  // only these change WHAT is worn; the sliders and the colours never do, so they never refetch
  const outfitKey = JSON.stringify([get(design, "gender"), get(design, "hair.style"), get(design, "hair.length"),
                                    get(design, "beard"), get(design, "hat"), get(design, "eyebrows"),
                                    get(design, "outfit.style"), get(design, "outfit.garment"),
                                    get(design, "outfit.sleeves"), !!get(design, "costume.boots")]);
  const costume: CostumeLook = {
    trim: tintOf(design, "costume.trim") || null, belt: tintOf(design, "costume.belt") || null,
    buckle: tintOf(design, "costume.buckle") || null, gloves: tintOf(design, "costume.gloves") || null,
    boots: !!get(design, "costume.boots"), sleeves: (get(design, "outfit.sleeves") as string) || null,
  };
  const colourKey = JSON.stringify([get(design, "skin"), get(design, "hair.color"), get(design, "outfit.top"),
                                    get(design, "outfit.bottom"), get(design, "outfit.shoes"), get(design, "hat_size"), costume]);
  // the body underneath the sliders: only these three change it, so only these three fetch a new one
  const shape = [get(design, "gender") || "female", get(design, "age") || 30,
                 get(design, "build") || "average", get(design, "height_cm") || 170].join("|");

  useEffect(() => {                       // one viewer for the life of the panel
    if (!canvas.current) return;
    view.current = new BodyView(canvas.current);
    const onResize = () => view.current?.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); view.current?.dispose(); view.current = null; };
  }, []);

  useEffect(() => {                       // a different body: fetch its kit (made once, then kept)
    let dropped = false;
    (async () => {
      setState("making");
      setNote("");
      try {
        const [gender, age, build, height] = shape.split("|");
        const where = await api<{json: string; bin: string; made: boolean}>(
          `/api/character/preview-kit?gender=${gender}&age=${age}&build=${build}&height_cm=${height}`);
        const [kit, bin] = await Promise.all([
          fetch(where.json).then(r => r.json() as Promise<Kit>),
          fetch(where.bin).then(r => r.arrayBuffer()),
        ]);
        if (dropped) return;
        await view.current?.load(kit, bin);
        view.current?.apply(targetsFor(design, schema));
        view.current?.resize();
        setState("ready");
      } catch (e) {
        if (!dropped) { setState("failed"); setNote((e as Error).message); }
      }
    })();
    return () => { dropped = true; };
  }, [shape]);                            // eslint-disable-line react-hooks/exhaustive-deps

  const asked = JSON.stringify(targetsFor(design, schema));
  useEffect(() => {                       // every slider move lands here: a few hundred adds, no server
    if (state === "ready") view.current?.apply(JSON.parse(asked));
  }, [asked, state]);

  useEffect(() => {                       // what the design is wearing: fetched only when the outfit changes
    let dropped = false;
    (async () => {
      setDressing(true);
      try {
        const r = await post<{wearing: WearItem[]; problems: string[]}>("/api/character/wear", {design});
        const loader = new THREE.TextureLoader();
        const items = await Promise.all(r.wearing.map(async item => {
          const [spec, bin] = await Promise.all([
            fetch(item.json).then(x => x.json() as Promise<WornSpec>),
            fetch(item.bin).then(x => x.arrayBuffer()),
          ]);
          const texture = item.texture
            ? await new Promise<THREE.Texture | null>(done =>
                loader.load(item.texture!, t => { t.colorSpace = THREE.SRGBColorSpace; done(t); }, undefined, () => done(null)))
            : null;
          return {spec: {...spec, role: item.role, tint: item.tint}, bin, texture};
        }));
        if (dropped) return;
        wornRef.current = items;
        paint();
      } catch { /* a missing wardrobe must not take the body down with it */ }
      finally { if (!dropped) setDressing(false); }
    })();
    return () => { dropped = true; };
  }, [outfitKey, state === "ready"]);     // eslint-disable-line react-hooks/exhaustive-deps

  const paint = () => {
    const skin = tintOf(design, "skin");
    view.current?.setSkin(skin);
    view.current?.setWearing(wornRef.current.map(w => ({
      spec: w.spec, bin: w.bin, texture: w.texture, colour: tintOf(design, w.spec.tint),
    } as Worn)));
    view.current?.setHatSize(Number(get(design, "hat_size") || 1));
    view.current?.setCostume(costume);              // after the clothes: the costume is drawn over them
  };
  useEffect(() => { paint(); }, [colourKey]);   // eslint-disable-line react-hooks/exhaustive-deps

  // what is being resized right now: everything already kept, plus the one being tried
  useEffect(() => {
    view.current?.setParts(draft ? [...saved, draft] : saved);
    setCover(draft ? view.current?.choose(draft) || 0 : 0);
  }, [JSON.stringify(saved), JSON.stringify(draft)]);     // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!view.current) return;
    view.current.picking = picking;
    view.current.onPick = spec => { setDraft(spec); setPicking(false); };
    if (!picking && !draft) view.current.choose(null);
  }, [picking, draft]);

  const keep = () => { if (draft) onParts?.([...saved, draft]); setDraft(null); };
  const drop = (i: number) => onParts?.(saved.filter((_, k) => k !== i));

  useEffect(() => { view.current?.setLook(look); }, [JSON.stringify(look), state]);  // eslint-disable-line react-hooks/exhaustive-deps

  const takePicture = () => {
    const png = view.current?.snapshot();
    if (!png) return;
    const a = document.createElement("a");
    a.href = png;
    a.download = `${String(get(design, "name") || "character")}.png`;
    a.click();
  };

  useEffect(() => {                      // light up what the slider under the hand actually moves
    const pair = touching ? schema.slider_targets?.[touching] : null;
    view.current?.showTargets(pair ? [...pair.plus, ...pair.minus] : null);
  }, [touching, state]);                 // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { view.current?.frame(focus); }, [focus]);
  useEffect(() => { view.current?.showRings(rings); }, [rings]);

  return (
    <div className="live-preview">
      <div className="live-stage">
        <canvas ref={canvas} />
        {state !== "ready" && (
          <div className="live-cover">
            {state === "failed"
              ? <div className="stack" style={{justifyItems: "center", gap: 6, padding: 16, textAlign: "center"}}>
                  <b>The live body is not available</b>
                  <span className="muted small">{note || "it could not be made"}</span>
                  <Button variant="ghost" icon={<RefreshCw size={14} />} onClick={() => setState("off")}>Try again</Button>
                </div>
              : <div className="stack" style={{justifyItems: "center", gap: 8}}>
                  <Loader2 size={22} className="spin" />
                  <b>Shaping the body…</b>
                  <span className="muted small">about eight seconds, once per age, sex and build</span>
                </div>}
          </div>
        )}
        {state === "ready" && (
          <div className="live-hint">
            <span><i style={{background: RING_SPIN}} />turn</span>
            <span><i style={{background: RING_TIP}} />tip</span>
            <span className="muted">drag to turn · right-drag to slide · wheel to zoom in on what you point at ·
              double-click a part to look at it</span>
            {dressing && <span className="muted">· dressing…</span>}
          </div>
        )}
      </div>
      {(draft || saved.length > 0) && (
        <div className="part-bar">
          {draft ? (
            <>
              <div className="part-head">
                <b>{partName(draft.on)}</b>
                <span className="muted small">
                  {cover > 0.75
                    ? `that is ${Math.round(cover * 100)}% of the ${partName(draft.on)} - almost all of it. `
                      + "Sizing a whole hat is what the Hat size dial is for; a part is meant to be smaller."
                    : `${Math.round(cover * 100)}% of the ${partName(draft.on)}. Everything you change `
                      + "fades out towards where this part joins on, so it stays attached."}
                </span>
                <span className="spacer" />
                <Button variant="primary" icon={<Check size={14} />} onClick={keep}>Keep</Button>
                <Button variant="ghost" icon={<X size={14} />} onClick={() => setDraft(null)}>Cancel</Button>
              </div>
              <div className="part-dials">
                <Dial label="How much of it" value={draft.radius} min={0.02} max={0.3} step={0.01}
                      middle={0.08} show={v => `${Math.round(v * 100)} cm`}
                      onChange={v => setDraft({...draft, radius: v})} />
                <Dial label="Size" value={draft.scale} min={0.5} max={2} step={0.05} middle={1}
                      show={v => `x${v.toFixed(2)}`}
                      onChange={v => setDraft({...draft, scale: v})} />
                <Dial label="Left / right" value={at(draft.move, 0)} min={-0.2} max={0.2} step={0.005}
                      middle={0} show={cm} onChange={v => setDraft({...draft, move: put(draft.move, 0, v)})} />
                <Dial label="Up / down" value={at(draft.move, 2)} min={-0.2} max={0.2} step={0.005}
                      middle={0} show={cm} onChange={v => setDraft({...draft, move: put(draft.move, 2, v)})} />
                <Dial label="Front / back" value={at(draft.move, 1)} min={-0.2} max={0.2} step={0.005}
                      middle={0} show={cm} onChange={v => setDraft({...draft, move: put(draft.move, 1, v)})} />
                <Dial label="Lean left / right" value={at(draft.turn, 1)} min={-60} max={60} step={1}
                      middle={0} show={deg} onChange={v => setDraft({...draft, turn: put(draft.turn, 1, v)})} />
                <Dial label="Tip forward / back" value={at(draft.turn, 0)} min={-60} max={60} step={1}
                      middle={0} show={deg} onChange={v => setDraft({...draft, turn: put(draft.turn, 0, v)})} />
                <Dial label="Twist" value={at(draft.turn, 2)} min={-60} max={60} step={1}
                      middle={0} show={deg} onChange={v => setDraft({...draft, turn: put(draft.turn, 2, v)})} />
              </div>
            </>
          ) : (
            <>
              <span className="muted small">Resized:</span>
              {saved.map((part, i) => (
                <button key={i} className="part-chip" onClick={() => drop(i)}
                        title="Put this part back to its own size">
                  {partName(part.on)} x{part.scale.toFixed(2)} <X size={11} />
                </button>
              ))}
            </>
          )}
        </div>
      )}
      <div className="view-bar">
        <span className="view-group" title="The light on the character">
          <Lightbulb size={13} />
          {(["studio", "warm", "cool", "flat"] as const).map(l => (
            <button key={l} className={`view-pip ${look.light === l ? "on" : ""}`}
                    onClick={() => setLook(v => ({...v, light: l}))}>{l}</button>
          ))}
        </span>
        <span className="view-group" title="What is behind the character">
          <SunMoon size={13} />
          {(["dark", "grey", "light"] as const).map(b => (
            <button key={b} className={`view-pip ${look.background === b ? "on" : ""}`}
                    onClick={() => setLook(v => ({...v, background: b}))}>{b}</button>
          ))}
        </span>
        <span className="spacer" />
        <button className={`view-pip ${look.wireframe ? "on" : ""}`} title="See the mesh itself"
                onClick={() => setLook(v => ({...v, wireframe: !v.wireframe}))}><Grid3x3 size={13} /> mesh</button>
        <button className={`view-pip ${look.turntable ? "on" : ""}`} title="Turn slowly on its own"
                onClick={() => setLook(v => ({...v, turntable: !v.turntable}))}><Rotate3d size={13} /> spin</button>
        <button className="view-pip" title="Save a picture of this view" onClick={takePicture}>
          <Camera size={13} /> photo
        </button>
      </div>
      <div className="live-bar">
        <Segmented value="" onChange={v => view.current?.turnTo(v as "front")}
                   options={[["front", "Front"], ["three_quarter", "3/4"], ["side", "Side"], ["back", "Back"]]} />
        <span className="spacer" />
        <Button variant="ghost" icon={<Move3d size={14} />} onClick={() => setRings(r => !r)}
                title="Show or hide the rings">{rings ? "Rings on" : "Rings off"}</Button>
        <Button variant={picking ? "primary" : "ghost"} icon={<Scaling size={14} />}
                onClick={() => { setPicking(p_ => !p_); setDraft(null); }}
                title="Click a part of the character and make it bigger or smaller">
          {picking ? "Click a part…" : "Resize a part"}
        </Button>
        <Button variant="ghost" icon={<Maximize2 size={14} />} onClick={() => view.current?.frame("whole")}>Fit</Button>
      </div>
      <p className="live-note muted small">
        The character as it will be built: the body from the sliders, dressed in what you have picked.
        Cloth is held clear of the skin, so nothing pokes through as you reshape the body. Fur trim, the
        belt and buckle, gloves and fur-topped boots show here too; a cape, a hood and armour are made at
        build time and appear in the built character.
      </p>
    </div>
  );
}
