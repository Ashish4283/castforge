import {useCallback, useEffect, useState} from "react";
import {ArrowRight, Check, Copy, ExternalLink, Film, Layers, Scissors, Send} from "lucide-react";
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

const ICON: Record<string, typeof Film> = {castforge: Film, forgefilms: Scissors, "graphic-novel": Layers};

function clock(s: number) {
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function Suite() {
  const {movie, toast} = useStore();
  const [info, setInfo] = useState<SuiteInfo | null>(null);
  const [busy, setBusy] = useState("");
  const [ran, setRan] = useState<{title: string; run: string} | null>(null);
  const [copied, setCopied] = useState(false);
  const load = useCallback(() => {
    api<SuiteInfo>(`/api/suite?movie=${encodeURIComponent(movie || "")}`).then(setInfo)
      .catch(e => toast((e as Error).message, "err"));
  }, [movie, toast]);
  useEffect(() => { load(); }, [load]);

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
