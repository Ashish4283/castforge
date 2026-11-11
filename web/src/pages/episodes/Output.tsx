import {Download, Film} from "lucide-react";
import {useEpisode} from "../../app/episode";
import {Card, Empty} from "../../components/ui";

export function Output() {
  const {info} = useEpisode();
  if (!info) return null;
  return (
    <div className="stack lg">
      <Card title="Episode film" text="The finished episode: titles, transitions, grade, subtitles and mastered sound."
            actions={info.downloads.length > 0 && <div className="row">{info.downloads.map(d => (
              <a key={d.url} className="btn sm" href={d.url} download><Download size={14} />{d.name}</a>))}</div>}>
        {info.video
          ? <video className="video" src={info.video} controls key={info.video} />
          : <Empty icon={<Film />} title="Not rendered yet" text="Press Render: Blocking quality is the fastest way to see the whole episode." />}
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
      {info.storyboard && (
        <Card title="Storyboard" text="One still per shot.">
          <a className="storyboard" href={info.storyboard} target="_blank" rel="noreferrer"><img src={info.storyboard} alt="Storyboard" /></a>
        </Card>
      )}
    </div>
  );
}
