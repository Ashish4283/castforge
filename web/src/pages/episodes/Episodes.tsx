import {lazy, Suspense, useEffect, useState} from "react";
import {Box, Braces, CheckCircle2, ClipboardCopy, Clapperboard, Film, LayoutGrid, MessageSquareText, Play, Plus,
  Save, Settings2, Sparkles, Square, Trash2, Wand2} from "lucide-react";
import {api, post, q} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Badge, Button, Card, copyText, Empty, Modal, Notice, Select, Tabs} from "../../components/ui";
import {SceneSetup} from "./SceneSetup";
import {Scenes} from "./Scenes";
import {Script} from "./Script";
import {Output} from "./Output";
import {Finishing} from "./Finishing";
const Editor3D = lazy(() => import("./Editor3D").then(m => ({default: m.Editor3D})));   // three.js loads on first use
import {JsonPanel} from "./JsonPanel";

type Tab = "scene" | "script" | "3d" | "output" | "finishing" | "json";
const QUALITIES: [string, string][] = [["blocking", "Blocking · fast 480p"], ["draft", "Draft · 640×360"],
  ["standard", "Standard · 960×540"], ["final", "Final · full size"], ["ultra", "Ultra · 1920 wide"]];

function percent(status: string) {
  const m = /(\d+)\/(\d+) frames/.exec(status), sc = /scene (\d+)\/(\d+)/.exec(status);
  if (status.startsWith("finished")) return 100;
  if (!m) return 0;
  const f = +m[1] / Math.max(+m[2], 1);
  return sc ? ((+sc[1] - 1 + f) / +sc[2]) * 100 : f * 100;
}

export function Episodes() {
  const {current, movie, prompts, toast, reload} = useStore();
  const ep = useEpisode();
  const [tab, setTab] = useState<Tab>(() => (localStorage.getItem("cf.epTab") as Tab) || "scene");
  const [newName, setNewName] = useState("");
  const [check, setCheck] = useState<{ok: boolean; output: string} | null>(null);
  const [busy, setBusy] = useState("");
  const [killing, setKilling] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [held, setHeld] = useState<string | null>(null);
  useEffect(() => {
    setHeld(null);
    if (!killing) return;
    api<{words: {total: string}}>(`/api/episode/space?${q({movie, episode: killing})}`)
      .then(r => setHeld(r.words.total)).catch(() => setHeld(null));
  }, [killing, movie]);
  const kill = async () => {
    const name = (killing || "").split("/").pop() || "";
    setBusy("delete");
    try {
      const r = await post<{words: string}>("/api/episode/delete",
                                            {movie, episode: killing, confirm: name});
      toast(`${name} deleted, ${r.words} free`);
      if (killing === ep.ep) await ep.open("");
      setKilling(null);
      await reload(movie);
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(""); }
  };
  const pick = (t: Tab) => { setTab(t); try { localStorage.setItem("cf.epTab", t); } catch { /* ignore */ } };

  const act = async (what: string, fn: () => Promise<string | void>) => {
    setBusy(what);
    try { const text = await fn(); if (text) toast(text); }
    catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(""); }
  };
  const body = () => ({movie, episode: ep.ep});
  const add = () => act("add", async () => {
    await post("/api/episode/new", {movie, episode: newName});
    const n = newName.toLowerCase().replace(/[ -]/g, "_");
    setNewName("");
    await reload(movie);
    await ep.open(n);
    return `Episode ${n} created`;
  });
  const model = ep.model;
  const scenes = Array.isArray(model?.scenes) ? model.scenes : null;
  const quality = (ep.scene() || model)?.quality || model?.quality || "blocking";
  const status = ep.info?.status || "";
  const pct = percent(status);

  const killName = (killing || "").split("/").pop() || "";
  return (
    <div className="workspace">
      {killing && (
        <Modal title={`Delete ${killName}?`} onClose={() => setKilling(null)}
               text="Everything in it goes: the renders, the film, the photoreal clips. There is no undo."
               foot={<>
                 <Button variant="ghost" onClick={() => setKilling(null)}>Keep it</Button>
                 <Button variant="danger" icon={<Trash2 size={14} />} busy={busy === "delete"}
                         disabled={typed !== killName} onClick={kill}>
                   Delete {held ? `and free ${held}` : "it"}
                 </Button>
               </>}>
          <div className="stack">
            <p className="muted small" style={{margin: 0}}>
              {held ? <>This episode is holding <b>{held}</b> on disk.</>
                    : <><span className="spinner" /> measuring what it is holding...</>}
            </p>
            <p className="muted small" style={{margin: 0}}>
              If you only want the space back, close this and use <b>Space on disk</b> in the Output
              tab instead: it clears what can be made again and keeps the film.
            </p>
            <label className="field">
              <span>Type <code>{killName}</code> to confirm</span>
              <input className="input" autoFocus value={typed} placeholder={killName}
                     onChange={e => setTyped(e.target.value)}
                     onKeyDown={e => { if (e.key === "Enter" && typed === killName) kill(); }} />
            </label>
          </div>
        </Modal>
      )}
      <aside className="ep-list">
        <div className="ep-head"><Clapperboard size={15} className="muted" /><h2>Episodes</h2><Badge>{current?.episodes.length ?? 0}</Badge></div>
        {(current?.episodes || []).map(e => (
          <div key={e} className={`ep-row ${e === ep.ep ? "on" : ""}`}>
            <button className="ep-item" onClick={() => ep.open(e)} title={e}>
              <span className="ep-icon"><Film size={14} /></span><span>{e}</span>
            </button>
            <button className="ep-kill" title={`Delete ${e} and everything in it`}
                    onClick={ev => { ev.stopPropagation(); setKilling(e); setTyped(""); }}>
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        <div className="row nowrap" style={{marginTop: 10}}>
          <input className="input sm" style={{flex: 1}} value={newName} onChange={e => setNewName(e.target.value)} placeholder="New episode name"
                 onKeyDown={e => { if (e.key === "Enter" && newName) add(); }} />
          <Button size="sm" square icon={<Plus size={14} />} disabled={!newName} busy={busy === "add"} onClick={add} aria-label="Add episode" />
        </div>
      </aside>
      <div className="ep-main">
        {!ep.ep ? (
          <Card><Empty icon={<Clapperboard />} title="Choose an episode" text="Pick one on the left, or create a new one." /></Card>
        ) : (
          <>
            <div className="ep-bar">
              <div style={{minWidth: 0}}>
                <div className="muted small">Episode</div>
                <h1>{ep.ep}</h1>
              </div>
              {scenes && (
                <span className="muted small">scene {ep.part + 1} of {scenes.length}: <b>{scenes[ep.part]?.id || "untitled"}</b></span>
              )}
              {ep.dirty && <Badge kind="warn" pip>Unsaved</Badge>}
              <div className="spacer" />
              <Button variant="ghost" icon={<ClipboardCopy size={15} />} onClick={() => prompts && copyText(prompts.scene, toast, "Scene prompt copied")}>Gemini prompt</Button>
              <Button icon={<Save size={15} />} busy={busy === "save"} onClick={() => act("save", async () => { await ep.save(); return "Saved"; })}>Save</Button>
              <Button icon={<CheckCircle2 size={15} />} busy={busy === "check"} onClick={() => act("check", async () => {
                await ep.save();
                const r = await post<{ok: boolean; output: string}>("/api/episode/check", body());
                setCheck(r);
              })}>Check</Button>
              <Select className="sm" value={quality} options={QUALITIES} aria-label="Quality"
                      onChange={v => ep.update(m => { (ep.scene() || m).quality = v; })} />
              <Button icon={<LayoutGrid size={15} />} busy={busy === "board"} title="One still per shot, about a minute per scene"
                      onClick={() => act("board", async () => { await ep.save(); await post("/api/episode/storyboard", body()); return "Making the storyboard (about a minute per scene)…"; })}>Storyboard</Button>
              {ep.info?.rendering
                ? <Button variant="danger" icon={<Square size={14} />} busy={busy === "stop"} onClick={() => act("stop", async () => (await post<{output: string}>("/api/episode/stop", body())).output)}>Stop</Button>
                : <Button variant="primary" icon={<Play size={15} />} busy={busy === "render"} onClick={() => act("render", async () => {
                    await ep.save(); await post("/api/episode/render", {...body(), quality}); pick("output");
                    return "Rendering in the background. You can close this page; it keeps going.";
                  })}>Render</Button>}
              <Button variant="ghost" icon={<Wand2 size={15} />} busy={busy === "finish"} title="Redo titles, transitions, grade, subtitles and sound without rendering"
                      onClick={() => act("finish", async () => { await ep.save(); await post("/api/episode/finish", body()); return "Finished: the video and downloads are updated."; })}>Finish only</Button>
            </div>
            {status && (
              <div className="status-strip">
                {ep.info?.rendering ? <span className="spinner" /> : <Sparkles size={15} className="muted" />}
                <span className="dim small" style={{flex: 1, minWidth: 0}}>{status}</span>
                {(ep.info?.rendering || pct > 0) && <div className="progress"><i style={{width: `${pct}%`}} /></div>}
              </div>
            )}
            {ep.error && <Notice kind="err">{ep.error}</Notice>}
            {check && (
              <div className="stack" style={{marginBottom: 18}}>
                <Notice kind={check.ok ? "ok" : "err"}>{check.ok ? "Looks good: no problems found." : "Problems found:"}
                  <Button size="sm" variant="ghost" style={{marginLeft: 8}} onClick={() => setCheck(null)}>Hide</Button></Notice>
                {!check.ok && <pre className="log">{check.output}</pre>}
              </div>
            )}
            {model && (
              <>
                <Tabs value={tab} onChange={pick} tabs={[
                  ["scene", "Stage", <Settings2 size={15} />], ["script", "Script", <MessageSquareText size={15} />],
                  ["3d", "3D editor", <Box size={15} />], ["output", "Output", <Film size={15} />],
                  ["finishing", "The cut", <Wand2 size={15} />], ["json", "JSON", <Braces size={15} />]]} />
                {tab === "scene" && <><Scenes /><SceneSetup /></>}
                {tab === "script" && <Script />}
                {tab === "3d" && <Suspense fallback={<Card><span className="spinner" /></Card>}><Editor3D /></Suspense>}
                {tab === "output" && <Output />}
                {tab === "finishing" && <Finishing />}
                {tab === "json" && <JsonPanel />}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
