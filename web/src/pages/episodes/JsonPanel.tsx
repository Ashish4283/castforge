import {useEffect, useState} from "react";
import {Check} from "lucide-react";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Button, Card} from "../../components/ui";

export function JsonPanel() {
  const {toast} = useStore();
  const ep = useEpisode();
  const text = JSON.stringify(ep.model, null, 1);
  const [draft, setDraft] = useState(text);
  useEffect(() => setDraft(text), [text]);
  const apply = () => {
    try { ep.replace(JSON.parse(draft)); toast("Applied: Save to keep it."); }
    catch (e) { toast(`The JSON is invalid: ${(e as Error).message}`, "err"); }
  };
  return (
    <Card title="scene.json" text="The whole episode as text, for anything the forms don't cover. Apply, then Save."
          actions={<Button variant="primary" size="sm" icon={<Check size={14} />} disabled={draft === text} onClick={apply}>Apply</Button>}>
      <textarea className="textarea code" rows={28} spellCheck={false} value={draft} onChange={e => setDraft(e.target.value)} />
    </Card>
  );
}
