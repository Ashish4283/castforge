import {useState} from "react";
import {Armchair, Plus, Trash2, UserPlus} from "lucide-react";
import {Json, label} from "../../api";
import {useStore} from "../../app/store";
import {parsePoint, useEpisode} from "../../app/episode";
import {Badge, Button, Card, ColorField, Field, Select} from "../../components/ui";
import {ParamInput} from "../../components/ParamInput";

export const COLORS = ["#e0574d", "#4f9dde", "#5cc985", "#e5a54a", "#b07fe0", "#4fc6c0"];
const isObj = (v: Json) => v && typeof v === "object" && !Array.isArray(v);

export function SceneSetup() {
  const {schema} = useStore();
  const ep = useEpisode();
  if (!schema || !ep.model) return null;
  const target = () => ep.scene() || ep.model;
  const value = (key: string) => ep.scene()?.[key] ?? ep.model[key];
  return (
    <div className="stack lg">
      <Card title="Scene settings" text="Set picture, floor, light, weather, sound bed and camera style for this scene.">
        <div className="form-grid">
          {Object.entries(schema.scene).map(([key, def]) => (
            <Field key={key} label={<span style={{textTransform: "capitalize"}}>{label(key)}</span>} hint={def.help} required={def.required}>
              <ParamInput name={key} def={def} value={value(key)} onChange={v => ep.update(() => {
                const t = target();
                if (v === null || v === "") delete t[key]; else t[key] = v;
              })} />
            </Field>
          ))}
        </div>
      </Card>
      <div className="grid-2" style={{alignItems: "start"}}>
        <CastEditor />
        <PropsEditor />
      </div>
    </div>
  );
}

function CastEditor() {
  const {schema, current, toast} = useStore();
  const ep = useEpisode();
  const [pick, setPick] = useState("");
  const cast = ep.cast();
  const multi = Array.isArray(ep.model.scenes);
  const local = multi ? (isObj(ep.scene()?.cast) ? ep.scene().cast : {}) : cast;
  const seats = (Array.isArray(ep.scene()?.props) ? ep.scene().props : []).filter((p: Json) => schema!.seats.includes(p?.make)).map((p: Json) => p.id);
  const available = (current?.characters || []).filter(c => !cast[c.name]).map(c => c.name);
  const add = () => ep.update(m => {
    const path = ep.characterPath(pick);
    m.cast = isObj(m.cast) ? m.cast : {};
    if (multi) {
      m.cast[pick] = m.cast[pick] || {character: path};
      const s = ep.scene();
      s.cast = isObj(s.cast) ? s.cast : {};
      s.cast[pick] = {...(s.cast[pick] || {}), position: [0, 0]};
    } else m.cast[pick] = {character: path, position: [0, 0]};
    setPick("");
  });
  const setField = (name: string, field: string, raw: string) => {
    try {
      const value = field === "position" ? parsePoint(raw) : field === "facing" ? (raw === "" ? "camera" : Number(raw)) : raw;
      ep.update(() => { const e = ep.castEntry(name); if (raw === "" && field !== "facing") delete e[field]; else e[field] = value; });
    } catch (e) { toast((e as Error).message, "err"); }
  };
  const names = Object.keys(cast);
  return (
    <Card title="Cast and placement" text="Who is in this scene, where they start, and how they look and sound."
          actions={<div className="row nowrap">
            <Select className="sm" value={pick} onChange={setPick} options={available} placeholder="Choose a character" />
            <Button size="sm" icon={<UserPlus size={14} />} disabled={!pick} onClick={add}>Add</Button>
          </div>}>
      <div className="item-list">
        {names.length === 0 && <p className="muted" style={{margin: 0}}>Add a character to stage the scene.</p>}
        {names.map((name, i) => {
          const e = isObj(cast[name]) ? cast[name] : {};
          const editable = Object.prototype.hasOwnProperty.call(local, name);
          const position = Array.isArray(e.position) ? e.position.join(", ") : "";
          return (
            <div key={name} className="item">
              <div className="item-head">
                <span className="avatar" style={{background: COLORS[i % COLORS.length]}}>{name.slice(0, 2)}</span>
                <b>{name}</b>
                <Badge>{editable ? "In this scene" : "Episode cast"}</Badge>
                <div className="spacer" />
                {editable && <Button size="sm" variant="ghost" square icon={<Trash2 size={14} />} aria-label={`Remove ${name}`}
                                     onClick={() => ep.update(m => { if (multi) delete ep.scene().cast[name]; else delete m.cast[name]; })} />}
              </div>
              <div className="item-body form-grid" style={{gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))"}}>
                <Field label="Position x, y"><input className="input" defaultValue={position} key={position} onBlur={ev => ev.target.value !== position && setField(name, "position", ev.target.value)} /></Field>
                <Field label="Facing (°)"><input className="input" type="number" placeholder="camera" key={String(e.facing)}
                  defaultValue={e.facing === "camera" || e.facing == null ? "" : e.facing} onBlur={ev => setField(name, "facing", ev.target.value)} /></Field>
                <Field label="Expression"><Select value={e.expression || ""} onChange={v => setField(name, "expression", v)} options={schema!.expressions} placeholder="Default" /></Field>
                <Field label="Posture"><Select value={e.posture || ""} onChange={v => setField(name, "posture", v)} options={schema!.postures} placeholder="Default" /></Field>
                <Field label="Voice"><Select value={e.voice || ""} onChange={v => setField(name, "voice", v)} options={Object.keys(schema!.voices)} placeholder="No voice" /></Field>
                <Field label="Voice effect"><Select value={e.voice_fx || ""} onChange={v => setField(name, "voice_fx", v)} options={schema!.voice_fx} placeholder="Default" /></Field>
                <Field label="Starts"><Select value={e.sit || ""} onChange={v => setField(name, "sit", v)} options={seats.map((s: string) => [s, `seated on ${s}`] as [string, string])} placeholder="Standing" /></Field>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function PropsEditor() {
  const {schema, toast} = useStore();
  const ep = useEpisode();
  const kinds = Object.keys(schema!.props).filter(k => schema!.props[k].size);
  const [make, setMake] = useState(kinds.includes("chair") ? "chair" : kinds[0]);
  const [id, setId] = useState("");
  const scene = ep.scene() || ep.model;
  const props: Json[] = Array.isArray(scene.props) ? scene.props : [];
  const add = () => {
    const pid = id.trim().toLowerCase().replace(/[ -]+/g, "_") || `${make}_${props.length + 1}`;
    if (!/^[a-z0-9_]+$/.test(pid)) return toast("Prop names can use lowercase letters, numbers and underscores.", "err");
    if (props.some(p => p?.id === pid)) return toast(`A prop named "${pid}" already exists in this scene.`, "err");
    const def = schema!.props[make];
    ep.update(() => {
      const s = ep.scene() || ep.model;
      if (!Array.isArray(s.props)) s.props = [];
      s.props.push({id: pid, make, position: [0, 0], ...(def.size ? {size: [...def.size]} : {}), material: def.material});
    });
    setId("");
  };
  const edit = (i: number, fn: (p: Json) => void) => ep.update(() => fn((ep.scene() || ep.model).props[i]));
  return (
    <Card title="Set props" text="Furniture, doors and objects the characters use. Drag them later in the 3D editor."
          actions={<div className="row nowrap">
            <Select className="sm" value={make} onChange={setMake} options={kinds} />
            <input className="input sm" style={{width: 120}} value={id} onChange={e => setId(e.target.value)} placeholder="name (optional)" />
            <Button size="sm" icon={<Plus size={14} />} onClick={add}>Add</Button>
          </div>}>
      <div className="item-list">
        {!Array.isArray(scene.props) && scene.props != null && <p className="muted">Props must be a list: repair it in the JSON tab.</p>}
        {props.length === 0 && <p className="muted" style={{margin: 0}}>No props in this scene yet.</p>}
        {props.map((p, i) => {
          if (!isObj(p)) return <div key={i} className="item item-body">Invalid prop at position {i + 1}; repair it in the JSON tab.</div>;
          const size = Array.isArray(p.size) ? p.size : schema!.props[p.make]?.size;
          const pos = Array.isArray(p.position) ? p.position.join(", ") : "0, 0";
          return (
            <div key={i} className="item">
              <div className="item-head">
                <Armchair size={15} className="muted" />
                <b>{p.id || `Prop ${i + 1}`}</b><Badge>{p.file ? "Blender model" : (p.make || "box").replace(/_/g, " ")}</Badge>
                <div className="spacer" />
                <Button size="sm" variant="ghost" square icon={<Trash2 size={14} />} aria-label="Remove prop"
                        onClick={() => ep.update(() => (ep.scene() || ep.model).props.splice(i, 1))} />
              </div>
              <div className="item-body form-grid" style={{gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))"}}>
                <Field label="Position x, y"><input className="input" key={pos} defaultValue={pos} onBlur={e => {
                  if (e.target.value === pos) return;
                  try { const v = parsePoint(e.target.value); edit(i, x => { x.position = v; }); } catch (err) { toast((err as Error).message, "err"); }
                }} /></Field>
                <Field label="Rotation °"><input className="input" type="number" value={p.rotation ?? 0} onChange={e => edit(i, x => { x.rotation = Number(e.target.value); })} /></Field>
                {p.file && <Field label="Scale"><input className="input" type="number" step={0.05} value={p.scale ?? 1} onChange={e => edit(i, x => { x.scale = Number(e.target.value); })} /></Field>}
                {size && ["Width", "Depth", "Height"].map((d, k) => (
                  <Field key={d} label={`${d} m`}><input className="input" type="number" step={0.05} min={0.01} value={size[k]} onChange={e => {
                    const v = Number(e.target.value);
                    if (v > 0) edit(i, x => { x.size = [...size]; x.size[k] = v; });
                  }} /></Field>
                ))}
                <Field label="Material"><Select value={p.material || ""} onChange={v => edit(i, x => { if (v) x.material = v; else delete x.material; })} options={schema!.materials} placeholder="Default" /></Field>
                <Field label="Colour"><ColorField value={p.color || ""} allowEmpty onChange={v => edit(i, x => { if (v) x.color = v; else delete x.color; })} /></Field>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
