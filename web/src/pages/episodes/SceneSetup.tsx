// The stage: one floor seen from above with everybody standing on it, and the controls for whoever is
// selected. Choosing a character is choosing a face; placing them is dragging them; which way they face is
// a dial; their voice is something you listen to first. Nothing here is typed except a prop's name.
import {ReactNode, useEffect, useMemo, useState} from "react";
import {Armchair, Plus, Trash2, UserPlus} from "lucide-react";
import {Json, label} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Badge, Button, Card, ColorField, Field, Select} from "../../components/ui";
import {ParamInput} from "../../components/ParamInput";
import {CastThumbs, ChipPick, Dial, Person, Regulator, StagePad, STAGE_COLORS, Thing, stageColor, VoicePicker} from "../../components/controls";
import {initials} from "../../components/glyphs";

export const COLORS = STAGE_COLORS;
const isObj = (v: Json) => v && typeof v === "object" && !Array.isArray(v);

// Scene settings read as two decisions - how it looks and how it sounds - instead of one long column.
const LOOK = ["background", "set_folder", "set", "lighting", "look", "weather", "aspect", "shots", "quality"];
const SOUND = ["floor", "ambience", "ambience_volume", "ambience_width", "ambience_duck_db",
               "music", "music_duck_db", "duck"];

type Sel = {kind: "who" | "prop"; id: string} | null;

export function SceneSetup() {
  const {schema} = useStore();
  const ep = useEpisode();
  const [sel, setSel] = useState<Sel>(null);
  const cast = ep.model ? ep.cast() : {};
  const names = Object.keys(cast);
  const scene = ep.scene() || ep.model;
  const props: Json[] = Array.isArray(scene?.props) ? scene.props : [];

  // Something is always selected, so the floor always has a subject to move.
  useEffect(() => {
    const alive = sel && (sel.kind === "who" ? names.includes(sel.id) : props.some(p => p?.id === sel.id));
    if (!alive) setSel(names.length ? {kind: "who", id: names[0]} : props[0]?.id ? {kind: "prop", id: props[0].id} : null);
  }, [ep.rev, ep.part, names.join("|"), props.map(p => p?.id).join("|")]);

  if (!schema || !ep.model) return null;
  return (
    <div className="stack lg">
      <Stage sel={sel} setSel={setSel} />
      <div className="grid-2" style={{alignItems: "start"}}>
        <Settings title="How it looks" text="The picture, the light and the weather." keys={LOOK} />
        <Settings title="How it sounds" text="Footsteps, room tone and music, and how far they dip under dialogue." keys={SOUND} />
      </div>
      <Settings title="Everything else" text="Settings with no better home." keys={null} />
    </div>
  );
}

// --- the floor and whoever is on it -----------------------------------------------------------------------
function Stage({sel, setSel}: {sel: Sel; setSel: (s: Sel) => void}) {
  const {current} = useStore();
  const ep = useEpisode();
  const cast = ep.cast();
  const names = Object.keys(cast);
  const multi = Array.isArray(ep.model.scenes);
  const scene = ep.scene() || ep.model;
  const props: Json[] = Array.isArray(scene.props) ? scene.props : [];
  const spare = (current?.characters || []).filter(c => !cast[c.name]).map(c => c.name);

  const people: Person[] = names.map((n, i) => {
    const e = isObj(cast[n]) ? cast[n] : {};
    return {name: n, at: Array.isArray(e.position) ? e.position : [0, 0], color: stageColor(i),
            self: sel?.kind === "who" && sel.id === n};
  });
  const things: Thing[] = props.filter(p => isObj(p)).map((p, i) => ({
    id: p.id || `prop ${i + 1}`,
    at: Array.isArray(p.position) ? p.position : [0, 0],
    size: Array.isArray(p.size) ? [p.size[0], p.size[1]] : undefined,
  }));
  const where = (): [number, number] | null => {
    if (!sel) return null;
    if (sel.kind === "who") {
      const e = isObj(cast[sel.id]) ? cast[sel.id] : {};
      return Array.isArray(e.position) ? e.position : [0, 0];
    }
    const p = props.find(x => x?.id === sel.id);
    return Array.isArray(p?.position) ? p.position : [0, 0];
  };
  const move = (spot: [number, number]) => {
    if (!sel) return;
    ep.update(() => {
      if (sel.kind === "who") { ep.castEntry(sel.id).position = spot; return; }
      const p = (ep.scene() || ep.model).props.find((x: Json) => x?.id === sel.id);
      if (p) p.position = spot;
    });
  };
  const add = (name: string) => {
    if (!name) return;
    ep.update(m => {
      const path = ep.characterPath(name);
      m.cast = isObj(m.cast) ? m.cast : {};
      if (multi) {
        m.cast[name] = m.cast[name] || {character: path};
        const s = ep.scene();
        s.cast = isObj(s.cast) ? s.cast : {};
        s.cast[name] = {...(s.cast[name] || {}), position: [0, 0]};
      } else m.cast[name] = {character: path, position: [0, 0]};
    });
    setSel({kind: "who", id: name});
  };

  return (
    <Card title="The stage" bodyClass="tight"
          text="Click a face to put them in the scene, then drag them where they start. The camera is at the bottom of the floor, looking up the page."
          actions={<Badge>{names.length} in the scene &middot; {props.length} props</Badge>}>
      <div className="stage-shelf">
        <div className="shelf-side">
          <h4 className="section-title"><UserPlus size={13} /> Put someone in</h4>
          <CastThumbs names={spare} value={null} size={46} onChange={v => add(String(v || ""))} />
          {!spare.length && !!names.length && <p className="hint">Everyone this film has is already in the scene.</p>}
          {!spare.length && !names.length && <p className="hint">Build a character first (Characters), then it appears here as a face.</p>}
        </div>
        <div className="shelf-pad">
          <StagePad value={where()} onChange={move} people={people} things={things} height={300}
                    onPick={n => setSel({kind: "who", id: n})} onPickThing={id => setSel({kind: "prop", id})} />
          <div className="row nowrap wrap" style={{marginTop: 8, gap: 6}}>
            {names.map((n, i) => (
              <button key={n} type="button" className={`tag ${sel?.kind === "who" && sel.id === n ? "on" : ""}`}
                      style={{borderColor: stageColor(i)}} onClick={() => setSel({kind: "who", id: n})}>
                <span className="dot" style={{background: stageColor(i)}} />{n}
              </button>
            ))}
            {things.map(t => (
              <button key={t.id} type="button" className={`tag ${sel?.kind === "prop" && sel.id === t.id ? "on" : ""}`}
                      onClick={() => setSel({kind: "prop", id: t.id})}>
                <Armchair size={11} />{t.id}
              </button>
            ))}
          </div>
        </div>
        <div className="shelf-panel">
          {sel?.kind === "who" && <Actor name={sel.id} />}
          {sel?.kind === "prop" && <PropPanel id={sel.id} />}
          {!sel && <p className="hint">Nobody is in this scene yet. Click a face on the left to put someone in.</p>}
        </div>
      </div>
      <NewProp onMade={id => setSel({kind: "prop", id})} />
    </Card>
  );
}

// --- one person's performance ------------------------------------------------------------------------------
function Actor({name}: {name: string}) {
  const {schema, current} = useStore();
  const ep = useEpisode();
  const cast = ep.cast();
  const multi = Array.isArray(ep.model.scenes);
  const local = multi ? (isObj(ep.scene()?.cast) ? ep.scene().cast : {}) : cast;
  const e = isObj(cast[name]) ? cast[name] : {};
  const mine = Object.prototype.hasOwnProperty.call(local, name);
  const seats = (Array.isArray(ep.scene()?.props) ? ep.scene().props : [])
    .filter((p: Json) => schema!.seats.includes(p?.make)).map((p: Json) => p.id);
  const picture = current?.characters?.find(c => c.name === name)?.preview || null;
  const at = Object.keys(cast).indexOf(name);
  const set = (field: string, v: Json) => ep.update(() => {
    const entry = ep.castEntry(name);
    if (v === null || v === "") delete entry[field]; else entry[field] = v;
  });
  return (
    <div className="actor">
      <div className="actor-head">
        {picture ? <img src={picture} alt="" />
                 : <span className="face-ini" style={{width: 40, height: 40, background: stageColor(at)}}>{initials(name)}</span>}
        <div className="grow">
          <b>{name}</b>
          <div className="muted small">{mine ? "placed in this scene" : "from the episode cast"}</div>
        </div>
        {mine && (
          <Button size="sm" variant="ghost" square icon={<Trash2 size={14} />} aria-label={`Take ${name} out`}
                  onClick={() => ep.update(m => { if (multi) delete ep.scene().cast[name]; else delete m.cast[name]; })} />
        )}
      </div>
      <div className="actor-rows">
        <Row label="Facing">
          <Dial value={e.facing ?? null} onChange={v => set("facing", v)} />
        </Row>
        <Row label="Voice">
          <VoicePicker value={e.voice || null} onChange={v => set("voice", v)} />
          <ChipPick value={e.voice_fx || null} onChange={v => set("voice_fx", v)} options={schema!.voice_fx} placeholder="default" placeholderHint="the voice as it comes" />
        </Row>
        <Row label="Face">
          <ChipPick value={e.expression || null} onChange={v => set("expression", v)} options={schema!.expressions} placeholder="default" placeholderHint="the face the character was built with" />
        </Row>
        <Row label="Stance">
          <ChipPick value={e.posture || null} onChange={v => set("posture", v)} options={schema!.postures} placeholder="default" placeholderHint="however they normally stand" />
        </Row>
        {!!seats.length && (
          <Row label="Starts">
            <ChipPick value={e.sit || null} onChange={v => set("sit", v)} options={seats} placeholder="standing" />
          </Row>
        )}
      </div>
    </div>
  );
}

function Row({label: text, children}: {label: string; children: ReactNode}) {
  return (
    <div className="actor-row">
      <span className="actor-label">{text}</span>
      <div className="actor-control">{children}</div>
    </div>
  );
}

// --- one prop ---------------------------------------------------------------------------------------------
const DIMS: [string, string][] = [["0", "width"], ["1", "depth"], ["2", "height"]];

function PropPanel({id}: {id: string}) {
  const {schema} = useStore();
  const ep = useEpisode();
  const scene = ep.scene() || ep.model;
  const props: Json[] = Array.isArray(scene.props) ? scene.props : [];
  const i = props.findIndex(p => p?.id === id);
  if (i < 0) return null;
  const p = props[i];
  const size = Array.isArray(p.size) ? p.size : schema!.props[p.make]?.size;
  const edit = (fn: (x: Json) => void) => ep.update(() => fn((ep.scene() || ep.model).props[i]));
  const metre = (help: string, lo: number, hi: number) =>
    ({type: "number", help, required: false, lo, hi, step: 0.05, unit: "m"} as const);
  return (
    <div className="actor">
      <div className="actor-head">
        <span className="face-ini" style={{width: 40, height: 40, background: "var(--line-2)"}}><Armchair size={18} /></span>
        <div className="grow">
          <b>{id}</b>
          <div className="muted small">{p.file ? "Blender model" : (p.make || "box").replace(/_/g, " ")}</div>
        </div>
        <Button size="sm" variant="ghost" square icon={<Trash2 size={14} />} aria-label="Remove prop"
                onClick={() => ep.update(() => (ep.scene() || ep.model).props.splice(i, 1))} />
      </div>
      <div className="actor-rows">
        <Row label="Turned">
          <Dial value={p.rotation ?? 0} presets={false} size={64} onChange={v => edit(x => { x.rotation = v ?? 0; })} />
        </Row>
        {size && DIMS.map(([k, what]) => (
          <Row key={k} label={what}>
            <Regulator def={metre(what, 0.05, what === "height" ? 3.5 : 3)} value={size[Number(k)]}
                       onChange={v => { if (typeof v === "number" && v > 0) edit(x => { x.size = [...size]; x.size[Number(k)] = v; }); }} />
          </Row>
        ))}
        {p.file && (
          <Row label="Scale">
            <Regulator def={{type: "number", help: "scale", required: false, lo: 0.2, hi: 3, step: 0.05, unit: "×", default: 1}}
                       value={p.scale ?? 1} onChange={v => edit(x => { x.scale = v ?? 1; })} />
          </Row>
        )}
        <Row label="Made of">
          <ChipPick value={p.material || null} onChange={v => edit(x => { if (v) x.material = v; else delete x.material; })}
                    options={schema!.materials} placeholder="default" />
        </Row>
        <Row label="Colour">
          <ColorField value={p.color || ""} allowEmpty onChange={v => edit(x => { if (v) x.color = v; else delete x.color; })} />
        </Row>
      </div>
    </div>
  );
}

function NewProp({onMade}: {onMade: (id: string) => void}) {
  const {schema, toast} = useStore();
  const ep = useEpisode();
  const kinds = Object.keys(schema!.props).filter(k => schema!.props[k].size);
  const [make, setMake] = useState(kinds.includes("chair") ? "chair" : kinds[0]);
  const [id, setId] = useState("");
  const add = () => {
    const scene = ep.scene() || ep.model;
    const props: Json[] = Array.isArray(scene.props) ? scene.props : [];
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
    onMade(pid);
  };
  return (
    <div className="new-prop">
      <span className="muted small">Put a prop on the floor</span>
      <Select className="sm" value={make} onChange={setMake} options={kinds} aria-label="What kind of prop" />
      <input className="input sm" style={{width: 130}} value={id} onChange={e => setId(e.target.value)} placeholder="name (optional)" />
      <Button size="sm" icon={<Plus size={14} />} onClick={add}>Add</Button>
    </div>
  );
}

// --- scene settings, straight from the schema -------------------------------------------------------------
function Settings({title, text, keys}: {title: string; text: string; keys: string[] | null}) {
  const {schema, current, toast} = useStore();
  const ep = useEpisode();
  const taken = useMemo(() => new Set([...LOOK, ...SOUND]), []);
  const entries = Object.entries(schema!.scene).filter(([k]) => (keys ? keys.includes(k) : !taken.has(k)));
  if (!entries.length) return null;
  const order = keys ? (a: string) => keys.indexOf(a) : () => 0;
  entries.sort(([a], [b]) => order(a) - order(b));
  const target = () => ep.scene() || ep.model;
  const value = (key: string) => ep.scene()?.[key] ?? ep.model[key];
  const onSet = typeof value("set_folder") === "string" ? String(value("set_folder")) : null;
  const named = (current?.sets || []).find(x => onSet?.endsWith(`/${x.name}`) || onSet === x.name);

  // Picking a built set and picking a background picture are two ways to say the same thing, and the
  // app used to let them disagree: choose the set, and `background` quietly went on pointing at the
  // old picture. The render replaces it anyway, but the check refused to start and the file looked
  // wrong. So choosing a set now sets the picture with it, and choosing a picture drops the set.
  const change = (key: string, v: Json) => ep.update(() => {
    const t = target();
    if (v === null || v === "") delete t[key]; else t[key] = v;
    if (key === "set_folder") {
      const picked = (current?.sets || []).find(x => typeof v === "string" && v.endsWith(`/${x.name}`));
      if (picked) {
        t.background = `${"../".repeat(ep.depth())}${picked.path.replace(/^\.\.\/sets\//, "sets/")}`;
        toast(`This scene is on the set ${picked.name}; its picture comes with it.`);
      } else if (v === null) {
        toast("Back to this scene's own picture. Choose one under Background.");
      }
    }
    if (key === "background" && v && t.set_folder) {
      delete t.set_folder;
      toast("Using that picture instead of the built set.");
    }
  });

  return (
    <Card title={title} text={text}>
      {named && keys?.includes("background") && (
        <p className="hint" style={{marginTop: 0}}>
          This scene is on the built set <b>{named.name}</b>: its picture, its depth and everything
          standing in it come with it. The background below is that set&rsquo;s own picture.
        </p>
      )}
      <div className="set-grid">
        {entries.map(([key, def]) => (
          <Field key={key} wide={def.type === "image" || def.type === "set"}
                 label={<span style={{textTransform: "capitalize"}}>{label(key)}</span>}
                 hint={def.help} required={def.required && !(key === "background" && !!onSet)}>
            <ParamInput name={key} def={def} value={value(key)} onChange={v => change(key, v)} />
          </Field>
        ))}
      </div>
    </Card>
  );
}
