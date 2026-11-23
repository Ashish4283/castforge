// The character designer: every design key (core/schema.py CHARACTER) as a control, ready-made looks, the
// front/side/back previews, and Rebuild. Photo characters keep their face and body from the photo.
import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {ChevronRight, Dumbbell, Hammer, RotateCcw, Shirt, Sparkles, UserRound, Wand2} from "lucide-react";
import {api, CharacterDetail, Json, label, ParamDef, post, q} from "../api";
import {useStore} from "../app/store";
import {Badge, Button, ColorField, Field, Notice, PageHead, Segmented, Select, Switch} from "../components/ui";

const SECTIONS: {title: string; text: string; keys: string[]}[] = [
  {title: "Body", text: "Who they are. Age and build shape the whole body.", keys: ["gender", "age", "height_cm", "build"]},
  {title: "Face and hair", text: "A hat hides the hair; a beard takes the hair colour. A hair style overrides the length.",
   keys: ["skin", "eyes", "hair.length", "hair.style", "hair.color", "eyebrows", "beard", "hat"]},
  {title: "Outfit", text: "The base clothes, coloured to your choice. A style other than casual is one whole-body outfit.",
   keys: ["outfit.style", "outfit.garment", "outfit.sleeves", "outfit.top", "outfit.bottom", "outfit.shoes"]},
  {title: "Costume", text: "Pieces over the outfit: a long coat, fur trim, a belt, gloves and boots. Leave a colour empty to leave the piece out.",
   keys: ["costume.coat", "costume.fabric", "costume.trim", "costume.belt", "costume.buckle", "costume.gloves",
          "costume.boots", "costume.cape", "costume.cape_length", "costume.armour"]},
];
const BLANK: Json = {gender: "female", age: 30, height_cm: 168, build: "average", skin: "#e0b89a", eyes: "brown",
  hair: {length: "medium", color: "#3b2a20"}, beard: "none", hat: "none",
  outfit: {garment: "trousers", sleeves: "long", top: "#40506a", bottom: "#2c2f36", shoes: "#2a2420"}};

const get = (d: Json, key: string) => key.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), d);
function set(d: Json, key: string, value: Json) {
  const parts = key.split("."), last = parts.pop()!;
  let o = d;
  for (const p of parts) o = o[p] = o[p] && typeof o[p] === "object" ? o[p] : {};
  if (value === "" || value == null) delete o[last]; else o[last] = value;
}

export function CharacterDesigner({name}: {name: string}) {
  const {movie, schema, jobs, toast, go, reload} = useStore();
  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [design, setDesign] = useState<Json>(null);
  const [saved, setSaved] = useState("");
  const [view, setView] = useState<"front" | "side" | "back">("front");
  const [usePhoto, setUsePhoto] = useState(true);
  const [busy, setBusy] = useState(false);
  const wasBuilding = useRef(false);

  const load = useCallback(async () => {
    try {
      const d = await api<CharacterDetail>(`/api/character?${q({movie, name})}`);
      setDetail(d);
      setIsNew(false);
      const start = Object.keys(d.design).length ? d.design : structuredClone(BLANK);
      setUsePhoto(start.use_photo ?? (!!d.photo && !start.costume));     // as it was last built
      setDesign(structuredClone(start));
      setSaved(JSON.stringify(start));
    } catch {
      setDetail({name, design: {}, photo: null, face: null, previews: {}, log: []});
      setIsNew(true);
      setDesign(structuredClone(BLANK));
      setSaved("");
    }
  }, [movie, name]);
  useEffect(() => { load(); }, [load]);

  const job = jobs.find(j => j.movie === movie && j.name === name && j.state === "building");
  useEffect(() => {          // a build of this character finished: show the new previews
    if (wasBuilding.current && !job) { load(); reload(); }
    wasBuilding.current = !!job;
  }, [job, load, reload]);

  const dirty = design && JSON.stringify(design) !== saved;
  // put a whole group of sliders back to the middle: the quickest way out of a face gone wrong
  const resetGroup = (part: string, keys: string[]) =>
    setDesign((d: Json) => { const n = structuredClone(d); for (const k of keys) set(n, `${part}.${k}`, null); return n; });
  const groupTouched = (part: string, keys: string[]) => keys.some(k => Number(get(design, `${part}.${k}`) || 0) !== 0);
  const change = (key: string, value: Json) => setDesign((d: Json) => { const n = structuredClone(d); set(n, key, value); return n; });
  const applyLook = (look: Record<string, string>) => {
    setDesign((d: Json) => { const n = structuredClone(d); for (const [k, v] of Object.entries(look)) set(n, k, v); return n; });
    toast("Look applied: check the colours, then Rebuild.", "info");
  };
  const problems = useMemo(() => {
    if (!schema || !design) return [];
    return Object.entries(schema.character).filter(([k, d]) => d.required && (get(design, k) == null || get(design, k) === "")).map(([k]) => label(k));
  }, [schema, design]);

  const rebuild = async () => {
    setBusy(true);
    try {
      await post("/api/character/rebuild", {movie, name, design, use_photo: !!detail?.photo && usePhoto});
      setSaved(JSON.stringify(design));
      toast(`Rebuilding ${name}: about 4 minutes. The previews update when it is done.`, "info");
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  };

  if (!schema || !design || !detail) return <div className="page"><PageHead title={name} eyebrow="Characters" /></div>;
  const img = detail.previews[view] || detail.previews.front;
  return (
    <div className="page">
      <PageHead
        eyebrow={<><a href="#/characters">Characters</a><ChevronRight size={12} />{isNew ? "New" : "Design"}</>}
        title={<span className="row" style={{gap: 12}}>{name}{job && <Badge kind="warn"><span className="spinner" style={{width: 9, height: 9}} />Building</Badge>}
          {isNew && <Badge kind="accent">Not built yet</Badge>}{dirty && !job && <Badge>Unsaved changes</Badge>}</span>}
        text="Change anything, then Rebuild: the character is made again with the same rig, so every scene that uses it picks up the new look."
        actions={<>
          <Button variant="ghost" icon={<RotateCcw size={15} />} disabled={!dirty} onClick={() => setDesign(JSON.parse(saved || JSON.stringify(BLANK)))}>Discard</Button>
          <Button variant="primary" icon={<Hammer size={15} />} busy={busy} disabled={!!job || problems.length > 0} onClick={rebuild}>{isNew ? "Build character" : "Rebuild"}</Button>
        </>} />
      <div className="designer">
        <div className="viewer card">
          <div className="stage">
            {img ? <img src={img} alt={`${name} ${view}`} /> : <UserRound size={64} className="muted" />}
            {job && <div className="building"><div className="stack" style={{justifyItems: "center"}}><span className="spinner" style={{width: 26, height: 26, borderWidth: 3}} /><b>Building…</b><span className="muted small">{job.last || "starting"}</span></div></div>}
          </div>
          <div className="views"><Segmented value={view} onChange={setView} options={[["front", "Front"], ["side", "Side"], ["back", "Back"]]} /></div>
          {detail.log.length > 0 && (
            <details style={{borderTop: "1px solid var(--line)", padding: "12px 16px"}}>
              <summary className="muted small" style={{cursor: "pointer"}}>Last build log</summary>
              <pre className="log" style={{marginTop: 10}}>{detail.log.join("\n")}</pre>
            </details>
          )}
        </div>
        <div className="card">
          <div className="design-section">
            <h3><Sparkles size={15} color="var(--accent-2)" />Ready-made looks</h3>
            <p>One click sets the costume pieces and colours; adjust anything afterwards.</p>
            <div className="presets">
              {Object.entries(schema.costumes).map(([id, look]) => (
                <button key={id} className="preset" onClick={() => applyLook(look)}>
                  <Shirt size={16} />
                  <b style={{textTransform: "capitalize"}}>{id.replace(/_/g, " ")}</b>
                  <span className="swatches">{Object.values(look).filter(v => /^#/.test(v)).slice(0, 5).map((c, i) => <i key={i} style={{background: c}} />)}</span>
                </button>
              ))}
            </div>
          </div>
          {detail.photo && (
            <div className="design-section">
              <h3><Wand2 size={15} color="var(--accent-2)" />Photo</h3>
              <div className="row nowrap" style={{alignItems: "flex-start", gap: 16}}>
                <img src={detail.photo} alt="" style={{width: 72, height: 96, objectFit: "cover", borderRadius: 8, border: "1px solid var(--line)"}} />
                <div className="stack" style={{gap: 8}}>
                  <Switch checked={usePhoto} onChange={setUsePhoto}>Use the photo for face and body</Switch>
                  <span className="hint">On: the photo shapes the face and body, the design adds everything else. Off: built from the design only (better for costumes and invented characters).</span>
                </div>
              </div>
            </div>
          )}
          {([["face", "Face shape", schema.face_groups,
              "Every feature from -1 to +1; the middle is an ordinary face. These are in addition to the photo, if there is one."],
             ["body", "Body shape", schema.body_groups,
              "The frame underneath the clothes. Height and build are up at the top; these shape the rest."]] as const).map(
            ([part, heading, groups, text]) => (
            <div key={part} className="design-section">
              <h3>{part === "face" ? <UserRound size={15} color="var(--accent-2)" /> : <Dumbbell size={15} color="var(--accent-2)" />}{heading}</h3>
              <p>{text}</p>
              {Object.entries(groups || {}).map(([group, keys]) => (
                <details key={group} className="slider-group" open={groupTouched(part, keys)}>
                  <summary>
                    <span>{group}</span>
                    {groupTouched(part, keys) && <Badge>changed</Badge>}
                    <span className="spacer" />
                    <button className="btn ghost sm" onClick={e => { e.preventDefault(); resetGroup(part, keys); }}>Reset</button>
                  </summary>
                  <div className="sliders">
                    {keys.filter(k => schema.character[`${part}.${k}`]).map(k => (
                      <SliderField key={k} name={k} def={schema.character[`${part}.${k}`]}
                                   range={schema.slider_range || [-1, 1]}
                                   value={Number(get(design, `${part}.${k}`) || 0)}
                                   onChange={v => change(`${part}.${k}`, v || null)} />
                    ))}
                  </div>
                </details>
              ))}
              {part === "face" && schema.character["face.head_shape"] && (
                <div className="form-grid">
                  <DesignField k="face.head_shape" def={schema.character["face.head_shape"]}
                               value={get(design, "face.head_shape")} onChange={v => change("face.head_shape", v)} />
                </div>
              )}
            </div>
          ))}
          {SECTIONS.map(s => (
            <div key={s.title} className="design-section">
              <h3>{s.title}</h3>
              <p>{s.text}</p>
              <div className="form-grid">
                {s.keys.filter(k => schema.character[k]).map(k => (
                  <DesignField key={k} k={k} def={schema.character[k]} value={get(design, k)} onChange={v => change(k, v)} />
                ))}
              </div>
            </div>
          ))}
          <div className="sticky-bar">
            {problems.length > 0 ? <Notice kind="warn">Fill in: {problems.join(", ")}</Notice>
              : <span className="muted small">{job ? "Building… you can keep editing." : dirty ? "Changes are not built yet." : "Up to date with the last build."} A build takes about 4 minutes on the GPU.</span>}
            <div className="spacer" />
            <Button variant="ghost" onClick={() => go("characters")}>Back</Button>
            <Button variant="primary" icon={<Hammer size={15} />} busy={busy} disabled={!!job || problems.length > 0} onClick={rebuild}>{isNew ? "Build character" : "Rebuild"}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// "hair.color" -> "Hair colour", "height_cm" -> "Height (cm)", "outfit.top" -> "Top"
function title(k: string) {
  const [group, last] = k.includes(".") ? k.split(".") : ["", k];
  const words = (group === "hair" ? `hair ${last}` : last).replace("height_cm", "height (cm)").replace("color", "colour");
  return label(words).replace(/^./, c => c.toUpperCase());
}

// One feature, from one end to the other, with the middle marked. The number says where it is so a look can
// be written down and repeated; double-click the handle (or Reset above) to come back to the middle.
function SliderField({name, def, range, value, onChange}:
                     {name: string; def: ParamDef; range: readonly [number, number] | number[]; value: number; onChange: (v: number) => void}) {
  const [lo, hi] = range as [number, number];
  return (
    <label className={`slider-row ${value ? "set" : ""}`} title={def.help}>
      <span className="slider-name">{title(name)}</span>
      <input type="range" min={lo} max={hi} step={0.05} value={value}
             onChange={e => onChange(Number(e.target.value))} onDoubleClick={() => onChange(0)} />
      <span className="slider-value">{value ? (value > 0 ? "+" : "") + value.toFixed(2) : "0"}</span>
    </label>
  );
}

function DesignField({k, def, value, onChange}: {k: string; def: ParamDef; value: Json; onChange: (v: Json) => void}) {
  const optional = !def.required && def.type === "color";
  return (
    <Field label={title(k)} hint={def.help} required={def.required}>
      {def.type === "enum" ? <Select value={value ?? def.default ?? ""} onChange={v => onChange(v || null)} options={def.values || []} />
        : def.type === "color" ? <ColorField value={value || ""} onChange={onChange} allowEmpty={optional} />
        : <input className="input" type={def.type === "number" ? "number" : "text"} value={value ?? ""}
                 onChange={e => onChange(def.type === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)} />}
    </Field>
  );
}
