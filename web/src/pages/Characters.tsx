import {useState} from "react";
import {Camera, ClipboardCopy, Palette, Plus, Sparkles, UserRound, Wand2} from "lucide-react";
import {form, post} from "../api";
import {useStore} from "../app/store";
import {Badge, Button, copyText, Empty, Field, Modal, PageHead, PictureDrop, Segmented, Select} from "../components/ui";

export function Characters() {
  const {current, go, jobs, movie} = useStore();
  const [adding, setAdding] = useState(false);
  const building = new Set(jobs.filter(j => j.state === "building" && j.movie === movie).map(j => j.name));
  const chars = current?.characters || [];
  return (
    <div className="page">
      <PageHead eyebrow="Assets" title="Characters"
                text="Every person in the movie: rigged, dressed and ready to act. Open one to change its design, costume and colours, then rebuild it."
                actions={<Button variant="primary" icon={<Plus size={16} />} onClick={() => setAdding(true)}>New character</Button>} />
      {chars.length === 0 && !adding ? (
        <div className="card"><Empty icon={<UserRound />} title="No characters yet" text="Design a character here, paste a Gemini design, or build one from a photo."
                                     action={<Button variant="primary" icon={<Plus size={16} />} onClick={() => setAdding(true)}>New character</Button>} /></div>
      ) : (
        <div className="gallery">
          {chars.map(c => (
            <button key={c.name} className="tile" onClick={() => go("characters", c.name)}>
              <div className="thumb contain">
                {c.preview ? <img src={c.preview} alt={c.name} loading="lazy" /> : <UserRound size={40} className="muted" />}
                <div className="over">{building.has(c.name) && <Badge kind="warn"><span className="spinner" style={{width: 9, height: 9}} />Building</Badge>}</div>
              </div>
              <div className="meta"><b>{c.name}</b><small>{c.design ? "Design" : "From a photo"}</small></div>
            </button>
          ))}
          <button className="tile add" onClick={() => setAdding(true)}><Plus size={22} /><span>New character</span></button>
        </div>
      )}
      {adding && <NewCharacter onClose={() => setAdding(false)} />}
    </div>
  );
}

function NewCharacter({onClose}: {onClose: () => void}) {
  const {movie, schema, prompts, toast, go} = useStore();
  const [mode, setMode] = useState<"design" | "gemini" | "photo">("design");
  const [name, setName] = useState("");
  const [json, setJson] = useState("");
  const [gender, setGender] = useState("female");
  const [age, setAge] = useState("30");
  const [height, setHeight] = useState("168");
  const [costume, setCostume] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [face, setFace] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const slug = name.trim().toLowerCase().replace(/[ -]+/g, "_");
  const run = async () => {
    if (!/^[a-z0-9_]{1,40}$/.test(slug)) return toast("Give the character a name: letters, numbers and _", "err");
    setBusy(true);
    try {
      if (mode === "design") { onClose(); go("characters", slug); return; }
      if (mode === "gemini") await post("/api/character/design", {movie, name: slug, design: json});
      else {
        if (!photo) throw new Error("Choose a full-body photo.");
        await form("/api/character/photo", {movie, name: slug, gender, age, height_cm: height, photo, face_photo: face, costume});
      }
      toast(`Building ${slug}: about 4 minutes. It appears here when ready.`, "info");
      onClose();
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  };
  return (
    <Modal title="New character" text="Three ways to make one; all of them can be edited and rebuilt later." onClose={onClose}
           foot={<><div className="spacer" /><Button variant="ghost" onClick={onClose}>Cancel</Button>
             <Button variant="primary" busy={busy} icon={mode === "design" ? <Palette size={15} /> : <Wand2 size={15} />} onClick={run}>
               {mode === "design" ? "Open the designer" : "Build character"}</Button></>}>
      <div className="stack">
        <Segmented value={mode} onChange={setMode} options={[
          ["design", <><Palette size={14} />Design here</>], ["gemini", <><Sparkles size={14} />Gemini design</>], ["photo", <><Camera size={14} />From a photo</>]]} />
        <Field label="Name" hint="Lowercase letters, numbers and _, for example noelle_brooks" required>
          <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="noelle_brooks" autoFocus />
        </Field>
        {mode === "design" && <p className="dim" style={{margin: 0}}>Pick body, face, hair, outfit and costume with controls and ready-made looks (such as a Santa suit), then build.</p>}
        {mode === "gemini" && (
          <>
            <div className="row">
              <span className="dim small" style={{flex: 1}}>Copy the prompt into Gemini, describe the character on its last line, and paste Gemini's answer below.</span>
              <Button size="sm" icon={<ClipboardCopy size={14} />} onClick={() => prompts && copyText(prompts.character, toast, "Character prompt copied")}>Copy Gemini prompt</Button>
            </div>
            <textarea className="textarea code" rows={10} value={json} onChange={e => setJson(e.target.value)} placeholder='{"gender": "female", "age": 30, ...}' />
          </>
        )}
        {mode === "photo" && (
          <>
            <div className="grid-3">
              <Field label="Body"><Select value={gender} onChange={setGender} options={["female", "male"]} /></Field>
              <Field label="Age"><input className="input" type="number" value={age} onChange={e => setAge(e.target.value)} /></Field>
              <Field label="Height (cm)"><input className="input" type="number" value={height} onChange={e => setHeight(e.target.value)} /></Field>
            </div>
            <Field label="Full-body photo" hint="One person, head to toe, facing the camera, arms a little away from the body. Only people who agreed." required>
              <PictureDrop file={photo} onFile={setPhoto} label="Body photo" />
            </Field>
            <Field label="Face photo (recommended)" hint="A sharp front close-up of the same person.">
              <PictureDrop file={face} onFile={setFace} label="Face photo" />
            </Field>
            <Field label="Costume" hint="A photo can't show what a costume is made of: pick one to add its coat, trim, belt, gloves and boots.">
              <Select value={costume} onChange={setCostume} options={Object.keys(schema?.costumes || {})} placeholder="None (clothes from the photo)" />
            </Field>
          </>
        )}
      </div>
    </Modal>
  );
}
