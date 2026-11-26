// What every part of CastForge is for, how to use it, and what the next step is.
//
// One place, because the same explanation belongs on the page, in the tooltip and in the help panel, and
// three copies of it drift apart within a week. Written for someone making a film, not for someone who
// has read the code: what this step DOES, what to press, and where it hands over.
export interface Guide {
  title: string;
  /** one sentence: what this is for */
  what: string;
  /** what to actually do, in order */
  how: string[];
  /** what this hands over to, and where that is */
  next?: {says: string; go?: string};
  /** the thing people get wrong here */
  mind?: string;
}

export const GUIDES: Record<string, Guide> = {
  overview: {
    title: "Making a film, start to finish",
    what: "Six steps: a story, a cast, the places it happens, a storyboard, the render, and the finished film.",
    how: [
      "Build the people on Characters - from a photograph, or designed from nothing.",
      "Build the places on Sets: one picture becomes a 3D room you can walk people around.",
      "Make an episode, put a scene on a set, and put your cast in it.",
      "Write what happens, render it, and finish it.",
    ],
    next: {says: "Open Episodes and make a scene", go: "episodes"},
    mind: "Every step saves into the movie folder, so you can stop anywhere and come back.",
  },
  characters: {
    title: "The cast",
    what: "A character is a body, a face, a costume and a rig that can act - built once and used in every scene.",
    how: [
      "Add from a photograph for a likeness, or design one from nothing.",
      "Shape the face and body with the sliders; the figure beside them moves as you go.",
      "Dress them, then build. A build takes a few minutes and makes the .blend every scene loads.",
    ],
    next: {says: "Put them in a scene", go: "episodes"},
    mind: "A design can ask for two things that cannot both be built - a one-piece suit and a long coat, say. It will tell you which to drop rather than quietly make one of them.",
  },
  sets: {
    title: "The places",
    what: "A set is one picture of an empty room turned into a 3D space: depth, a floor people can walk on, and the things standing in it.",
    how: [
      "Add a picture of the place with nobody in it.",
      "Mark what stands in the room - a table, a chair, a door - so people walk round them instead of through.",
      "Build it. Every scene on that set then reads the same geometry.",
    ],
    next: {says: "Put a scene in it", go: "episodes"},
    mind: "The picture should have no people in it: anyone in the photograph becomes part of the wall.",
  },
  results: {
    title: "Everything this movie has made",
    what: "The films, the graded cuts, the photoreal clips and the storyboards, newest first.",
    how: [
      "Play any of them here.",
      "Save pulls the file out to wherever you want it.",
      "Open takes you to the episode it came from.",
    ],
    mind: "Deleting an episode takes its results with it - they live in the episode's own folder.",
  },
  scenes: {
    title: "The scenes of this episode",
    what: "An episode is a list of scenes in the order they play. This is where you choose which one you are working on, and what it is set in.",
    how: [
      "Click a scene to work on it.",
      "Click a set, or drag one onto a scene, to put that scene in it.",
      "Add a scene when the story moves somewhere new.",
    ],
    next: {says: "Put someone in it on the Stage below"},
    mind: "Putting a scene on a built set brings its picture, its depth and everything standing in it. You do not choose a background as well.",
  },
  stage: {
    title: "The stage",
    what: "Who is in this scene, where each of them starts, and how they look and sound.",
    how: [
      "Click a face to put that person in the scene.",
      "Drag them on the floor to where they start. The camera is at the bottom, looking up the page.",
      "With someone selected, set which way they face, their voice, their expression and their stance.",
    ],
    next: {says: "Write what happens, on the Script tab"},
    mind: "The floor is seen from above: x runs right (red), y runs away from the camera (green).",
  },
  script: {
    title: "What happens, in order",
    what: "Every line spoken and every action taken, from the top of the scene to the bottom.",
    how: [
      "Press a card in 'Add what happens next' to put a step at the end.",
      "A line is spoken in that character's voice - press Hear it before you commit.",
      "Walks, looks and camera moves are actions: each one asks only for what it needs.",
    ],
    next: {says: "See it move in the 3D editor"},
    mind: "A thought is heard with the mouth closed; a line is spoken. The render and the photoreal pass both rely on that difference.",
  },
  editor3d: {
    title: "The scene in 3D",
    what: "The scene as a space you can walk around, scrub and look through the lens of - before spending a render on it.",
    how: [
      "Press Build 3D preview once: about twenty seconds a scene, and it renders nothing.",
      "Drag the discs to move where people start, and the rings to move where they walk to.",
      "Press Through the lens to see the shot the render will actually make.",
    ],
    next: {says: "Render it, on the Output tab"},
    mind: "Rendering makes the film; this makes the thing you can move people around in. They are different buttons.",
  },
  cut: {
    title: "The cut",
    what: "Every scene in the order it plays, and the transition that joins each pair.",
    how: [
      "Drag a scene to move it in the cut.",
      "Click between two scenes to choose how the second one begins.",
      "Below, the colour grade, grain and subtitles for the whole episode.",
    ],
    next: {says: "Finish it, on the Output tab"},
    mind: "These are applied after rendering, so changing them never costs another render - use Finish only.",
  },
  output: {
    title: "The finished thing",
    what: "The rendered episode, the graded cut, the photoreal clips, and what this episode is holding on disk.",
    how: [
      "Render makes the film. Finish only re-applies colour and captions without re-rendering.",
      "Space on disk clears what can be made again - Blender's backups cost nothing to lose.",
      "Prepare for YouTube checks the film and writes a publish folder.",
    ],
    next: {says: "See everything this movie has made", go: "results"},
  },
  suite: {
    title: "The three tools",
    what: "The graphic novel designs the cast, CastForge builds and films them, forgefilms finishes the picture.",
    how: [
      "Give it a body builds a 3D character from a face the novel already designed.",
      "Hand to post cuts and masters the episode: colour, crossfades, captions, -16 LUFS.",
      "Make it real turns each shot into a photograph and animates it.",
    ],
    mind: "Make it real generates nothing by itself - it shows you every clip and its prompt first, so you can read them before spending a GPU.",
  },
  space: {
    title: "Space on disk",
    what: "What this episode is holding, sorted by what it would cost to get back.",
    how: [
      "Tidy up takes Blender's own backup files. Nothing ever reads them.",
      "The next one also takes 3D previews and check renders: a button brings each back.",
      "The last also takes the scene files and built sets: only a full re-render brings those back.",
    ],
    mind: "The film, its sound, its timings and the scene it was written from are never touched, at any depth.",
  },
  voices: {
    title: "Voices",
    what: "Forty-one voices, in seven languages, that you listen to before choosing.",
    how: [
      "Filter by language or by women and men.",
      "Press play to hear the actual line this character says.",
      "Click a voice to give it to them.",
    ],
    mind: "A voice effect - radio, phone, megaphone - is set on the line, not on the person.",
  },
  photoreal: {
    title: "Photoreal clips",
    what: "The same shots, photographed: each still is re-imagined by a photoreal model and then animated.",
    how: [
      "The cut is already there - each clip is one shot the director made.",
      "Every prompt is read off the scene: who is on screen, what they wear, the light, and whether they are speaking or thinking.",
      "It runs on the rented GPU. The clips come back into the episode's own folder.",
    ],
    mind: "Image-to-video animates the picture it is given; it does not restyle it. That is why the still is made photographic first.",
  },
};
