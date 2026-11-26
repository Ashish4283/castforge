---
name: castforge-ux
description: How to design anything in the CastForge app so a director can use it - where a thing belongs, how one step hands over to the next, which control to reach for, and the discoverability rules this project learned by breaking them. Use before adding or changing any page, panel, control or output location.
---

# Designing CastForge so a director can use it

This is a tool for someone making a film, not for someone reading a schema. Every rule below was paid
for by a real failure in this project.

## The one test that matters

**If the person cannot find it, it does not exist.** Not "it is in the Output tab", not "it is in
`tmp/`", not "it is behind two clicks they do not know about". Three times now, work that was finished,
correct and tested was invisible, and the honest report was "nothing happened".

Before calling anything done, answer out loud:

1. Where does what this makes **land on disk**? If the answer is not inside `movies/<movie>/...`, it has
   not been delivered. Scratch folders are for working, never for results.
2. Where does the person **see it** without being told? If that is only a tab inside a thing they have
   to open first, add it to the page they land on as well.
3. What do they **do next**, and does the screen say so?

## Where things belong

| what | where it lives | where it is seen |
|---|---|---|
| a rendered episode | `<episode>/episode.mp4` | Output tab, Overview row |
| the graded cut | `<episode>/post/film.mp4` | Output tab, Overview "Made from it" |
| photoreal clips | `<episode>/real/<id>.mp4` | Output tab, Overview "Made from it" |
| a built character | `<movie>/characters/<name>.blend` | Characters page, and as a FACE wherever cast is chosen |
| a built set | `<movie>/sets/<name>/` | Sets page, and as a PICTURE in the scene settings |

A new kind of output needs three things in the same change: a home in the movie folder, a field in
`/api/episode` (or `/api/movie/progress`), and somewhere on screen. Shipping one or two of the three is
how the last three features became invisible.

## Reach for the right control

`components/controls.tsx` exists so nobody builds a form again. `ParamInput.tsx` routes by schema TYPE,
so a new action in `core/schema.py` arrives playable with no UI work at all.

- a place on the floor -> `StagePad`, never two numbers in a text box
- a number -> `Regulator`, with its span in `schema.RANGES`
- a word from a list -> `ChipPick` with a picture from `glyphs.ts`
- a person -> their face (`CastThumbs`), never their name in a drop-down
- a voice -> `VoicePicker`, which you listen to before choosing
- which way something points -> `Dial`
- a set or a picture -> the picture itself (`PicturePick`)

**Every control must say what it is.** Five unlabelled squares with an emoji in each is not a camera
control; it became one when each square was named and a line said what the pad was for.

## One thing is said in one place

`background` and `set_folder` both say where a scene is. They were separate fields that could disagree,
and a scene that would have rendered was refused because of a picture nothing used. Now choosing a set
sets the picture, and choosing a picture drops the set.

When two fields can contradict each other, either make one of them follow the other, or refuse the pair
with a sentence saying which to drop (`schema.costume_clashes`).

## Never fail in silence, never refuse without a cure

A build that cannot make something must say so. `santa_2` asked for a one-piece suit AND a long coat;
the build made the suit, reported `"problems": []`, and produced a red onesie that nobody could trace.

Every refusal says three things: **what was asked for, why it cannot happen, and what to change.**

    costume.coat "long" and outfit.style "suit" cannot both be built: a long coat is made by
    continuing the top's hem downwards, and a one-piece outfit has no separate top. Drop one of the two.

## Each step hands over to the next

The chain is: a character and a set -> a scene on the Stage -> a script -> a render -> the cut -> post ->
photoreal. At every stage the screen should say what this step is for and what the next one is. "Build
3D preview: about 20 seconds a scene, and it renders nothing" tells someone whether to press it;
"Build 3D preview" does not.

Destructive steps say what goes before they do it, and anything that takes work with it says what it is
taking - deleting an episode takes its renders, its film and its photoreal clips, and the confirm must
name them.

## Writing for a director

Plain words, no jargon, and the unit a person thinks in: "about 20 seconds a scene", "5.06 s at 16 fps",
"136 MB spare". Never a bare identifier where a sentence fits. The help text for a schema parameter lives
in `core/schema.py`, which is what the app prints under the control - fix it there and it is fixed in
every place it appears.
