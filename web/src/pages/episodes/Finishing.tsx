import {useEffect, useState} from "react";
import {label} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Card, Field} from "../../components/ui";
import {ParamInput} from "../../components/ParamInput";
import {Cut} from "./Cut";

export function Finishing() {
  const {schema} = useStore();
  const ep = useEpisode();
  const m = ep.model;
  const title = typeof m?.title === "string" ? {text: m.title, subtitle: ""} : {text: m?.title?.text || "", subtitle: m?.title?.subtitle || ""};
  const credits = Array.isArray(m?.credits?.lines) ? m.credits.lines.join("\n") : "";
  const [t, setT] = useState(title);
  const [c, setC] = useState<string>(credits);
  useEffect(() => { setT(title); setC(credits); }, [ep.rev]);   // the model changed elsewhere (JSON tab, undo)
  if (!schema || !m) return null;
  const target = () => ep.scene() || m;
  return (
    <div className="stack lg">
      <Cut />
      <Card title="Finishing" text="Applied after rendering: changing these never re-renders (use Finish only).">
        <div className="set-grid">
          {Object.entries(schema.finish).map(([key, def]) => (
            <Field key={key} label={<span style={{textTransform: "capitalize"}}>{label(key)}</span>} hint={def.help}>
              <ParamInput name={key} def={def} value={ep.scene()?.[key] ?? m[key]} onChange={v => ep.update(() => {
                const s = target();
                if (v === null || v === "") delete s[key]; else s[key] = v;
              })} />
            </Field>
          ))}
        </div>
      </Card>
      <Card title="Title and credits" text="A title card at the start and credits at the end of the episode.">
        <div className="form-grid">
          <Field label="Title"><input className="input" value={t.text} placeholder="Optional title card" onChange={e => setT({...t, text: e.target.value})}
            onBlur={() => ep.update(x => { if (!t.text.trim() && !t.subtitle.trim()) delete x.title; else x.title = {text: t.text.trim(), subtitle: t.subtitle.trim()}; })} /></Field>
          <Field label="Subtitle"><input className="input" value={t.subtitle} placeholder="Optional subtitle" onChange={e => setT({...t, subtitle: e.target.value})}
            onBlur={() => ep.update(x => { if (!t.text.trim() && !t.subtitle.trim()) delete x.title; else x.title = {text: t.text.trim(), subtitle: t.subtitle.trim()}; })} /></Field>
          <Field label="Credits" hint="One line per entry" wide><textarea className="textarea" rows={4} value={c} onChange={e => setC(e.target.value)}
            onBlur={() => ep.update(x => {
              const lines = c.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
              if (!lines.length) delete x.credits; else x.credits = {...(x.credits || {}), lines};
            })} /></Field>
        </div>
      </Card>
    </div>
  );
}
