import {useCallback, useEffect, useState} from "react";
import {ArrowRight, Check, Copy, ExternalLink, Film, Layers, Scissors, Send, UserRound} from "lucide-react";
import {api, post} from "../api";
import {useStore} from "../app/store";
import {GpuPicker} from "../components/GpuPicker";
import {Badge, Button, Card, Empty, Notice, PageHead} from "../components/ui";

/** The three tools that make art for the same films, and the step that joins them.
 *
 *  CastForge finishes at a rendered, voiced episode. Post - colour, crossfades, loudness, captions,
 *  ambience - is forgefilms' job, and it starts from a shot list. "Hand to post" writes that shot list
 *  from the scenes CastForge already rendered. The contract is shared/handoff.py; this page only shows
 *  it and presses the button.
 */
interface Tool {
  name: string; port: number; does: string; folder: string;
  installed: boolean; running: boolean; url: string;
}
interface Ready {
  episode: string; scenes: number; seconds: number; lines: number; problems: string[];
}
interface SuiteInfo {
  tools: Tool[]; shares: Record<string, string>; problems: string[]; episodes: Ready[];
}
interface Member {
  name: string; novel_name: string; trigger: string; angles: string[]; read: string[];
  assumed: string[]; built: boolean; ready: boolean; person: boolean;
  body: string | null; appearance: string;
}
interface CastInfo { novel: string; installed: boolean; problems: string[]; cast: Member[] }

const ICON: Record<string, typeof Film> = {castforge: Film, forgefilms: Scissors, "graphic-novel": Layers};

function clock(s: number) {
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function Suite() {
  const {movie, toast, reload} = useStore();
  const [info, setInfo] = useState<SuiteInfo | null>(null);
  const [cast, setCast] = useState<CastInfo | null>(null);
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState("");
  const [ran, setRan] = useState<{title: string; run: string} | null>(null);
  const [copied, setCopied] = useState(false);
  const load = useCallback(() => {
    const m = encodeURIComponent(movie || "");
    api<SuiteInfo>(`/api/suite?movie=${m}`).then(setInfo)
      .catch(e => toast((e as Error).message, "err"));
    api<CastInfo>(`/api/suite/cast?movie=${m}`).then(setCast).catch(() => { /* the novel may be absent */ });
  }, [movie, toast]);
  useEffect(() => { load(); }, [load]);

  const build = async (who: Member) => {
    if (!movie) return toast("Open a movie first.", "err");
    setBusy(who.name);
    try {
      await post("/api/suite/cast/build", {movie, name: who.name});
      toast(`Building ${who.novel_name} from the novel's reference sheet. It appears in Characters when ready.`);
      await reload(movie);
      load();
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(""); }
  };

  const hand = async (episode: string) => {
    setBusy(episode);
    try {
      const r = await post<{title: string; run: string; problems: string[]}>(
        "/api/suite/post", {movie, episode});
      setRan({title: r.title, run: r.run});
      r.problems.forEach(p => toast(p, "err"));
      toast(`${episode} handed to forgefilms as ${r.title}`);
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(""); }
  };

  if (!info) return <div className="page"><p className="muted"><span className="spinner" /> looking at what is installed...</p></div>;
  const post_tool = info.tools.find(t => t.name === "forgefilms");

  return (
    <div className="page">
      <PageHead eyebrow="Suite" title="One platform, three tools"
                text="CastForge builds and renders the film. forgefilms does the post. graphic-novel draws it flat. They share one model library, one ComfyUI, one GPU choice and one cast." />
      <div className="stack lg">
        <div className="grid-3">
          {info.tools.map(t => {
            const Icon = ICON[t.name] || Film;
            return (
              <Card key={t.name} className="tool-card"
                    title={<span className="tool-title"><Icon size={16} /> {t.name}</span>}
                    text={t.does}
                    foot={
                      <div className="row between">
                        <Badge kind={t.running ? "ok" : t.installed ? "warn" : "err"} pip>
                          {t.running ? `running on ${t.port}` : t.installed ? `installed, not running (${t.port})` : "not here"}
                        </Badge>
                        {t.running && (
                          <a className="btn ghost sm" href={t.url} target="_blank" rel="noreferrer">
                            <ExternalLink size={13} /> open
                          </a>
                        )}
                      </div>
                    }>
                <p className="muted small mono wrap">{t.folder}</p>
              </Card>
            );
          })}
        </div>

        {cast?.installed && cast.cast.length > 0 && (
          <Card title={cast.novel ? `The cast of "${cast.novel}"` : "The novel's cast"}
                text={<>Designed in the graphic novel and locked against a turnaround. Building one here gives
                  it a body from the same reference the novel draws it with, so the 3D character and the
                  drawn panels are the same person by construction.</>}>
            <div className="cast-grid">
              {cast.cast.map(c => (
                <div key={c.name} className={`cast-card ${c.built ? "done" : ""}`}>
                  {c.body
                    ? <img src={c.body} alt={c.novel_name} loading="lazy" />
                    : <div className="cast-none"><UserRound size={20} /></div>}
                  <div className="cast-body">
                    <div className="row between">
                      <b>{c.novel_name}</b>
                      {c.built
                        ? <Badge kind="ok" pip>built</Badge>
                        : c.ready ? <Badge kind="accent">{c.angles.length} view{c.angles.length === 1 ? "" : "s"}</Badge>
                          : <Badge kind="warn">{c.person ? "no front view" : "not a person"}</Badge>}
                    </div>
                    <button className="cast-what" onClick={() => setOpen(open === c.name ? "" : c.name)}>
                      {open === c.name ? "hide what was read" : `read ${c.read.length}, guessed ${c.assumed.length}`}
                    </button>
                    {open === c.name && (
                      <div className="cast-read">
                        {c.read.map(r => <div key={r}><span className="ok-text">read</span> {r}</div>)}
                        {c.assumed.map(r => <div key={r}><span className="warn-text">guess</span> {r}</div>)}
                        <p className="muted small">{c.appearance}</p>
                      </div>
                    )}
                    <Button variant={c.built ? "ghost" : "primary"} size="sm" icon={<UserRound size={13} />}
                            busy={busy === c.name} disabled={!c.ready || !movie}
                            onClick={() => build(c)}>
                      {c.built ? "Build again" : "Give it a body"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
            {cast.problems.length > 0 && (
              <div className="stack sm" style={{marginTop: 12}}>
                {cast.problems.map(p => <Notice key={p} kind="warn">{p}</Notice>)}
              </div>
            )}
          </Card>
        )}

        <Card title="Hand an episode to post"
              text={movie
                ? <>A rendered episode of <b>{movie}</b> becomes a forgefilms shot list: one shot per scene, its own render as the picture, its finished sound as the bed, and the real line times as captions.</>
                : "Open a movie first."}>
          {!post_tool?.installed && (
            <Notice kind="warn">forgefilms is not installed under <code>suite/</code>, so there is nothing to hand an episode to.</Notice>
          )}
          {info.episodes.length === 0
            ? <Empty icon={<Send size={20} />} title="No episodes yet"
                     text="Write a scene and render it, then it can go to post." />
            : (
              <div className="item-list">
                {info.episodes.map(e => (
                  <div key={e.episode} className="item suite-row">
                    <div className="suite-what">
                      <b>{e.episode}</b>
                      <span className="muted small">
                        {e.scenes > 0
                          ? `${e.scenes} scene${e.scenes === 1 ? "" : "s"} · ${clock(e.seconds)} · ${e.lines} spoken line${e.lines === 1 ? "" : "s"}`
                          : "not rendered yet"}
                      </span>
                      {e.problems.length > 0 && (
                        <span className="small warn-text">{e.problems[0]}{e.problems.length > 1 ? ` (+${e.problems.length - 1} more)` : ""}</span>
                      )}
                    </div>
                    <Button variant={e.scenes > 0 ? "primary" : "ghost"} size="sm" icon={<ArrowRight size={14} />}
                            busy={busy === e.episode} disabled={!e.scenes || !post_tool?.installed}
                            onClick={() => hand(e.episode)}>
                      Hand to post
                    </Button>
                  </div>
                ))}
              </div>
            )}
          {ran && (
            <Notice kind="ok">
              <div className="stack sm">
                <span>Written into forgefilms as <b>{ran.title}</b>. Run the post there:</span>
                <div className="row">
                  <code className="mono wrap grow">{ran.run}</code>
                  <Button variant="ghost" size="sm" icon={copied ? <Check size={13} /> : <Copy size={13} />}
                          onClick={() => {
                            navigator.clipboard?.writeText(ran.run).then(() => {
                              setCopied(true);
                              setTimeout(() => setCopied(false), 1500);
                            }, () => toast("could not reach the clipboard", "err"));
                          }}>
                    {copied ? "copied" : "copy"}
                  </Button>
                </div>
              </div>
            </Notice>
          )}
        </Card>

        <div className="grid-2" style={{alignItems: "start"}}>
          <Card title="Shared by all of them"
                text="Written down once, in shared/suite.py. Every path can be pointed elsewhere with an environment variable.">
            <div className="item-list">
              {Object.entries(info.shares).map(([what, where]) => (
                <div key={what} className="item suite-row">
                  <div className="suite-what"><b>{what}</b><span className="mono wrap">{where}</span></div>
                </div>
              ))}
            </div>
            {info.problems.length > 0 && (
              <div className="stack sm" style={{marginTop: 10}}>
                {info.problems.map(p => <Notice key={p} kind="warn">{p}</Notice>)}
              </div>
            )}
          </Card>
          <Card title="Where the heavy work runs"
                text="One setting for the whole suite: this laptop, or the rented GPU. Every tool asks CastForge, so they cannot disagree.">
            <GpuPicker onError={m => toast(m, "err")} />
          </Card>
        </div>
      </div>
    </div>
  );
}
