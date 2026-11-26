// Everything this movie has actually produced, in one place.
//
// Results used to be reachable only from inside the episode that made them - the graded cut and the
// photoreal clips lived in one tab of one episode, which is the same as not existing. This is the page
// to open when the question is "where is the thing we made".
import {useCallback, useEffect, useState} from "react";
import {Camera, Clapperboard, Download, Film, Images, RefreshCw, Wand2} from "lucide-react";
import {api, q} from "../api";
import {useStore} from "../app/store";
import {Badge, Button, Card, Empty, PageHead} from "../components/ui";

interface Result {
  episode: string; kind: string; what: string; note: string; url: string;
  bytes: number; when: number; still?: string | null;
}
interface Made { movie: string; results: Result[]; words: Record<string, string> }

const KINDS: Record<string, {title: string; icon: JSX.Element; says: string}> = {
  film: {title: "Episode films", icon: <Film size={15} />,
         says: "Rendered and finished by CastForge: titles, transitions, grade, subtitles, mixed sound."},
  graded: {title: "Graded cuts", icon: <Wand2 size={15} />,
           says: "Cut and finished by forgefilms: colour, 0.5 s crossfades, captions, mastered to -16 LUFS."},
  photoreal: {title: "Photoreal clips", icon: <Camera size={15} />,
              says: "The same shots photographed: each still re-imagined by RealVisXL, then animated by Wan 2.2."},
  storyboard: {title: "Storyboards", icon: <Images size={15} />, says: "One still per shot the director cut."},
};
const ORDER = ["graded", "photoreal", "film", "storyboard"];

export function Results() {
  const {movie, go, toast} = useStore();
  const [made, setMade] = useState<Made | null>(null);
  const [busy, setBusy] = useState(false);

  const look = useCallback(async () => {
    if (!movie) return;
    setBusy(true);
    try { setMade(await api<Made>(`/api/movie/results?${q({movie})}`)); }
    catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  }, [movie, toast]);
  useEffect(() => { look(); }, [look]);

  const all = made?.results || [];
  const when = (t: number) => new Date(t * 1000).toLocaleString();
  return (
    <div className="page">
      <PageHead eyebrow="Produce" title="Results"
                text="Everything this movie has made: the films, the graded cuts, the photoreal clips and the storyboards. Each one says which episode it came from."
                actions={<Button icon={<RefreshCw size={15} />} busy={busy} onClick={look}>Look again</Button>} />
      {!all.length && !busy && (
        <Card>
          <Empty icon={<Clapperboard />} title="Nothing made yet"
                 text="Render an episode, then its film appears here. Hand it to post for a graded cut, or make it real for photoreal clips."
                 action={<Button variant="primary" onClick={() => go("episodes")}>Open an episode</Button>} />
        </Card>
      )}
      {ORDER.filter(k => all.some(r => r.kind === k)).map(kind => {
        const rows = all.filter(r => r.kind === kind);
        const about = KINDS[kind];
        return (
          <Card key={kind} title={<span className="row nowrap" style={{gap: 7}}>{about.icon}{about.title}</span>}
                text={about.says} actions={<Badge>{rows.length}</Badge>}>
            <div className="result-grid">
              {rows.map(r => (
                <div key={r.url} className="result">
                  {kind === "storyboard"
                    ? <a href={r.url} target="_blank" rel="noreferrer"><img src={r.url} alt="" /></a>
                    : <video src={r.url} controls preload="metadata" poster={r.still || undefined} />}
                  <div className="result-what">
                    <b>{r.what}</b>
                    <span className="muted small">
                      {r.episode} &middot; {made?.words[r.url]} &middot; {when(r.when)}
                    </span>
                  </div>
                  <div className="row nowrap" style={{gap: 6}}>
                    <Button size="sm" onClick={() => go("episodes")}>Open {r.episode}</Button>
                    <a className="btn sm" href={r.url} download><Download size={14} />Save</a>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
