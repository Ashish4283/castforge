// The scene's script in order: spoken lines, thoughts and actions (walks, gestures, camera, sound...).
import {useRef, useState} from "react";
import {ArrowDown, ArrowUp, Copy, MessageCircle, Sliders, Trash2, Upload, Volume2, Zap} from "lucide-react";
import {api, Json, label} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Badge, Button, Card, Empty, Field, Guide, Select} from "../../components/ui";
import {ParamInput} from "../../components/ParamInput";
import {ACTION_GLYPHS, words} from "../../components/glyphs";
import {COLORS} from "./SceneSetup";

const LINE = new Set(["say", "think"]);
const isObj = (v: Json) => v && typeof v === "object" && !Array.isArray(v);

export function Script() {
  const {schema, toast} = useStore();
  const ep = useEpisode();
  if (!schema || !ep.model) return null;
  const scene = ep.scene();
  if (!scene) return <Card><Empty icon={<MessageCircle />} title="This episode has no scenes yet" text="Add a scene in the JSON tab." /></Card>;
  if (scene.script != null && !Array.isArray(scene.script))
    return <Card><Empty icon={<MessageCircle />} title="The script must be a list" text="Repair it in the JSON tab." /></Card>;
  const script: Json[] = scene.script || [];
  const cast = Object.keys(ep.cast());
  const actions = Object.entries(schema.actions).filter(([n]) => !LINE.has(n));
  const edit = (fn: (s: Json[]) => void) => ep.update(() => { const s = ep.scene(); if (!Array.isArray(s.script)) s.script = []; fn(s.script); });
  const add = (what: string) => edit(s => {
    if (LINE.has(what)) return s.push({who: cast[0] || "", do: what, text: ""});
    const def = schema.actions[what], step: Json = {do: what};
    if (def.who) step.who = cast[0] || "";
    for (const [k, p] of Object.entries(def.params)) if ("default" in p) step[k] = p.default;
    s.push(step);
  });
  const palette = (
    <Card title="Add what happens next" bodyClass="tight"
          text="One press puts the step at the end of the scene, ready to adjust.">
      <div className="palette">
        {([["say", "says a line"], ["think", "thinks it"]] as [string, string][]).map(([what, says]) => (
          <button key={what} type="button" className="act big" disabled={!cast.length} onClick={() => add(what)} title={says}>
            <span className="act-glyph">{ACTION_GLYPHS[what]}</span>
            <b>{what === "say" ? "Line" : "Thought"}</b>
            <small>{says}</small>
          </button>
        ))}
        {actions.map(([name, def]) => (
          <button key={name} type="button" className="act" onClick={() => add(name)} title={def.help}
                  disabled={!!def.who && !cast.length}>
            <span className="act-glyph">{ACTION_GLYPHS[name] || "✨"}</span>
            <b>{words(name)}</b>
            <small>{def.help}</small>
          </button>
        ))}
      </div>
      {!cast.length && <p className="hint">Put someone in the scene first (the Stage tab): most of these belong to a person.</p>}
    </Card>
  );
  return (
    <div className="stack">
      {palette}
      <Card bodyClass="tight" title={<span className="row nowrap" style={{gap: 7}}>Script <Guide topic="script" /></span>} text="Everything that happens in this scene, in order. Lines are spoken with the character's voice; actions move people, the camera and the sound."
            actions={<Badge>{script.length} steps</Badge>}>
        <div className="item-list">
          {script.length === 0 && <Empty icon={<MessageCircle />} title="Nothing happens yet" text="Add a line or an action below." />}
          {script.map((step, i) => (
            <Step key={i} i={i} step={step} last={i === script.length - 1} cast={cast} actions={actions.map(([n]) => n)}
                  edit={edit} onError={m => toast(m, "err")} />
          ))}
        </div>
      </Card>
      {script.length > 3 && palette}
    </div>
  );
}

function Step({i, step, last, cast, actions, edit, onError}: {
  i: number; step: Json; last: boolean; cast: string[]; actions: string[];
  edit: (fn: (s: Json[]) => void) => void; onError: (m: string) => void;
}) {
  const {schema, movie, toast} = useStore();
  const ep = useEpisode();
  const file = useRef<HTMLInputElement>(null);
  const [speaking, setSpeaking] = useState(false);
  const [open, setOpen] = useState(false);
  if (!isObj(step)) return <div className="item item-body">Invalid step at position {i + 1}; repair it in the JSON tab.</div>;
  const def = schema!.actions[step.do];
  const line = LINE.has(step.do);
  const set = (k: string, v: Json) => edit(s => { if (v === null || v === "") delete s[i][k]; else s[i][k] = v; });
  const colour = COLORS[Math.max(0, cast.indexOf(step.who)) % COLORS.length];
  const tools = (
    <>
      <div className="spacer" />
      <Button size="sm" variant="ghost" square icon={<ArrowUp size={14} />} disabled={i === 0} aria-label="Move up" onClick={() => edit(s => { [s[i - 1], s[i]] = [s[i], s[i - 1]]; })} />
      <Button size="sm" variant="ghost" square icon={<ArrowDown size={14} />} disabled={last} aria-label="Move down" onClick={() => edit(s => { [s[i + 1], s[i]] = [s[i], s[i + 1]]; })} />
      <Button size="sm" variant="ghost" square icon={<Copy size={14} />} aria-label="Duplicate" onClick={() => edit(s => { s.splice(i + 1, 0, structuredClone(s[i])); })} />
      <Button size="sm" variant="ghost" square icon={<Trash2 size={14} />} aria-label="Remove" onClick={() => edit(s => { s.splice(i, 1); })} />
    </>
  );
  if (!def) return <div className="item"><div className="item-head"><span className="num">{i + 1}</span>Unknown action <b>{String(step.do)}</b>{tools}</div></div>;

  if (line) {
    const hear = async () => {
      setSpeaking(true);
      try {
        const c = ep.cast()[step.who] || {}, voice = c.voice || ep.model.narrator?.voice;
        const r = await fetch("/api/voice/preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text: step.text || "", voice, fx: step.fx})});
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
        await new Audio(URL.createObjectURL(await r.blob())).play();
      } catch (e) { onError((e as Error).message); }
      finally { setSpeaking(false); }
    };
    const upload = async (f: File) => {
      try {
        await ep.save();
        const fd = new FormData();
        fd.append("movie", movie); fd.append("episode", ep.ep!); fd.append("step", String(i)); fd.append("text", step.text || "");
        if (Array.isArray(ep.model.scenes)) fd.append("scene_index", String(ep.part));
        fd.append("file", f);
        const r = await api<{scene: string}>("/api/episode/voice", {method: "POST", body: fd});
        ep.replace(JSON.parse(r.scene), true);
        toast("Voice performance uploaded and linked to this line.");
      } catch (e) { onError((e as Error).message); }
    };
    const params = ["expression", "fx", "speed", "pause"].filter(k => def.params[k]);
    return (
      <div className="item">
        <div className="item-head">
          <span className="num">{i + 1}</span>
          <span className="avatar" style={{background: colour, width: 24, height: 24, fontSize: 10}}>{(step.who || "?").slice(0, 2)}</span>
          <Select className="sm" value={step.who || ""} onChange={v => set("who", v)} options={cast} />
          <Select className="sm" value={step.do} onChange={v => set("do", v)} options={[["say", "speaks"], ["think", "thinks (inner voice)"]]} />
          {step.audio ? <Badge kind="ok">Recorded voice</Badge> : <Badge>Draft voice</Badge>}
          {tools}
        </div>
        <div className="item-body stack" style={{gap: 12}}>
          <textarea className="line-text" rows={2} value={step.text || ""} placeholder="What does the character say?"
                    onChange={e => edit(s => { s[i].text = e.target.value; delete s[i].audio; })} />
          <div className="row nowrap wrap">
            <button type="button" className={`mini ${open ? "on" : ""}`} onClick={() => setOpen(o => !o)}>
              <Sliders size={11} /> performance
            </button>
            {params.filter(k => step[k] != null).map(k => (
              <span key={k} className="tag quiet">{label(k)} {String(step[k])}</span>
            ))}
            {!open && !params.some(k => step[k] != null) && <span className="muted small">said plainly</span>}
          </div>
          {open && (
            <div className="form-grid" style={{gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))"}}>
              {params.map(k => (
                <Field key={k} label={label(k)} hint={def.params[k].help}>
                  <ParamInput name={k} def={def.params[k]} value={step[k]} onChange={v => set(k, v)} onError={onError} who={step.who} />
                </Field>
              ))}
            </div>
          )}
          <div className="row">
            <Button size="sm" icon={<Volume2 size={14} />} busy={speaking} onClick={hear}>Hear it</Button>
            <Button size="sm" icon={<Upload size={14} />} onClick={() => file.current?.click()}>Upload WAV performance</Button>
            <input ref={file} type="file" accept=".wav,audio/wav" hidden onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
            {step.audio?.startsWith("voices/") && (
              <audio controls preload="none" style={{height: 30, flex: 1, minWidth: 200}}
                     src={`/media/${[movie, ep.ep, step.audio].join("/").split("/").map(encodeURIComponent).join("/")}`} />
            )}
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="item">
      <div className="item-head">
        <span className="num">{i + 1}</span>
        <Zap size={14} color="var(--accent-2)" />
        <Select className="sm" value={step.do} options={actions} onChange={v => edit(s => {
          const next: Json = {do: v};
          if (schema!.actions[v].who) next.who = s[i].who || cast[0] || "";
          s[i] = next;
        })} />
        {def.who && <Select className="sm" value={step.who || ""} onChange={v => set("who", v)} options={cast} />}
        <span className="muted small" style={{minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"}}>{def.help}</span>
        {tools}
      </div>
      {Object.keys(def.params).length > 0 && (
        <div className="item-body form-grid" style={{gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))"}}>
          {Object.entries(def.params).map(([k, p]) => (
            <Field key={k} label={label(k)} hint={p.help} required={p.required}
                   wide={["point", "target", "look", "image", "set", "clip", "cast_list"].includes(p.type)}>
              <ParamInput name={k} def={p} value={step[k]} onChange={v => set(k, v)} onError={onError}
                          who={step.who} clip={typeof step.clip === "string" ? step.clip : undefined} />
            </Field>
          ))}
        </div>
      )}
    </div>
  );
}
