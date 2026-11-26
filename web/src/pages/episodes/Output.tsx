import {useState} from "react";
import {Download, Film, UploadCloud} from "lucide-react";
import {post} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Button, Card, Empty, Notice} from "../../components/ui";

export function Output() {
  const {movie, toast} = useStore();
  const ep = useEpisode();
  const [report, setReport] = useState("");
  const [busy, setBusy] = useState(false);
  const info = ep.info;
  if (!info) return null;
  const publish = async () => {
    setBusy(true);
    try {
      const r = await post<{ok: boolean; problems: number; report: string}>(
        "/api/episode/publish", {movie, episode: ep.ep});
      setReport(r.report);
      toast(r.ok ? "Publish package ready: see the downloads above." : `${r.problems} to fix before publishing (see the report).`, r.ok ? "ok" : "err");
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  };
  return (
    <div className="stack lg">
      <Card title="Episode film" text="The finished episode: titles, transitions, grade, subtitles and mastered sound."
            actions={<div className="row nowrap">
              {info.video && <Button size="sm" icon={<UploadCloud size={14} />} busy={busy} onClick={publish}
                                     title="Checks the film and writes publish/: YouTube loudness, 1280x720 thumbnail, valid chapters, description">Prepare for YouTube</Button>}
              {info.downloads.map(d => (
                <a key={d.url} className="btn sm" href={d.url} download><Download size={14} />{d.name}</a>))}
            </div>}>
        {info.video
          ? <video className="video" src={info.video} controls key={info.video} />
          : <Empty icon={<Film />} title="Not rendered yet" text="Press Render: Blocking quality is the fastest way to see the whole episode." />}
        {report && (
          <div className="stack" style={{marginTop: 14, gap: 8}}>
            <Notice>What the publish check found:</Notice>
            <pre className="log">{report}</pre>
          </div>
        )}
      </Card>
      {info.shots.length > 0 && (
        <Card title="Scenes" text="Each scene as rendered, before finishing.">
          <div className="shots">
            {info.shots.map(s => (
              <div key={s.video} className="stack" style={{gap: 6}}>
                <span className="muted small">{s.name}</span>
                <video src={s.video} controls preload="metadata" />
              </div>
            ))}
          </div>
        </Card>
      )}
      {info.post && (
        <Card title="Graded film"
              text="Cut and finished by forgefilms: colour, crossfades, captions, mastered to -16 LUFS.">
          <video className="video" src={info.post.video} controls key={info.post.video}>
            {info.post.captions && <track default kind="captions" src={info.post.captions}
                                          srcLang="en" label="English" />}
          </video>
        </Card>
      )}
      {info.real?.length > 0 && (
        <Card title="Photoreal clips"
              text="The same shots, photographed: each still was re-imagined by RealVisXL and then animated.">
          <div className="shots">
            {info.real.map(c => (
              <div key={c.id} className="stack" style={{gap: 6}}>
                <span className="muted small">{c.id}</span>
                <video src={c.video} controls preload="metadata" poster={c.still || undefined} />
              </div>
            ))}
          </div>
        </Card>
      )}
      {info.storyboard && (
        <Card title="Storyboard" text="One still per shot.">
          <a className="storyboard" href={info.storyboard} target="_blank" rel="noreferrer"><img src={info.storyboard} alt="Storyboard" /></a>
        </Card>
      )}
    </div>
  );
}
