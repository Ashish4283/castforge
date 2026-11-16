// One input for one schema parameter (core/schema.py `p(kind, help, ...)`): scene settings, finishing settings
// and action parameters all use it. onChange(null) removes the key from the scene.
import {useEffect, useId, useState} from "react";
import {Json, ParamDef} from "../api";
import {useStore} from "../app/store";
import {useEpisode} from "../app/episode";
import {Select, Switch} from "./ui";

const POINTISH = new Set(["point", "target", "look"]);

export function ParamInput({name, def, value, onChange, onError}: {
  name: string; def: ParamDef; value: Json; onChange: (v: Json) => void; onError?: (msg: string) => void;
}) {
  const {schema, current} = useStore();
  const ep = useEpisode();
  const id = useId();
  const shown = value == null ? "" : Array.isArray(value) ? value.join(", ") : String(value);
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);
  if (!schema) return null;
  const scene = ep.scene();

  switch (def.type) {
    case "bool":
      return <Switch checked={!!value} onChange={onChange}>{name.replace(/_/g, " ")}</Switch>;
    case "enum":
      return <Select value={String(value ?? def.default ?? "")} onChange={v => onChange(v || null)} options={def.values || []} placeholder="Default" />;
    case "voice":
      return <Select value={value || ""} onChange={v => onChange(v || null)} placeholder="Choose voice"
                     options={Object.entries(schema.voices).map(([v, d]) => [v, `${v} · ${d}`] as [string, string])} />;
    case "cast_list":
      return (
        <select className="select" multiple value={Array.isArray(value) ? value : []}
                onChange={e => onChange([...e.target.selectedOptions].map(o => o.value))}>
          {Object.keys(ep.cast()).map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      );
    case "door":
    case "seat":
    case "prop": {
      const types = def.type === "door" ? ["door"] : def.type === "seat" ? schema.seats : null;
      const ids = (Array.isArray(scene?.props) ? scene.props : [])
        .filter((p: Json) => p?.id && (types === null || types.includes(p?.make))).map((p: Json) => p.id);
      return <Select value={value || ""} onChange={v => onChange(v || null)} options={ids} placeholder="Choose prop" />;
    }
    case "weather": {
      const w = typeof value === "string" ? {type: value} : value || {};
      const set = (k: string, v: Json) => onChange(k === "type" && !v ? null : {...w, [k]: v});
      return (
        <div className="stack" style={{gap: 8}}>
          <Select value={w.type || ""} onChange={v => set("type", v)} options={["snow", "rain"]} placeholder="None" />
          {w.type && (
            <div className="row nowrap">
              {(["amount", "wind", "fog"] as const).map(k => (
                <input key={k} className="input sm" type="number" step={0.1} min={k === "wind" ? -1 : 0} max={1} title={k}
                       value={w[k] ?? (k === "amount" ? 0.5 : k === "wind" ? 0.2 : 0)} onChange={e => set(k, Number(e.target.value))} />
              ))}
            </div>
          )}
        </div>
      );
    }
  }

  let list: string[] | null = null;
  if (def.type === "bed" || def.type === "sfx" || def.type === "clip") {
    list = schema.library[({bed: "beds", sfx: "sfx", clip: "clips"} as const)[def.type]] || [];
  } else if (def.type === "image") {
    const prefix = "../".repeat(ep.depth());
    list = (current?.sets || []).map(s => `${prefix}${s.path.replace(/^\.\.\/sets\//, "sets/")}`);
  }
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
    <>
      <input className="input" id={id} type={def.type === "number" ? "number" : "text"} step="any" value={text}
             list={list ? `${id}-list` : undefined} placeholder={def.default != null ? String(def.default) : def.help}
             onChange={e => setText(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === "Enter") commit(); }} />
      {list && <datalist id={`${id}-list`}>{list.map(v => <option key={v} value={v} />)}</datalist>}
    </>
  );
}
