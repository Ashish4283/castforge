// The cut: the whole episode as a strip of film you can take hold of.
//
// Every scene is a card showing its own first frame, how long it runs and how much is said in it; between
// two cards sits the transition that joins them, because a transition belongs to a join and not to a
// scene. Drag a card to move it, and the order of `scenes` in scene.json moves with it - that order IS
// the cut, so this edits the film rather than a view of it.
import {useState} from "react";
import {AlertTriangle, Clock, GripVertical, MessageSquareText, Scissors} from "lucide-react";
import {Json} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Badge, Button, Card, Empty, Guide} from "../../components/ui";
import {ChipPick, Regulator, tidy} from "../../components/controls";
import {GLYPHS, GRADE_COLORS, words} from "../../components/glyphs";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export function Cut() {
  const {schema, toast} = useStore();
  const ep = useEpisode();
  const [held, setHeld] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const [joint, setJoint] = useState<number | null>(null);
  if (!schema || !ep.model) return null;
  const scenes: Json[] = Array.isArray(ep.model.scenes) ? ep.model.scenes : [];
  if (!scenes.length)
    return <Card><Empty icon={<Scissors />} title="This episode is a single scene" text="A cut needs more than one scene. Add one in the JSON tab." /></Card>;

  const made = Object.fromEntries((ep.info?.shots || []).map(s => [s.id || s.name, s]));
  const setting = (i: number, key: string) => scenes[i]?.[key] ?? ep.model[key];
  const put = (i: number, key: string, v: Json) => ep.update(m => {
    if (v === null || v === "") delete m.scenes[i][key]; else m.scenes[i][key] = v;
  });
  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= scenes.length) return;
    ep.update(m => { m.scenes.splice(to, 0, m.scenes.splice(from, 1)[0]); });
    ep.setPart(to);
    toast(`Moved to position ${to + 1} in the cut. Save, then Finish only to re-cut the film.`);
  };
  const known = (scenes.map(s => made[s?.id]?.seconds).filter(v => typeof v === "number") as number[]);
  const total = known.reduce((a, b) => a + b, 0);
  const fade = (i: number) => Number(setting(i, "transition_seconds") ?? schema.finish.transition_seconds?.default ?? 0.5);

  return (
    <Card title={<span className="row nowrap" style={{gap: 7}}>The cut <Guide topic="cut" /></span>} bodyClass="tight"
          text="Every scene in the order it plays, with the transition that joins each pair. Drag a scene to move it."
          actions={<Badge>{scenes.length} scenes &middot; {known.length === scenes.length
            ? clock(total) : `${clock(total)} of ${scenes.length - known.length} still to render`}</Badge>}>
      <div className="cut-strip">
        {scenes.map((scene, i) => {
          const id = scene?.id || `scene ${i + 1}`;
          const film = made[scene?.id];
          const grade = String(setting(i, "grade") || "neutral");
          const swatch = GRADE_COLORS[grade];
          const how = String(setting(i, "transition") || schema.finish.transition?.default || "cut");
          return (
            <div key={id + i} className="cut-piece">
              {i > 0 && (
                <div className="cut-joint">
                  <button type="button" className={`joint ${joint === i ? "on" : ""}`}
                          title={`${words(how)}${how === "cut" ? "" : ` over ${tidy(fade(i))}s`} into ${id}`}
                          onClick={() => setJoint(joint === i ? null : i)}>
                    <span>{GLYPHS[how] || "✂️"}</span>
                    <small>{words(how)}</small>
                  </button>
                </div>
              )}
              <div className={`cut-card ${ep.part === i ? "on" : ""} ${over === i ? "over" : ""}`}
                   draggable onDragStart={() => setHeld(i)} onDragEnd={() => { setHeld(null); setOver(null); }}
                   onDragOver={e => { e.preventDefault(); setOver(i); }}
                   onDrop={e => { e.preventDefault(); if (held !== null) move(held, i); setHeld(null); setOver(null); }}
                   onClick={() => ep.setPart(i)}>
                <div className="cut-frame">
                  {film
                    ? <video src={`${film.video}#t=0.4`} preload="metadata" muted playsInline
                             onMouseEnter={e => { (e.target as HTMLVideoElement).play().catch(() => {}); }}
                             onMouseLeave={e => { const v = e.target as HTMLVideoElement; v.pause(); v.currentTime = 0.4; }} />
                    : <div className="cut-none"><AlertTriangle size={15} /><span>not rendered</span></div>}
                  <span className="cut-n">{i + 1}</span>
                  {swatch && grade !== "neutral" &&
                    <span className="cut-grade" title={`${words(grade)} grade`}
                          style={{background: `linear-gradient(135deg, ${swatch[0]}, ${swatch[1]})`}} />}
                </div>
                <div className="cut-what">
                  <b>{id}</b>
                  <span className="muted small">
                    <Clock size={10} /> {film?.seconds ? `${tidy(film.seconds, 0.1)}s` : "—"}
                    {!!film?.lines && <> &middot; <MessageSquareText size={10} /> {film.lines}</>}
                    {!!film?.cuts && <> &middot; {film.cuts} shot{film.cuts > 1 ? "s" : ""}</>}
                  </span>
                </div>
                <GripVertical size={13} className="cut-grip" />
              </div>
            </div>
          );
        })}
      </div>
      {joint !== null && (
        <div className="joint-panel">
          <div className="row nowrap wrap">
            <b>How scene {joint + 1} begins</b>
            <span className="muted small grow">The transition belongs to the scene it opens.</span>
            <Button size="sm" variant="ghost" onClick={() => setJoint(null)}>Done</Button>
          </div>
          <ChipPick value={scenes[joint]?.transition ?? null} options={schema.transitions || []}
                    placeholder="default" placeholderHint={`the episode's own (${schema.finish.transition?.default || "cut"})`}
                    onChange={v => put(joint, "transition", v)} />
          {String(setting(joint, "transition") || "cut") !== "cut" && schema.finish.transition_seconds && (
            <label className="reg-line">
              <span>over</span>
              <Regulator def={schema.finish.transition_seconds} value={scenes[joint]?.transition_seconds ?? null}
                         onChange={v => put(joint, "transition_seconds", v)} />
            </label>
          )}
        </div>
      )}
    </Card>
  );
}
