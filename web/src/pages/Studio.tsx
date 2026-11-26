import {useEffect, useState} from "react";
import {ArrowRight, Boxes, Building2, CheckCircle2, Clapperboard, Image, Sparkles, Users} from "lucide-react";
import {api, Progress, q} from "../api";
import {useStore} from "../app/store";
import {useEpisode} from "../app/episode";
import {Badge, Button, Card, Empty, PageHead} from "../components/ui";

const QUICK = [
  {tab: "characters", icon: Users, title: "Character", text: "Design one, or build from a photo"},
  {tab: "sets", icon: Image, title: "Set", text: "A picture, built into a 3D set"},
  {tab: "props", icon: Boxes, title: "Prop", text: "An object from a reference picture"},
  {tab: "library", icon: Building2, title: "City library", text: "Reusable buildings and streets"},
  {tab: "episodes", icon: Clapperboard, title: "Episode", text: "Scenes, dialogue, acting, camera"},
];

export function Studio() {
  const {movie, go, jobs} = useStore();
  const {open} = useEpisode();
  const [p, setP] = useState<Progress | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!movie) return;
    let live = true;
    const load = () => api<Progress>(`/api/movie/progress?${q({movie})}`).then(r => live && setP(r)).catch(e => setErr(e.message));
    load();
    const t = setInterval(load, 8000);
    return () => { live = false; clearInterval(t); };
  }, [movie, jobs.length]);
  const film = (e: Progress["episodes"][string]) =>
    e.broken ? <Badge kind="err" pip>scene.json is broken</Badge> : !e.film ? <Badge>Not made</Badge>
      : e.current ? <Badge kind="ok" pip>Up to date</Badge> : <Badge kind="warn" pip>Changed since render</Badge>;
  const done = p?.steps.filter(s => s.state === "done").length ?? 0;
  return (
    <div className="page">
      <PageHead eyebrow="Overview" title={movie || "CastForge Studio"}
                text="Where this movie stands and what to do next. Every step saves into the movie folder, so you can stop and come back any time."
                actions={p && <Badge kind="accent">{done} of {p.steps.length} steps done</Badge>} />
      {err && !p && <Card><Empty icon={<Sparkles />} title="Could not load this movie" text={err} /></Card>}
      {p && (
        <div className="stack lg">
          <div className="hero">
            <div className="h-icon">{p.next ? <Sparkles size={22} /> : <CheckCircle2 size={22} />}</div>
            <div style={{flex: 1, minWidth: 0}}>
              <div className="muted small">{p.next ? "Next step" : "All steps done"}</div>
              <h2>{p.next ? p.next.title : p.movie}</h2>
              <p>{p.next ? p.next.detail : "Every film is rendered and up to date."}</p>
            </div>
            {p.next && <Button variant="primary" size="lg" onClick={() => go(p.next!.tab)}>Go to {p.next.title} <ArrowRight size={16} /></Button>}
          </div>
          <div className="pipeline">
            {p.steps.map((s, i) => (
              <button key={s.key} className={`pipe ${s.state}`} onClick={() => go(s.tab)}>
                <div className="p-top"><span className="p-num">{s.state === "done" ? "✓" : i + 1}</span><b>{s.title}</b></div>
                <small>{s.detail}</small>
              </button>
            ))}
          </div>
          <div>
            <h3 className="section-title">Create</h3>
            <div className="quick">
              {QUICK.map(x => (
                <button key={x.tab} onClick={() => go(x.tab)}>
                  <span className="q-icon"><x.icon size={18} /></span>
                  <b>{x.title}</b><small>{x.text}</small>
                </button>
              ))}
            </div>
          </div>
          <Card title="Episodes" text="Open one to edit its scenes, preview it in 3D and render it." bodyClass="tight">
            {Object.keys(p.episodes).length ? (
              <table className="table">
                <thead><tr><th>Episode</th><th>Scenes</th><th>Rendered</th><th>Storyboard</th><th>Film</th>
                  <th>Made from it</th><th /></tr></thead>
                <tbody>
                  {Object.entries(p.episodes).map(([n, e]) => (
                    <tr key={n}>
                      <td><b>{n}</b>{(e.missing || []).length > 0 && <div className="small" style={{color: "var(--warn)"}}>missing: {e.missing!.join(", ")}</div>}</td>
                      <td>{e.scenes}</td>
                      <td>{e.rendered ?? 0} / {e.scenes}</td>
                      <td>{e.storyboard ? <Badge kind="ok">Yes</Badge> : <span className="muted">—</span>}</td>
                      <td>{film(e)}</td>
                      <td>
                        {/* what this episode has actually produced. It all lived inside the episode's
                            Output tab, which meant it may as well not have existed. */}
                        {e.graded || e.clips
                          ? <span className="row nowrap" style={{gap: 6}}>
                              {e.graded && <Badge kind="ok">graded film</Badge>}
                              {!!e.clips && <Badge kind="accent">{e.clips} photoreal</Badge>}
                            </span>
                          : <span className="muted">&mdash;</span>}
                      </td>
                      <td style={{textAlign: "right"}}>
                        <Button size="sm" onClick={() => { open(n); go("episodes"); }}>
                          {e.graded || e.clips ? "See it" : "Open"} <ArrowRight size={14} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty icon={<Clapperboard />} title="No episodes yet" text="Create the first one on the Episodes page." />}
          </Card>
        </div>
      )}
    </div>
  );
}
