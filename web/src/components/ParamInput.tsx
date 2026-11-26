// One control for one schema parameter (core/schema.py `p(kind, help, ...)`): scene settings, finishing
// settings and action parameters all come through here.
//
// The parameter's own type decides what you get, so nothing has to be wired up twice: a point becomes a
// floor you drag a marker on, a number becomes a slider over the span the schema allows, an enum becomes
// pictures you click, a voice becomes a gallery you listen to, a set becomes its own photograph. Add an
// action to the schema and it arrives in the app already playable. onChange(null) removes the key.
import {useEffect, useId, useState} from "react";
import {Json, ParamDef} from "../api";
import {useStore} from "../app/store";
import {words} from "./glyphs";
import {useEpisode} from "../app/episode";
import {Switch} from "./ui";
import {
  CastThumbs, ChipPick, ClipPick, MovePad, Person, Regulator, SoundPick, StagePad, TargetPick, Thing,
  stageColor, useClips, VoicePicker,
} from "./controls";

const POINTISH = new Set(["point", "target", "look"]);
const isObj = (v: Json) => v && typeof v === "object" && !Array.isArray(v);
/** Which enums show a swatch or a shape rather than a picture. */
const KIND: Record<string, "grade" | "aspect"> = {grade: "grade", aspect: "aspect"};

/** A clip's own length is the real ceiling for "start at" and "stop at", not the schema's generic 30 s. */
function clipSpan(def: ParamDef, name: string, seconds: number | null): ParamDef {
  if (!seconds || !["from", "to"].includes(name)) return def;
  return {...def, hi: Math.ceil(seconds * 20) / 20};
}

export function ParamInput({name, def, value, onChange, onError, who, clip}: {
  name: string; def: ParamDef; value: Json; onChange: (v: Json) => void; onError?: (msg: string) => void;
  /** the cast member this step belongs to: they are highlighted on the floor */
  who?: string;
  /** the motion clip this step plays: its length bounds the trim sliders */
  clip?: string;
}) {
  const {schema, current} = useStore();
  const ep = useEpisode();
  const clips = useClips();
  const id = useId();
  const shown = value == null ? "" : Array.isArray(value) ? value.join(", ") : String(value);
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);
  if (!schema) return null;
  const scene = ep.scene();

  // Everyone and everything already standing in this scene, so a floor is never an empty grid.
  const stageCast = (): Person[] => {
    const cast = ep.cast();
    return Object.keys(cast).map((n, i) => {
      const e = isObj(cast[n]) ? cast[n] : {};
      return {name: n, at: Array.isArray(e.position) ? e.position : [0, 0], color: stageColor(i), self: n === who};
    });
  };
  const stageThings = (): Thing[] => (Array.isArray(scene?.props) ? scene.props : [])
    .filter((p: Json) => isObj(p) && Array.isArray(p.position))
    .map((p: Json) => ({id: p.id || "prop", at: p.position,
                        size: Array.isArray(p.size) ? [p.size[0], p.size[1]] : undefined}));

  switch (def.type) {
    case "bool":
      return <Switch checked={!!value} onChange={onChange}>{name.replace(/_/g, " ")}</Switch>;
    case "number":
      if (def.lo == null) break;                    // no span in the schema: fall through to the text box
      return <Regulator value={value} onChange={onChange} onError={onError}
                        def={clipSpan(def, name, clip ? clips.find(c => c.name === clip)?.seconds ?? null : null)} />;
    case "enum":
      if (name === "move" && (def.values || []).includes("static"))
        return <MovePad value={value == null ? null : String(value)} onChange={onChange} options={def.values || []} />;
      return <ChipPick value={value == null ? null : String(value)} onChange={onChange} options={def.values || []}
                       kind={KIND[name]} placeholder={def.required ? undefined : "default"}
                       placeholderHint={def.default != null ? `default: ${words(String(def.default))}` : "leave it out"} />;
    case "voice":
      return <VoicePicker value={value == null ? null : String(value)} onChange={onChange} placeholder="No voice" />;
    case "cast_list":
      return <CastThumbs multi size={44} names={Object.keys(ep.cast())}
                         value={Array.isArray(value) ? value : null} onChange={onChange} />;
    case "point":
      return <StagePad value={Array.isArray(value) ? (value as [number, number]) : null} onChange={onChange}
                       people={stageCast()} things={stageThings()} />;
    case "target":
    case "look":
      return <TargetPick value={value} onChange={onChange} cast={Object.keys(ep.cast())}
                         directions={def.type === "look" ? schema.look_directions : undefined}
                         people={stageCast()} things={stageThings()} />;
    case "clip":
      return <ClipPick value={value == null ? null : String(value)} onChange={onChange} />;
    case "bed":
      return <SoundPick kind="beds" names={schema.library.beds || []} onChange={onChange}
                        value={value == null ? null : String(value)} />;
    case "sfx":
      return <SoundPick kind="sfx" names={schema.library.sfx || []} onChange={onChange}
                        value={value == null ? null : String(value)} />;
    case "set": {
      // the built sets of the open film; a set brings its picture, its depth and its objects with it
      const made = (current?.sets || []).filter(s => s.blueprint);
      if (!made.length)
        return <p className="hint">No built sets yet. Open Sets, place what stands in the room, and save it.</p>;
      return <PicturePick value={value == null ? null : String(value)} onChange={onChange} none="This scene's own picture"
                          options={made.map(s => ({value: `../sets/${s.name}`, label: s.name, picture: s.empty || s.picture}))} />;
    }
    case "image": {
      const prefix = "../".repeat(ep.depth());
      return (
        <PicturePick value={value == null ? null : String(value)} onChange={onChange}
                     options={(current?.sets || []).map(s => ({
                       value: `${prefix}${s.path.replace(/^\.\.\/sets\//, "sets/")}`, label: s.name, picture: s.picture,
                     }))}
                     free={{text, setText, hint: "or a picture in this scene's folder",
                            commit: () => { if (text !== shown) onChange(text.trim() || null); }}} />
      );
    }
    case "door":
    case "seat":
    case "prop": {
      const types = def.type === "door" ? ["door"] : def.type === "seat" ? schema.seats : null;
      const ids = (Array.isArray(scene?.props) ? scene.props : [])
        .filter((p: Json) => p?.id && (types === null || types.includes(p?.make))).map((p: Json) => p.id);
      if (!ids.length)
        return <p className="hint">This scene has no {def.type === "prop" ? "props" : def.type + "s"} yet. Add one in the Scene tab.</p>;
      return <ChipPick value={value == null ? null : String(value)} onChange={onChange} options={ids}
                       placeholder={def.required ? undefined : "none"} />;
    }
    case "weather": {
      const w = typeof value === "string" ? {type: value} : value || {};
      const set = (k: string, v: Json) => onChange(k === "type" && !v ? null : {...w, [k]: v});
      const dials: [string, number, number, number][] = [["amount", 0, 1, 0.5], ["wind", -1, 1, 0.2], ["fog", 0, 1, 0]];
      return (
        <div className="stack sm">
          <ChipPick value={w.type || null} onChange={v => set("type", v)} options={schema.weather || []} placeholder="clear" />
          {w.type && dials.map(([k, lo, hi, dflt]) => (
            <label key={k} className="reg-line">
              <span>{k}</span>
              <Regulator def={{type: "number", help: k, required: false, lo, hi, step: 0.05, unit: "", default: dflt}}
                         value={w[k] ?? dflt} onChange={v => set(k, v == null ? dflt : v)} />
            </label>
          ))}
        </div>
      );
    }
  }

  // Anything left is free text: a line of dialogue, a file path, a number with no span of its own.
  const commit = () => {
    if (text === shown) return;
    if (text.trim() === "") return onChange(null);
    if (def.type === "number") {
      const n = Number(text);
      if (!Number.isFinite(n)) { onError?.("Enter a valid number."); setText(shown); return; }
      return onChange(n);
    }
    if (def.type === "point" || (POINTISH.has(def.type) && /^[\d.+-]/.test(text.trim()))) {
      const p = text.split(/[,\s]+/).filter(Boolean).map(Number);
      if (p.length !== 2 || p.some(n => !Number.isFinite(n))) { onError?.("Enter two coordinates, for example -1.2, 0.5."); setText(shown); return; }
      return onChange(p);
    }
    onChange(text);
  };
  return (
    <input className="input" id={id} type={def.type === "number" ? "number" : "text"} step="any" value={text}
           placeholder={def.default != null ? String(def.default) : def.help}
           onChange={e => setText(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === "Enter") commit(); }} />
  );
}

/** Pictures instead of paths: the set photographs of this film, as a grid you point at. */
function PicturePick({value, onChange, options, none, free}: {
  value: string | null; onChange: (v: Json) => void; none?: string;
  options: {value: string; label: string; picture: string | null}[];
  free?: {text: string; setText: (t: string) => void; commit: () => void; hint: string};
}) {
  const known = options.some(o => o.value === value);
  return (
    <div className="stack sm">
      <div className="pic-grid">
        {none && (
          <button type="button" className={`pic ${value ? "" : "on"}`} onClick={() => onChange(null)}>
            <span className="pic-none">&mdash;</span><span className="pic-name">{none}</span>
          </button>
        )}
        {options.map(o => (
          <button key={o.value} type="button" className={`pic ${o.value === value ? "on" : ""}`}
                  onClick={() => onChange(o.value)} title={o.value}>
            {o.picture ? <img src={o.picture} alt="" /> : <span className="pic-none">?</span>}
            <span className="pic-name">{o.label}</span>
          </button>
        ))}
        {!options.length && !none && <span className="muted small">No set pictures in this film yet.</span>}
      </div>
      {free && (
        <div className="row nowrap">
          <span className="muted small">{free.hint}</span>
          <input className="input sm grow" value={free.text} onChange={e => free.setText(e.target.value)}
                 onBlur={free.commit} onKeyDown={e => { if (e.key === "Enter") free.commit(); }}
                 placeholder="background.png" />
        </div>
      )}
      {value && !known && !free && <span className="muted small">Set in the file: {value}</span>}
    </div>
  );
}
