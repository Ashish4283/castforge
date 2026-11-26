---
name: run-castforge
description: Launch the CastForge app and drive it in a real browser to see a change working - start the server on a test port, build the web bundle, click through with headless Chrome over CDP, and screenshot. Use whenever asked to run, start, open or screenshot the app, or to confirm a UI change really works rather than only type-checks.
---

# Running CastForge and seeing it work

Type-checking a React change proves nothing about whether it appears. Every UI change here is confirmed
by driving the real app and looking at it, because this project has produced, more than once, a feature
that built cleanly, passed its tests and was invisible to the person using it.

## The two ports, and the trap behind them

| port | whose | rule |
|---|---|---|
| **8765** | the user's own app | never take it, never restart it without asking |
| **8787** | yours | start and stop it freely |

```bash
# the user's app may already hold 8787 from an earlier session: take it back first
powershell -c "(Get-NetTCPConnection -LocalPort 8787 -State Listen -EA SilentlyContinue).OwningProcess | Select -Unique | % { Stop-Process -Id \$_ -Force }"
cd "<repo>" && (python -m uvicorn app.server:app --port 8787 --host 127.0.0.1 > /dev/null 2>&1 &)
sleep 12                       # 8 is not always enough; a short sleep returns empty JSON and looks like a bug
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8787/api/schema
```

**A Python change needs the server restarted. A web change needs the bundle rebuilt.** Forgetting either
is the single most common way to "verify" a change against the old code:

```bash
cd web && npx vite build          # writes into ../app/ui - the server serves THAT, not web/src
```

`npx tsc --noEmit` must be run from `web/`. From the repo root, `npx tsc` installs a different,
unrelated `tsc` package and prints "This is not the tsc command you are looking for".

## Driving it

There is no Playwright module installed, but Chrome is on the machine and the system Python has
`websockets`, which is all CDP needs.

```python
CHROME = r"C:\Users\<user>\AppData\Local\ms-playwright\chromium-1255\chrome-win64\chrome.exe"
subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9333",
                  "--user-data-dir=<a scratch dir>", "--window-size=1680,1060", "--hide-scrollbars",
                  "--force-device-scale-factor=1", "--no-first-run", "--no-default-browser-check",
                  "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "about:blank"])
# then: GET http://127.0.0.1:9333/json -> webSocketDebuggerUrl -> Page.enable, Runtime.enable,
# Emulation.setDeviceMetricsOverride, Page.navigate, Runtime.evaluate, Page.captureScreenshot
```

**`--disable-gpu` screenshots the whole page BLACK** once a WebGL canvas is anywhere on it - not just the
canvas, the entire capture. It cost a long debugging detour. Use the two swiftshader flags instead.

**`PYTHONIOENCODING=utf-8`** on any driver script that prints page text: the UI is full of emoji and the
Windows console encoder raises `UnicodeEncodeError` on them, killing the script after the useful part.

## Getting to the thing you changed

Most of this app is behind a click, not behind a URL. The movie and the episode are chosen by clicking,
and the episode tabs are React state, not routes:

```
#/episodes  ->  click .ep-item "act1"  ->  click .tabs button "Stage" | "Script" | "3D editor" | "The cut" | "Output"
#/suite     ->  the three tools, the novel's cast, the post and photoreal buttons
#/studio    ->  Overview (the landing page)
```

Clicking by text beats clicking by index - the DOM order changes, the words do not:

```javascript
[...document.querySelectorAll(sel)].find(e => e.textContent.toLowerCase().includes(want))?.click()
```

The page scrolls an inner container, not the body: `window.scrollTo` does nothing. Find the element whose
`scrollHeight > clientHeight`, or call `scrollIntoView({block: "center"})` on what you want to see.

## Proving it, not just photographing it

A screenshot shows that something rendered. It does not show that it works, and this project has shipped
a control that looked right and put the marker where the pointer was not. Where geometry or state is
involved, assert it:

- click real pixels with `Input.dispatchMouseEvent` and read the value back out of the page
- change something in the UI, then open the JSON tab and read the model to see the file changed
- take two screenshots and compare the bytes to prove a view actually moved

## When nothing seems to have changed

Check in this order, because the first two are the usual answer:

1. Was the bundle rebuilt? `grep -c "<some new string>" app/ui/assets/index-*.js`
2. Was the server restarted? A new route answering 404 means old Python.
3. Is the user looking at a page you did not change? Overview is the landing page; most new work
   lives inside an episode. If they cannot find it, that is a discoverability bug, not their mistake.
