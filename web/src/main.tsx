import {StrictMode, useState} from "react";
import {createRoot} from "react-dom/client";
import "@fontsource-variable/inter";
import "./styles.css";
import {StoreProvider, useStore} from "./app/store";
import {EpisodeProvider} from "./app/episode";
import {GpuProvider} from "./components/GpuPicker";
import {Sidebar} from "./layout/Sidebar";
import {Toasts} from "./components/ui";
import {Studio} from "./pages/Studio";
import {Characters} from "./pages/Characters";
import {CharacterDesigner} from "./pages/CharacterDesigner";
import {Results} from "./pages/Results";
import {Episodes} from "./pages/episodes/Episodes";
import {Sets} from "./pages/Sets";
import {Props} from "./pages/Props";
import {Library} from "./pages/Library";
import {Suite} from "./pages/Suite";
import {Help} from "./pages/Help";

function Page() {
  const {route} = useStore();
  switch (route[0]) {
    case "episodes": return <Episodes />;
    case "results": return <Results />;
    case "characters": return route[1] ? <CharacterDesigner name={route[1]} /> : <Characters />;
    case "sets": return <Sets />;
    case "props": return <Props />;
    case "library": return <Library />;
    case "suite": return <Suite />;
    case "help": return <Help />;
    default: return <Studio />;
  }
}

function Shell() {
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("cf.side") === "small"; } catch { return false; }
  });
  const collapse = (v: boolean) => {
    setCollapsed(v);
    try { localStorage.setItem("cf.side", v ? "small" : "full"); } catch { /* ignore */ }
  };
  return (
    <div className={`shell ${collapsed ? "collapsed" : ""}`}>
      <Sidebar collapsed={collapsed} onCollapse={collapse} />
      <main className="main"><Page /></main>
      <Toasts />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StoreProvider>
      <EpisodeProvider>
        <GpuProvider>
          <Shell />
        </GpuProvider>
      </EpisodeProvider>
    </StoreProvider>
  </StrictMode>,
);
