// What this episode is holding on disk, and getting rid of what it does not need.
//
// A rendered episode is mostly not film: of 552 MB, about 5 MB a scene is the picture you watch and the
// rest is working material. Three sweeps, because "rebuildable" is not one thing - a Blender backup
// costs nothing to lose, a 3D preview costs twenty seconds a scene, and a scene file costs a full
// re-render. Nothing offers to take the film, its sound, its timings or the scene it was written from.
import {useCallback, useEffect, useState} from "react";
import {AlertTriangle, HardDrive, Trash2} from "lucide-react";
import {api, post, q, Space as Held} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Badge, Button, Card, Notice} from "../../components/ui";

const SWEEPS: {how: string; label: string; what: string; warn?: boolean}[] = [
  {how: "spare", label: "Tidy up", what: "Blender's own backup files. Nothing ever reads them."},
  {how: "cheap", label: "...and the previews", what: "also the 3D previews and check renders: a button brings each back."},
  {how: "dear", label: "...and the scene files", what: "also the scene files and built sets. Only a full re-render brings those back.", warn: true},
];

export function Space() {
  const {movie, toast} = useStore();
  const ep = useEpisode();
  const [held, setHeld] = useState<Held | null>(null);
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState(false);

  const look = useCallback(async () => {
    if (!ep.ep) return;
    try { setHeld(await api<Held>(`/api/episode/space?${q({movie, episode: ep.ep})}`)); }
    catch { setHeld(null); }
  }, [movie, ep.ep]);
  useEffect(() => { if (open) look(); }, [open, look]);

  const sweep = async (how: string, label: string) => {
    setBusy(how);
    try {
      const r = await post<{files: number; words: string; problems: string[]}>(
        "/api/episode/clean", {movie, episode: ep.ep, how_far: how});
      r.problems.forEach(p => toast(p, "err"));
      toast(r.files ? `${label}: ${r.files} files gone, ${r.words} free` : "there was nothing to sweep");
      await look();
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(""); }
  };

  if (!ep.ep) return null;
  return (
    <Card title="Space on disk" bodyClass={open ? "" : "tight"}
          text={held ? `This episode is holding ${held.words.total}.` : "What this episode is holding, and what it does not need."}
          actions={<div className="row nowrap">
            {held && <Badge kind={held.spare > 50e6 ? "warn" : undefined}>{held.words.spare} spare</Badge>}
            <Button size="sm" icon={<HardDrive size={14} />} onClick={() => setOpen(o => !o)}>
              {open ? "Hide" : "Look"}
            </Button>
          </div>}>
      {open && (
        <div className="stack">
          {!held && <p className="muted"><span className="spinner" /> measuring...</p>}
          {held && (
            <>
              <div className="held">
                {held.kinds.map(k => (
                  <div key={k.name} className={`held-row ${k.group}`}>
                    <b>{k.words}</b>
                    <span>{k.name}</span>
                    <small>{k.files} file{k.files === 1 ? "" : "s"}</small>
                    <em>back by: {k.back}</em>
                  </div>
                ))}
                {!held.kinds.length && <p className="muted" style={{margin: 0}}>Nothing here can be swept.</p>}
              </div>
              <div className="sweeps">
                {SWEEPS.map(s => {
                  const frees = (held as unknown as Record<string, string>) && held.words[s.how as "spare"];
                  return (
                    <div key={s.how} className={`sweep ${s.warn ? "warn" : ""}`}>
                      <div className="grow">
                        <b>{s.label}</b>
                        <div className="muted small">{s.what}</div>
                      </div>
                      <Badge>{frees} free</Badge>
                      <Button size="sm" variant={s.warn ? "danger" : undefined} busy={busy === s.how}
                              disabled={!!busy} onClick={() => sweep(s.how, s.label)}>Sweep</Button>
                    </div>
                  );
                })}
              </div>
              <Notice>
                A re-render writes over what it made before, so rendering again does not pile up - but
                Blender leaves a backup beside every file it saves, and those do.
              </Notice>
            </>
          )}
        </div>
      )}
    </Card>
  );
}

/** Renaming and deleting an episode. Making one was a one-way door until now. */
export function EpisodeFile() {
  const {movie, toast, reload} = useStore();
  const ep = useEpisode();
  const short = (ep.ep || "").split("/").pop() || "";
  const [name, setName] = useState(short);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => { setName(short); setConfirm(""); }, [ep.ep]);
  if (!ep.ep) return null;

  const rename = async () => {
    const want = name.trim().toLowerCase().replace(/[ -]+/g, "_");
    if (!want || want === short) return;
    setBusy("rename");
    try {
      const r = await post<{episode: string}>("/api/episode/rename", {movie, episode: ep.ep, name: want});
      await reload(movie);
      await ep.open(r.episode);
      toast(`Now called ${want}`);
    } catch (e) { toast((e as Error).message, "err"); setName(short); }
    finally { setBusy(""); }
  };
  const remove = async () => {
    setBusy("delete");
    try {
      const r = await post<{words: string}>("/api/episode/delete", {movie, episode: ep.ep, confirm});
      toast(`${short} deleted, ${r.words} free`);
      await reload(movie);
      location.hash = "/episodes";
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(""); }
  };

  return (
    <Card title="This episode" text="Rename it, or delete it and everything in it.">
      <div className="stack">
        <div className="row nowrap wrap">
          <span className="muted small" style={{minWidth: 54}}>Name</span>
          <input className="input" style={{maxWidth: 260}} value={name} onChange={e => setName(e.target.value)}
                 onKeyDown={e => { if (e.key === "Enter") rename(); }} />
          <Button size="sm" busy={busy === "rename"} disabled={!name.trim() || name.trim() === short}
                  onClick={rename}>Rename</Button>
        </div>
        <div className="danger-zone">
          <div className="row nowrap wrap">
            <AlertTriangle size={15} className="warn-text" />
            <div className="grow">
              <b>Delete this episode</b>
              <div className="muted small">
                Everything in it goes: the renders, the film, the clips. There is no undo.
                Type <code>{short}</code> to confirm.
              </div>
            </div>
            <input className="input sm" style={{width: 160}} value={confirm} placeholder={short}
                   onChange={e => setConfirm(e.target.value)} />
            <Button size="sm" variant="danger" icon={<Trash2 size={14} />} busy={busy === "delete"}
                    disabled={confirm !== short} onClick={remove}>Delete</Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
