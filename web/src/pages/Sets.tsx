// Sets: a picture of a place, with the 3D details people use (doors, seats, tables) marked on it, built into a
// reusable 3D set. Building never changes the movie's scenes.
import {PointerEvent as RPE, useEffect, useRef, useState} from "react";
import {Crop, Download, Hammer, Image as ImageIcon, Plus, Save, Trash2, X} from "lucide-react";
import {form, Json, post, SetInfo} from "../api";
import {useStore} from "../app/store";
import {Badge, Button, Card, Empty, Field, Modal, PageHead, PictureDrop, Select} from "../components/ui";

export function Sets() {
  const {current, movie, toast, reload} = useStore();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [pic, setPic] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const add = async () => {
    if (!name.trim() || !pic) return toast("Give the set a name and a picture.", "err");
    setBusy(true);
    try {
      await form("/api/set/new", {movie, name: name.trim(), picture: pic});
      toast(`Set ${name} added`);
      setName(""); setPic(null); setAdding(false);
      await reload(movie);
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  };
  const sets = current?.sets || [];
  return (
    <div className="page">
      <PageHead eyebrow="Assets" title="Sets"
                text="Mark each door, seat and table on the set picture, give it a real size, then build a reusable 3D set. Building does not change your scenes."
                actions={<Button variant="primary" icon={<Plus size={16} />} onClick={() => setAdding(true)}>Add set</Button>} />
      {sets.length === 0
        ? <Card><Empty icon={<ImageIcon />} title="No sets yet" text="Add a picture of a place: an eye-level photo of the empty room or street, 16:9." /></Card>
        : <div className="stack lg">{sets.map(s => <SetCard key={s.name} set={s} all={sets} />)}</div>}
      {adding && (
        <Modal title="Add a set" text="A picture of the empty place, eye level, 16:9 (Gemini can make one)." onClose={() => setAdding(false)}
               foot={<><div className="spacer" /><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button variant="primary" busy={busy} onClick={add}>Add set</Button></>}>
          <div className="stack">
            <Field label="Name" required><input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="truck_cab" autoFocus /></Field>
            <Field label="Picture" required><PictureDrop file={pic} onFile={setPic} label="Set picture" /></Field>
          </div>
        </Modal>
      )}
    </div>
  );
}

function SetCard({set, all}: {set: SetInfo; all: SetInfo[]}) {
  const {schema, movie, toast} = useStore();
  const [bp, setBp] = useState<Json>(() => structuredClone(set.blueprint || {description: "", props: []}));
  const [drawing, setDrawing] = useState<number | null>(null);
  const [draft, setDraft] = useState<number[] | null>(null);
  const [newType, setNewType] = useState("door");
  const [busy, setBusy] = useState("");
  const stage = useRef<HTMLDivElement>(null);
  const start = useRef<{x: number; y: number} | null>(null);
  useEffect(() => { setBp(structuredClone(set.blueprint || {description: "", props: []})); }, [set.name]);   // another set
  if (!schema) return null;
  const types = Object.entries(schema.props).filter(([n]) => n !== "picture_road");
  const props: Json[] = Array.isArray(bp.props) ? bp.props : [];
  const edit = (fn: (b: Json) => void) => setBp((b: Json) => { const n = structuredClone(b); if (!Array.isArray(n.props)) n.props = []; fn(n); return n; });
  const point = (e: RPE) => {
    const r = stage.current!.getBoundingClientRect();
    return {x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)), y: Math.max(0, Math.min(1, (e.clientY - r.top) / r.height))};
  };
  const save = async (build: boolean) => {
    setBusy(build ? "build" : "save");
    try {
      const r = await post<{blueprint: Json; job?: string}>(build ? "/api/set/build" : "/api/set/blueprint", {movie, set: set.name, blueprint: bp});
      setBp(r.blueprint);
      toast(build ? "Building the 3D set: a few minutes the first time. Your scenes are unchanged." : "Set details saved", build ? "info" : "ok");
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(""); }
  };
  const marks = props.map((p, i) => ({p, i, r: i === drawing && draft ? draft : p.picture_rect}))
    .filter(x => Array.isArray(x.r) && x.r.length === 4);
  return (
    <Card title={set.name} text={<code>{set.path}</code>}
          actions={<div className="row nowrap">
            {set.asset ? <Badge kind="ok" pip>3D set built</Badge> : <Badge>Not built</Badge>}
            {set.asset && <a className="btn sm" href={set.asset} download><Download size={14} />.blend</a>}
            <Button size="sm" icon={<Save size={14} />} busy={busy === "save"} onClick={() => save(false)}>Save details</Button>
            <Button size="sm" variant="primary" icon={<Hammer size={14} />} busy={busy === "build"} onClick={() => save(true)}>Build 3D set</Button>
          </div>}>
      <div className="grid-2" style={{alignItems: "start"}}>
        <div className="stack">
          <div ref={stage} className={`set-stage ${drawing !== null ? "drawing" : ""}`}
               onPointerDown={e => { if (drawing === null) return; e.preventDefault(); (e.target as Element).setPointerCapture(e.pointerId); start.current = point(e); }}
               onPointerMove={e => { if (!start.current) return; const p = point(e), s = start.current; setDraft([Math.min(s.x, p.x), Math.min(s.y, p.y), Math.max(s.x, p.x), Math.max(s.y, p.y)]); }}
               onPointerUp={() => {
                 if (start.current && draft && drawing !== null && draft[2] - draft[0] >= 0.01 && draft[3] - draft[1] >= 0.01) {
                   const rect = draft, i = drawing;
                   edit(b => { b.props[i].picture_rect = rect; });
                 }
                 start.current = null; setDraft(null); setDrawing(null);
               }}>
            <img src={set.picture} alt={set.name} draggable={false} />
            {marks.map(({p, i, r}) => {
              const [l, t, rr, bb] = r.map((v: number) => Math.max(0, Math.min(1, v)) * 100);
              return <div key={i} className="set-mark" style={{left: `${l}%`, top: `${t}%`, width: `${rr - l}%`, height: `${bb - t}%`}}><span>{p.id || p.make}</span></div>;
            })}
          </div>
          {drawing !== null && <span className="muted small">Drag across the picture to mark “{props[drawing]?.id}”.</span>}
          {set.preview && <figure style={{margin: 0}}><img src={set.preview} alt="3D build preview" style={{width: "100%", borderRadius: 8}} /><figcaption className="muted small">Generated 3D preview</figcaption></figure>}
        </div>
        <div className="stack">
          <Field label="Notes" hint="Stored with the blueprint; they do not change the geometry.">
            <input className="input" maxLength={2000} value={bp.description || ""} onChange={e => edit(b => { b.description = e.target.value; })} placeholder="Optional notes" />
          </Field>
          <div className="item-list">
            {props.length === 0 && <p className="muted" style={{margin: 0}}>No 3D details marked yet. Add one, then mark the matching area on the picture.</p>}
            {props.map((p, i) => {
              const size = p.size || schema.props[p.make]?.size || [1, 1, 1];
              const pos = p.position || [0, 0];
              return (
                <div key={i} className="item">
                  <div className="item-head">
                    <input className="input sm" style={{width: 140}} value={p.id || ""} onChange={e => edit(b => { b.props[i].id = e.target.value; })} aria-label="Object id" />
                    <Select className="sm" value={p.make} options={types.map(([n]) => n)} onChange={v => edit(b => {
                      b.props[i].make = v; b.props[i].size = [...(schema.props[v]?.size || [1, 1, 1])];
                      if (v !== "door") delete b.props[i].outside_set;
                    })} />
                    <div className="spacer" />
                    <Button size="sm" icon={<Crop size={14} />} onClick={() => setDrawing(i)}>{p.picture_rect ? "Redraw" : "Mark region"}</Button>
                    {p.picture_rect && <Button size="sm" variant="ghost" square icon={<X size={14} />} aria-label="Clear region" onClick={() => edit(b => { delete b.props[i].picture_rect; })} />}
                    <Button size="sm" variant="ghost" square icon={<Trash2 size={14} />} aria-label="Remove" onClick={() => edit(b => { b.props.splice(i, 1); })} />
                  </div>
                  <div className="item-body form-grid" style={{gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))"}}>
                    {["Width", "Depth", "Height"].map((d, k) => (
                      <Field key={d} label={`${d} m`}><input className="input" type="number" min={0.01} step={0.05} value={size[k]}
                        onChange={e => edit(b => { b.props[i].size = [...size]; b.props[i].size[k] = Number(e.target.value); })} /></Field>
                    ))}
                    <Field label="Rotation °"><input className="input" type="number" step={5} value={p.rotation ?? 0} onChange={e => edit(b => { b.props[i].rotation = Number(e.target.value); })} /></Field>
                    {[0, 1].map(k => (
                      <Field key={k} label={`Position ${"XY"[k]} m`}><input className="input" type="number" step={0.1} value={pos[k]}
                        onChange={e => edit(b => { b.props[i].position = [...pos]; b.props[i].position[k] = Number(e.target.value); })} /></Field>
                    ))}
                    {p.make === "door" && (
                      <Field label="Outside the door" wide><Select value={p.outside_set || ""} placeholder="No linked set"
                        options={all.filter(s => s.name !== set.name).map(s => s.name)}
                        onChange={v => edit(b => { if (v) b.props[i].outside_set = v; else delete b.props[i].outside_set; })} /></Field>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="row nowrap">
            <Select className="sm" value={newType} onChange={setNewType} options={types.map(([n]) => n)} />
            <Button size="sm" icon={<Plus size={14} />} onClick={() => edit(b => {
              const base = newType.replace(/[^a-z0-9_]/g, "_");
              let n = b.props.filter((x: Json) => x.id?.startsWith(base + "_")).length + 1;
              while (b.props.some((x: Json) => x.id === `${base}_${n}`)) n++;
              b.props.push({id: `${base}_${n}`, make: newType, position: [0, 0], rotation: 0, size: [...(schema.props[newType]?.size || [1, 1, 1])]});
            })}>Add set detail</Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
