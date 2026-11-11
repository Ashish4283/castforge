import {ClipboardCopy} from "lucide-react";
import {useStore} from "../app/store";
import {Button, Card, copyText, PageHead} from "../components/ui";

export function Help() {
  const {prompts, toast} = useStore();
  return (
    <div className="page">
      <PageHead eyebrow="Support" title="Help" text="How a CastForge movie is made, step by step, and the prompts that write scenes and characters with Gemini."
                actions={<>
                  <Button icon={<ClipboardCopy size={15} />} onClick={() => prompts && copyText(prompts.scene, toast, "Scene prompt copied")}>Scene prompt</Button>
                  <Button icon={<ClipboardCopy size={15} />} onClick={() => prompts && copyText(prompts.character, toast, "Character prompt copied")}>Character prompt</Button>
                </>} />
      <Card title="How to make an episode"><pre className="log" style={{maxHeight: "none"}}>{prompts?.help || "Loading…"}</pre></Card>
    </div>
  );
}
