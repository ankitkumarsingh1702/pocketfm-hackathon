/**
 * Ready-made story library — pick one and showcase, no typing required.
 *
 * This is STATIC, bundled content. Nothing here is loaded from the knowledge
 * graph / Neo4j — that is deliberate. The seeded canon (ANDHERA) lives in the
 * DB for the Plot Hole demo; these are clean, self-contained shows a presenter
 * can drop into ANY lens (Audience Simulator, Cliffhanger Optimizer, Story Canon,
 * Writers Room, Genre Converter) to demonstrate the studio end-to-end.
 *
 * Each story is now a FULL 40-episode show. Episode 1 is a rich, hand-written
 * pilot; episodes 2–40 are authored season arcs living in `./stories/<id>.js`
 * as `{ title, scenes[] }` beats. `makeStory` assembles every episode's script
 * so that:
 *   - selecting a story + episode feeds THAT episode's text into any lens, and
 *   - the live canon extraction / plot-hole traversal changes per episode —
 *     proof the canon is built from the loaded input, not a fixed dataset.
 *
 * Scenes are split on `SCENE_DELIMITER` (matching the composer), so each episode
 * reads as a real multi-scene script full of named characters, places, clues,
 * and concrete facts. Every episode ends on an open beat — good raw material for
 * the Cliffhanger Optimizer to lift.
 */

import { SCENE_DELIMITER } from './constants'
import lastBusToRanikhet from './stories/lastBusToRanikhet'
import lettersToMeghna from './stories/lettersToMeghna'
import theColabaLedger from './stories/theColabaLedger'
import theMemoryTax from './stories/theMemoryTax'
import theNinthRing from './stories/theNinthRing'
import theWeaverOfHastinapur from './stories/theWeaverOfHastinapur'

/** @typedef {{n:number,label:string,title:string,text:string}} StoryEpisode */
/** @typedef {{id:string,title:string,genre:string,blurb:string,episode:string,text:string,episodes:StoryEpisode[]}} LibraryStory */

const JOIN = `\n${SCENE_DELIMITER}\n`

/** Build one episode's script text from bare scene strings ("Scene N: …"). */
function sceneText(scenes) {
  return scenes.map((s, i) => `Scene ${i + 1}: ${s}`).join(JOIN)
}

/**
 * Assemble a full multi-episode story.
 *   - Episode 1 uses the hand-written `pilot` script verbatim.
 *   - Episodes 2..N come from the imported season file (`{ title, scenes }`).
 * The flat `episode`/`text` fields mirror episode 1 so every existing consumer
 * (which reads `story.text` / `story.episode`) keeps working unchanged.
 *
 * @param {{id:string,title:string,genre:string,blurb:string,pilotTitle:string,pilot:string}} base
 * @param {{title:string,scenes:string[]}[]} rest
 * @returns {LibraryStory}
 */
function makeStory(base, rest) {
  const { pilot, pilotTitle, ...meta } = base
  const episodes = [
    { n: 1, label: 'Episode 1', title: pilotTitle, text: pilot },
    ...rest.map((e, i) => ({
      n: i + 2,
      label: `Episode ${i + 2}`,
      title: e.title,
      text: sceneText(e.scenes),
    })),
  ]
  return { ...meta, episodes, episode: episodes[0].label, text: episodes[0].text }
}

/** @type {LibraryStory[]} */
export const STORY_LIBRARY = [
  makeStory(
    {
      id: 'the-ninth-ring',
      title: 'The Ninth Ring',
      genre: 'Supernatural Thriller',
      blurb:
        'A night-shift telephone operator keeps getting calls from a number that was disconnected years ago.',
      pilotTitle: 'The Call on Line 9',
      pilot: `Scene 1: Ira Sohal takes the 11 p.m. shift at the Deonar telephone exchange, alone with two hundred sleeping switchboards. Her supervisor, Mr. Wagle, warns her never to answer line 9 — it was cut off in 2011.
---
Scene 2: At 1:14 a.m., line 9 rings. Against the rule, Ira plugs in. A child's voice says, "Didi, the water is rising again. Tell them we are still on the fourth floor."
---
Scene 3: Ira checks the ledger. Line 9 belonged to Flat 402, Neelkamal Building — a tower that collapsed in the 2011 monsoon. Eleven people drowned in the flooded stairwell.
---
Scene 4: She tells Wagle. He goes pale and admits he was the operator that night; he never patched the emergency call through in time. He has not slept a full night since.
---
Scene 5: The calls come nightly, always at 1:14 — the minute the water reached the fourth floor. Each night the child names one more person still "waiting" to be counted.
---
Scene 6: Ira cross-references the names against the official death list. The child names ten. The list has only nine. One girl, Roshni, age 7, was never recorded — her body never found, her family never informed.
---
Scene 7: Ira drives to the ruins of Neelkamal at dawn and finds a rusted nameplate: Flat 402, "Sohal." Her own surname. Her father never told her he once lived there — or why he left the city in 2011.
---
Scene 8: That night line 9 rings early, at 1:12. The child says, "You came. Now they can stop counting." Then, for the first time, she asks Ira a question: "Didi — do you remember me?" Ira's hand freezes on the switchboard.`,
    },
    theNinthRing,
  ),
  makeStory(
    {
      id: 'letters-to-meghna',
      title: 'Letters to Meghna',
      genre: 'Romance Drama',
      blurb:
        'Two strangers keep swapping notebooks on the same Mumbai local — until one of them stops showing up.',
      pilotTitle: 'Seat 3, The 8:47',
      pilot: `Scene 1: Every 8:47 Churchgate fast, Aarav Menon writes in a green notebook and "forgets" it on seat 3. Every evening it comes back with a stranger's reply in the margins, signed only "M."
---
Scene 2: For three months they argue about everything in ink — whether the sea is grey or blue, whether people can change, whether he should quit his father's accountancy firm to teach music.
---
Scene 3: M writes that she is getting married in November to a man her family chose. Aarav writes back a single line: "Then let me hear your voice once before you become a stranger for real."
---
Scene 4: They agree to meet at the Kala Ghoda coffee cart, Saturday, 5 p.m. Aarav wears the green shirt she once teased him about. She never comes.
---
Scene 5: The notebook returns Monday with one sentence in a different, shakier hand: "M is in Nair Hospital. I am her sister. She wanted you to have this." A pressed marigold falls out.
---
Scene 6: Aarav finds the ward. Meghna is recovering from a train-platform accident — she had run to make the 8:47 to reach him. She smiles: "You're taller than your handwriting."
---
Scene 7: Her mother forbids the visits. The wedding is in nine days. Meghna slips him the notebook one last time; the final page has only a train time and a date — the morning of her wedding.
---
Scene 8: On that morning Aarav stands on platform 3 with the green notebook and two tickets to nowhere in particular. The 8:47 pulls in. The doors open. He waits to see who steps off.`,
    },
    lettersToMeghna,
  ),
  makeStory(
    {
      id: 'the-colaba-ledger',
      title: 'The Colaba Ledger',
      genre: 'Crime / Detective',
      blurb:
        'A retired inspector is pulled back for one case: a locked-room death in a building he already investigated thirty years ago.',
      pilotTitle: 'The Locked Study',
      pilot: `Scene 1: Inspector Farhan Qureshi, three months into retirement, is called to Sea Breeze Mansion, Colaba. Antique dealer Vikram Rao is dead in his study — door bolted from inside, key still in the lock.
---
Scene 2: The room is untouched except for one thing: a nineteenth-century wall clock stopped at 3:40. Rao's wristwatch, however, stopped at 11:10. Two times, one body.
---
Scene 3: Farhan recognises the address. In 1994 he closed a "suicide" here — Rao's business partner, found the same way, same bolted study. He always believed it was murder but could never prove it.
---
Scene 4: The housekeeper, Lily D'Souza, swears no one entered after 10 p.m. But the tea tray holds two cups, both used. Rao lived alone and, everyone insists, never drank tea.
---
Scene 5: In the ledger on the desk, the last entry reads: "Bronze Nataraja — sold — buyer: R.M." The figurine's display stand is empty. Its glass case is locked, undisturbed, from the outside.
---
Scene 6: Farhan finds a hairline gap behind the bookshelf — a service passage the building plans don't show, connecting this study to the flat above. The flat above has been "vacant" since 1994.
---
Scene 7: The upstairs flat is furnished, lived-in, and full of stolen temple bronzes. On the mantel: a photograph of the 1994 victim, alive, older, smiling. He never died. He vanished — and he has been living one floor up ever since.
---
Scene 8: Farhan calls it in. As backup climbs the stairs, the vacant flat's door clicks shut from the inside, and the wall clock in Rao's study, untouched, quietly begins to tick again.`,
    },
    theColabaLedger,
  ),
  makeStory(
    {
      id: 'the-weaver-of-hastinapur',
      title: 'The Weaver of Hastinapur',
      genre: 'Mythology / Historical',
      blurb:
        "The blind queen's handmaiden weaves a tapestry that keeps predicting the war — until her thread runs out.",
      pilotTitle: 'The Hundredth Figure',
      pilot: `Scene 1: In the palace of Hastinapur, the handmaiden Suvarna weaves for the blind queen Gandhari. Her loom is said to be a gift from a wandering rishi: whatever it weaves at dawn comes true by dusk.
---
Scene 2: One morning the loom weaves, unbidden, a hundred brothers standing in a field of ash. Suvarna hides the cloth. By dusk, news arrives: the dice game has begun in the great hall.
---
Scene 3: Prince Yuyutsu, the one Kaurava born of a maid, seeks Suvarna out. He alone senses the war coming and asks the loom a forbidden question: which side will the just gods take?
---
Scene 4: The loom answers with a single figure — a charioteer with no weapon, holding only reins, glowing blue. Suvarna does not yet know his name is Krishna.
---
Scene 5: Gandhari discovers the tapestries. Rather than destroy them, she asks Suvarna to weave one last cloth: the fate of her hundred sons. Suvarna's hands shake; she has only enough indigo thread for ninety-nine figures.
---
Scene 6: She weaves through the night. At the ninety-ninth figure the indigo runs dry. The hundredth brother remains an empty outline — neither living nor dead in the cloth.
---
Scene 7: Yuyutsu realises the empty outline is himself: the son who will cross to the Pandava side and survive the war that consumes his brothers. He must choose before the cloth is finished for him.
---
Scene 8: At dawn, Suvarna threads her loom with a single strand of her own white hair to complete the hundredth figure. Before she can pass it through, a war conch sounds across the plain of Kurukshetra. Her hand hovers over the empty space.`,
    },
    theWeaverOfHastinapur,
  ),
  makeStory(
    {
      id: 'the-memory-tax',
      title: 'The Memory Tax',
      genre: 'Science Fiction',
      blurb:
        'In 2071, citizens pay their taxes in memories. An auditor discovers her own childhood was collected years ago.',
      pilotTitle: 'The Lien on a Childhood',
      pilot: `Scene 1: Bengaluru, 2071. The state no longer takes money — it takes memories, siphoned at the Revenue Spire and stored as light. Auditor Devika Rao is the best collector in Sector 12.
---
Scene 2: Her job: verify that citizens surrender genuine memories, not fabricated ones. A fake memory shimmers at the edges. Devika can spot a forgery in under four seconds.
---
Scene 3: A trembling old man, Prof. Iyer, is flagged for underpayment. He begs Devika not to take the last memory he owns of his late wife. Rules are rules; she reaches for the extractor.
---
Scene 4: Iyer whispers that he taught at the Revenue Spire before it was the Spire — back when it was an orphanage. He says he remembers her. Devika has no memories from before age nine, and never questioned why.
---
Scene 5: She pulls her own citizen file. There is a lien on her childhood: fourteen years of memories, collected in 2058, filed under "Involuntary State Contribution — Ward of the Spire."
---
Scene 6: Devika breaks protocol and enters the memory vault. Rows of light stretch to the ceiling. She finds a canister labelled with her own citizen ID, glowing faintly, still intact.
---
Scene 7: Iyer meets her in the vault; he has been hiding here for a decade, guarding the children's memories the state seized. He offers to return hers — but warns that reclaiming them will overwrite whoever she has become.
---
Scene 8: Devika holds the canister of her stolen childhood in one hand and her auditor's badge in the other. The vault alarm begins to rise. She has ninety seconds to decide which version of herself walks out.`,
    },
    theMemoryTax,
  ),
  makeStory(
    {
      id: 'last-bus-to-ranikhet',
      title: 'Last Bus to Ranikhet',
      genre: 'Mystery / Thriller',
      blurb:
        'Six strangers board the last night bus through the hills. By the first stop, one of them is already dead.',
      pilotTitle: 'Seven Boarded, Six Awake',
      pilot: `Scene 1: The 9:40 night service from Kathgodam to Ranikhet leaves with six passengers and one driver as the first snow begins. The road ahead is a single lane cut into the mountain.
---
Scene 2: The passengers: a nervous newlywed, Sameer; a doctor, Mrs. Bhatt; a monk who never speaks; a loud businessman, Taneja; a young woman, Kiran, clutching a locked steel box; and an old man in seat 1 who paid in coins.
---
Scene 3: At the first checkpoint, the conductor counts heads and finds seven boarded but only six awake. The old man in seat 1 is dead — and by the doctor's read, he has been dead for hours, long before the bus left.
---
Scene 4: The driver refuses to stop; the pass closes at midnight or they are stranded till spring. They agree to carry on with the body, doors locked against the cold.
---
Scene 5: Kiran's steel box is gone from her lap. She screams that it held her father's ashes — and the address of the only person who knows what happened in Ranikhet in 1998.
---
Scene 6: Taneja is found to have the box. He claims he took it "for safekeeping," but his hands are burned, and the ashes inside are still warm, as if recently disturbed.
---
Scene 7: The monk finally speaks, once: "The man in seat 1 boarded in 1998 too. That night, someone got off who should not have." He points, not at the body, but at Mrs. Bhatt.
---
Scene 8: The headlights catch a landslide across the pass. The driver brakes hard; the cabin light dies. When it flickers back, seat 1 is empty, the door is open to the snow, and Kiran is gone.`,
    },
    lastBusToRanikhet,
  ),
]

/** Fast lookup by id. */
export const STORY_BY_ID = Object.fromEntries(STORY_LIBRARY.map((s) => [s.id, s]))
