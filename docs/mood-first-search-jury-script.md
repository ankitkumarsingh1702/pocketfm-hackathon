# Mood-First Search — jury script

Everything here is meant to be **said out loud**. Read the blockquotes verbatim if you
like; they are written for speech, not for slides. Every technical claim is followed by
*why* it was built that way, because a technical jury is not impressed by what you built —
they want to know what you rejected.

Traced from the code and adversarially re-checked. Where a number appears, the file it
came from is named, so you can be challenged and open it.

---

## Before you speak — the one thing to internalise

**There are two complete engines behind one identical API. The deployed one is the
simpler one.**

`.github/workflows/_deploy-studio.yml:86` sets `MOOD_SIMPLE=1`, and
`backend/app/main.py:539` uses that flag to mount `app.mood.simple_engine` instead of
`app.mood.api`. So the live URL runs a keyword parser, hand-authored mood axes and plain
euclidean distance — **not** the LLM parser, embeddings, MMR, contraindication vocabulary
or reranker.

Everything in the un-deployed path is real, tested code. It just is not what a juror
clicks. **If you describe a mechanism, say which engine it lives in.** Getting this wrong
is the one way to look dishonest rather than rigorous.

| | Deployed (`MOOD_SIMPLE=1`) | Default in code |
|---|---|---|
| Parse | keyword substring match | 1 LLM call + keyword floor |
| Mood axes | 72 hand-typed numbers | LLM-fingerprinted per arc |
| Ranking | unweighted euclidean | axis .45 · embedding .30 · tags .20 · affinity ≤.22 |
| Diversity | one arc per collection | + MMR |
| Explanations | build-time templates | reranker writes score + line together |
| Safety | **distress gate, verbatim** | + 7-code contraindications + despair mask |
| Clarify question | not reachable | yes |
| Playable audio | **yes, 203 real tracks** | no (fields don't exist) |

**Timing — about 5 minutes**

| Segment | Time |
|---|---|
| The problem and the bet | 0:45 |
| Why the obvious build fails | 0:45 |
| Two engines, parse, three readings | 1:00 |
| Safety ordering, ranking, entry point | 1:05 |
| Live demo | 1:00 |
| Limits, unprompted, and close | 0:25 |

---

## 1 · Opening

> It is eleven at night. Somebody has had a bad day, they open a listening app, and they
> know exactly how they feel — and they have absolutely no idea what they want to hear.
> What the app shows them is a grid. Romance. Thriller. Comedy. Top Charts. Genre is a
> fact about the content; it says nothing about what the content will *do* to you. So they
> scroll for six minutes and close the app, or they play the same thing they always play.
>
> Our bet is one sentence. Let the person describe the feeling in their own words —
> English, Hinglish, whatever they actually type — and answer with **three readings** of
> that feeling instead of one ranked list. And for each reading, point at a specific place
> to start, not a title. That is the entire product. Everything after this is us defending
> that shape, and telling you where it does not hold up yet.

---

## 2 · Why the obvious build fails

This is the intellectual core. Slow down here.

> The obvious build is: embed the query, embed the description, take nearest neighbours.
> That fails, and it fails in a direction worse than merely being useless.
>
> Take our own test sentence — "something that feels like a rainy Sunday after
> heartbreak." Embed that against descriptions and the top result is the thing that is
> *about* rain and heartbreak. In our catalogue that is Adele, "Someone Like You."
> Near-perfect lexical and semantic overlap. And for somebody actually sitting in it at
> eleven at night, that is close to the worst thing you could hand them.
>
> That is the trap. A description tells you what happens; a query tells you how someone
> feels. Those live in different neighbourhoods. And it gets worse — both the embedding
> term and the tag-overlap term reward the topical match, so a naive system pushes you
> towards the wrong answer *confidently*.
>
> So we made the primary signal not text at all. Every arc carries nine numbers: valence,
> arousal, tension, weight, warmth, hope, catharsis, companionship, pace. Axis distance is
> weighted nought point four five. The embedding gets nought point three oh. That ordering
> is deliberate — if embeddings outvoted the axes, dragging a "heavier" control would
> return results that do not get heavier, and the control would be theatre.

---

## 3 · Walkthrough

### 3.1 Two engines, and which one is live

Say this early. It buys you credibility for everything after.

> One thing first, so nothing later surprises you. There are two complete engines behind
> one identical API contract, and an environment variable decides which mounts. The
> deployed service sets `MOOD_SIMPLE=1`, so what is on that URL is the simpler of the two
> — keyword parser, hand-authored axes, plain euclidean distance. The other engine, with
> the LLM parser, the embedding term, two safety layers and a reranker, is the default in
> code and what we run locally and in tests.
>
> We deployed the simple one deliberately. The LLM path cannot see a catalogue at all
> until an offline Vertex job has fingerprinted it into an index, and no deploy of ours
> has both credentials and somewhere to persist that index. So the choice was: a live URL
> serving real, playable songs, or a live URL serving about fifty invented series that
> look completely real. We took the first. From here on, every time I describe a mechanism
> I will tell you which engine it lives in.

**If asked — why not bake a prebuilt index into the container?**

> Because that makes the index a binary artefact nobody can review in a pull request, and
> the whole point of nine readable axes is that a human can argue with them. And the
> health endpoint admits which engine is live — it returns engine `simple`, source
> `curated-music-catalog`. I would rather that surface existed than not.

### 3.2 Parse — one model call to structure, with a floor under it

> On the LLM path, stage one is a single model call that turns the sentence into a
> structured query: situation, felt state, intensity, destination, tolerance, session
> length, language, things to avoid, a sparsity score and a distress flag. Structure
> rather than an embedding, because everything downstream needs *fields*. A slider can
> only nudge a target vector if a target vector exists. A filter can only be exact if the
> constraint is a field and not a phrase. A debug trace can only tell you why a shelf came
> back thin if the query is data.
>
> Underneath that call sits a deterministic keyword parser, and every failure path lands
> on it — no client, network error, quota, malformed JSON, the model improvising its own
> schema. That is not politeness. The parser is the first thing in the request. If it
> throws there is no degraded experience, there is a blank screen. And in production
> today, that keyword parser is the *only* parser.

**If asked — two decisions worth knowing:**

> First, if the model returns a confident destination on text our cheap heuristic reads as
> near-empty — "bore ho raha hoon" — we throw the destination away and ask one question
> instead. A confident answer to an empty sentence is the model inventing intent. The cost
> of guessing is a wrong shelf; the cost of asking is one tap.
>
> Second, a named loss or rupture floors intensity at nought point seven five, over
> whatever the model returned, because models read a flatly worded "my mother died last
> week" as low intensity. The sentence is calm. The situation is not.
>
> Honest note: clarify mode is not reachable on the deployed engine. It is implemented
> behind the flag, not something I can show you live.

### 3.3 Three readings, because the feeling really is ambiguous

> "After heartbreak" means at least three incompatible things. Sit in it. Keep me company.
> Get me out of here. A single ranked list forces the system to silently pick one and be
> wrong for two-thirds of listeners. So we return three shelves side by side and the
> listener's click *is* the disambiguation — no extra friction, and the shape itself shows
> we noticed the ambiguity rather than fumbled it.
>
> On the LLM path the three are chosen by a static table — not a model, not a scorer —
> because that decision is on the critical path and has to be explainable and instant. The
> three shelves are then built concurrently, one thread each, because each ends in a
> rerank call and three of those in sequence is the difference between a system that is
> thinking and one that is broken.
>
> Now the caveat I would rather give you than have you find: on this catalogue, with eight
> collections and four cards to a shelf, shelves overlap. On the hero query, "keep me
> company" and "lift me out of it" share three of four collections in the same order. The
> argument is stronger than this catalogue can currently demonstrate.

**If asked — show me three shelves that actually differ:**

> Type "heartbroken but I want to dance until I can sleep." That trips three separate
> keyword intents and returns Sit in it, Turn it up, and Wind down. The first two then
> share nothing. The third still shares two of four, because three shelves times four
> cards is twelve slots over eight collections — somebody has to repeat. That is
> arithmetic about corpus size, not a ranking defect.

### 3.4 Safety runs before scoring, never after

> Distress detection is twelve regular expressions over the lowercased text, English and
> romanised Hinglish, and nothing else. No model, no embedding, no score. That is the one
> decision in this system we refused to make probabilistic, because the two error
> directions are not symmetric. A false positive costs somebody one gentle screen they tap
> past. A false negative routes somebody in crisis into a shelf of the heaviest content we
> have. The model may *raise* that flag and never lower it — the line is literally keyword
> OR model — so the worst a bad model can do is add a false positive.
>
> On a distress query the retrieval engine is never called at all. We return before
> search, with a fixed message and two real Indian helplines that are string constants on
> the server, because a model must not paraphrase a phone number. We also do not ask a
> clarifying question there; "what would you like this to do for you" is the wrong
> sentence to put in front of someone in crisis. And that gate is the one thing the
> deployed engine reuses **verbatim** — same function, same helplines.

**If asked — the rest of the safety design:**

> Two contraindication layers, both boolean masks that finish *before* anything is scored.
> Layer one compiles the fingerprinter's free prose into a closed seven-code vocabulary at
> index time, so the query path only does a set intersection — free prose in for the
> author, exact codes out for the matcher. Layer two is structural: if the listener is in
> a raw state, anything simultaneously hopeless *and* bleak *and* heavy is masked even
> when nobody wrote a contraindication for it.
>
> We needed the second layer because our own fixture proves the gap — three trap arcs are
> equally harmful to a grieving listener and only one happened to write the word "grief",
> so codes catch one and the axis rule catches the other two.
>
> Ordering is the guarantee. If a contraindicated item reaches the reranker, a persuasive
> sentence can talk it back in — and an LLM scoring it nine out of ten is not a bug you
> can see.

### 3.5 Ranking — nine axes, the arc as the unit, no vector database

> On the LLM path the score is four terms — axis distance nought four five, cosine nought
> three oh, tag overlap nought two oh, listening affinity nought one two — divided by the
> weight sum so it stays a real zero-to-one quantity.
>
> Two things about that. The cosine is computed over a written vibe sentence plus sensory
> tags and *never* over a synopsis, because the synopsis is precisely the text that
> produces the topical trap. And affinity is capped at nought point two two, scaled up
> only when the query is thin — history should matter most on "bore ho raha hoon", where
> it is the only evidence in the room, and should never own a query where the person has
> just told us how they feel. Past about nought point two five this stops being mood
> search with a personalisation nudge and becomes a collaborative filter wearing mood
> search as a costume.
>
> The unit we index and rank is the **arc**, never the collection, because a fifty-track
> collection is warm in one stretch and brutal in another, and a collection-level mood is
> an average of incompatible things.
>
> And the index is brute-force numpy, not a vector database. At this size the whole thing
> fits in cache — but the stronger reason is filters. Ours are axis-range predicates
> applied before search. In numpy that is a boolean mask a test can assert exactly; in a
> vector DB it becomes a prefilter string that can silently mis-parse. A silently empty
> filter is exactly the bug that ships.

**If asked — what the deployed ranker actually does:**

> Much simpler, and its own docstring says it is not the LLM pipeline and does not pretend
> to be. Eight hand-typed nine-axis vectors, unweighted euclidean distance, one arc per
> collection per shelf, up to four cards, and a hard mask on anything the selected
> listener finished or disliked.
>
> It has a flatness I should name: each shelf's target is its reference collection's own
> vector, so that collection's first arc sits at distance zero and always wins rank one.
> Deep entry points only appear at ranks two to four, and about ten of the twenty-five
> arcs never surface in the default flow. Small catalogue, blunt ranker.

### 3.6 The entry point — the part to take away

> The last deterministic step does not return a title, it returns a doorway: an arc, a
> track number, and a label. "Start at track ten — what it added up to." A fifty-track
> collection is not an answer to "I feel like this" — it is a commitment decision wearing
> the costume of a recommendation.
>
> On the LLM path, if there is a near-equal match earlier in the same collection we will
> swap to it — but only if the entry is already deeper than track twelve, only if the mood
> cost is under nought point oh one five, and only if it saves at least thirty-five
> percent of the track number.
>
> That tolerance used to be nought point oh four. At nought point oh four the swap fired
> on essentially every result and collapsed every entry point back to track one, which
> silently deletes the entire proposition and turns arc-level indexing into an expensive
> way to recommend collections. Our tests passed the whole time, because the assertion was
> "returns a valid episode." **Assert the product behaviour, not that the field is
> populated** — that is the lesson from this codebase I would actually keep.
>
> And the doorway survives into the UI: the track-list fetch defaults to the entry point,
> not track one. Everything earlier is one button away. It is just not where we drop you.

### 3.7 Playback — real tracks, and what happens when a rights holder says no

> Playback is real, and I want to keep two sentences apart that people usually collapse.
> **Nothing in this build listens to a waveform in order to score anything. But the
> listener does hear the actual track.**
>
> All two hundred and three tracks carry a real YouTube watch URL, and the player drives
> the YouTube IFrame Player API rather than a bare iframe — specifically because a bare
> iframe gives you no lifecycle events, so you cannot tell a playing video from a dead
> frame. With the API we get error codes we can act on. One-oh-one and one-fifty mean the
> rights holder disabled embedding, the one thing a web page genuinely cannot work around.
> Two, five and one hundred mean invalid, removed or private. In both cases we hide the
> frame and put up a "Play on YouTube" button with a sentence explaining why, so nobody
> stares at a black box in front of a jury. One shared player per result list, so a second
> Play cannot leave two tracks audible.

**If asked — the two failure modes:**

> First, we fetch the IFrame API script from youtube.com at runtime. If the venue network
> blocks or captive-portals YouTube, that script never loads and the promise never
> rejects, so the player sits in loading forever. The honest answer to "what if the wifi
> is bad" is that inline playback dies and the link out is all that is left.
>
> Second, we call play inside the ready callback, and because the player is constructed
> after an async script load, browsers can drop the user-gesture attribution — so the
> first tap may not start audio.
>
> On verification: all two hundred and three URLs were checked against YouTube's oEmbed
> endpoint. Two hundred and three of two hundred and three come back live with titles
> matching ours exactly, which proves they exist and that our metadata is the platform's
> own. It does not prove every one permits embedding — that is what those error codes are
> for.

### 3.8 Refine — the sliders, and the bug that made two of them do nothing

> After a mood result nobody re-types the sentence. They want heavier, lighter, slower,
> warmer. So each shelf carries nudge chips, and a tap sends the **raw slider position**
> along with that shelf's own target axes. Raw position, not pre-nudged axes — that is
> load-bearing: the engine needs to know which axis you steered so it can grant that axis
> room against the destination's own filter bounds.
>
> We shipped the other version once. Sliders steer exactly the axes the destination filter
> clamps, so pulling "faster" on a sit-with shelf moved the target into a region the
> filter had already emptied. Two individually correct designs cancelling into a dead
> feature, and not one unit test noticed.
>
> The second fix was reweighting. Across a drag the query text never changes, so the
> embedding and tag terms are frozen — about half the score — and a full drag was moving
> only twenty-two percent of what separated the candidates. On refine, axis weight goes
> from nought four five to nought seven eight, because once you have dragged something you
> have stated a preference in axis terms your sentence never contained. That is strictly
> better evidence, so it should carry the ranking.
>
> And refine gets its own reranker, hardcoded to the heuristic, because the shared one
> becomes an LLM whenever credentials resolve — which is to say, exactly on demo day.

**If asked — and this is weakest on the engine you will click:**

> Production moves the target by nought point two per full drag against eight widely
> spaced hand-typed vectors. We measured it: thirty-five out of a hundred and fifty single
> full drags changed the shelf at all, and the top card never moved. All five sliders at
> maximum on the sit-with shelf returned the identical four collections in identical
> order.
>
> Also, a failed nudge and a nudge that changed nothing look the same on screen, because
> we deliberately leave the shelf untouched on error rather than blank results somebody is
> reading. And on the un-deployed path one of the four composite sliders, "warmer", still
> shows zero churn on the hero query — there is a behavioural test failing on exactly that
> right now. Same bug class, different engine. First thing I would fix.

### 3.9 Where the content came from

Expect the hardest questions here.

> We cut the audio pipeline, which left the catalogue metadata-only — and audio-fiction
> metadata in the right emotional register does not exist to hand-collect. LibriVox is
> real human prose, but it is Victorian and classical; nobody's rainy Sunday after
> heartbreak is answered by Boethius.
>
> So the corpus is one public YouTube playlist, "Top Songs of the Decade, 2010 to 2019."
> We scraped two hundred and ten items with no API key and no third-party library, dropped
> seven because the playlist owner had mixed in Japan travel vlogs — a travel vlog has no
> mood in the sense this index uses, so it would fingerprint as noise and could turn up on
> any shelf — and kept two hundred and three songs. Every title, duration and URL is
> carried through unmodified. We never let a model invent a track title, because a
> plausible wrong title is worse than an obvious stub: it reads fine, it is wrong, and in
> the interface it is indistinguishable from a real one.
>
> The actual curation is a two-hundred-and-ten-token array, one letter per playlist
> position, assigning each track to one of eight mood collections. That array is the human
> judgement in this system and the only place mood enters the data. And it is
> reproducible — the build script is deterministic, so changing one letter and re-running
> shows exactly what moved, as a diff.

**If asked — what you will *not* claim:**

> The arc boundaries. The arc count, labels and summaries are human; the cut points are
> arithmetic — a proportional split of each collection's track count by a small hand-set
> weight vector. Our own code concedes the cost: even splits are not where the emotional
> turns are, so entry points land *near* the right track rather than on it. And tracks
> inside a collection are in original playlist order, so which arc a song lands in is
> partly coincidence. Adele's "Someone Like You" is the first track of an arc labelled
> "letting it settle" because of where it sat in the playlist. Anyone who opens the JSON
> finds that in a minute, so I would rather say it first.
>
> One more: the artist line comes from the uploading channel, and for twenty-three of two
> hundred and three that is a label rather than the artist — "We Are Young" is credited to
> Fueled By Ramen. Real metadata, imperfectly attributed.

---

## 4 · Numbers, phrased for speech

| Number | Say it like this |
|---|---|
| 203 / 8 / 25 | "Two hundred and three real songs, eight mood collections, twenty-five arcs. Thirteen and a half hours. That is small — a curated demo corpus, not catalogue scale." |
| 210 decisions | "Two hundred and ten hand-made decisions, one per playlist position. That array *is* the curation." |
| 7 dropped | "Seven items dropped, all seven Japan travel vlogs the owner had mixed in. A vlog has no mood in the sense this index uses." |
| 72 constants | "Seventy-two hand-typed numbers — eight collections times nine axes. No model produced one of them, which is how we sidestep grading our own homework." |
| .45 vs .30 | "Axis distance nought four five; the embedding nought three oh. That ordering is what makes the sliders honest instead of decorative." |
| .78 on refine | "On a refine, axis weight goes to nought seven eight, because half the score is frozen across a drag." |
| .22 ceiling | "History is capped at nought point two two. Past nought point two five this becomes a collaborative filter in a costume." |
| 12 regexes | "Twelve regular expressions. That is the whole distress check, and the one decision we refused to make probabilistic." |
| .015 from .04 | "The entry-swap tolerance is nought oh one five. It was nought oh four, and at nought oh four every entry point collapsed to track one — while every test kept passing." |
| 203/203 live | "All two hundred and three URLs came back live from oEmbed with titles matching ours. That proves they exist. It does not prove all of them allow embedding." |
| 25 vs 203 calls | "Fingerprinting this catalogue is twenty-five calls at arc level against two hundred and three at track level. To be clear — we have not run that job on this data." |
| 3 of 8 masked | "Picking a listener hides three of eight collections — two finished, one disliked. Hard mask before ranking, not a penalty." |

---

## 5 · Limits — say these unprompted

Volunteering these reads as competence. Waiting to be caught does not.

> **Nothing in this build listens to audio.** That is the single overclaim a jury would be
> right to probe, so I will make it myself. The original plan had speech recognition,
> prosody and an audio embedding model, and we cut all three. On the deployed engine the
> axes are seventy-two hand-typed constants; on the other, one text call over a written
> summary. The audio-verified flag is hardcoded false everywhere by design. The listener
> hears the real track; we do not analyse it. Two different sentences, kept apart.

> **What is deployed is the simpler engine**, so several things I described are not running
> on the URL you will click: no embedding term, no MMR, no contraindication vocabulary, no
> despair mask, no reranker, no relax ladder, no language or duration filter, no clarifying
> question. What survives is the distress gate, imported verbatim, and the doorway
> calculation. Two consequences: the refine sliders are largely inert in production, and
> Devanagari self-harm text is not detected at all, because all twelve patterns are
> latin-script and there is no model in production to widen recall. That is a gap, not a
> mitigation.

> **On the data, three things are authored rather than discovered.** The grouping into eight
> collections is human judgement — I claim that as a feature. The arc cut points are
> arithmetic, not marked emotional turns. And tracks are in original playlist order, so
> which arc a song falls into is partly coincidence. There is also one collection whose
> synopsis says instrumental and ambient and whose contents include a Snoop Dogg track —
> it is where the twelve songs that fit nowhere went, and it is what our sleep starter
> points at, so it is the most fragile thing in the data.

> **Every metric our eval harness produces was computed over a synthetic fixture** whose own
> docstring says "test fixture, not the catalogue." Not one number was computed over these
> two hundred and three songs, so I will not quote lift or coverage at you as a result
> about this catalogue.

> **Three things on the demo surface.** The latency badge is a hardcoded constant in the
> deployed engine, not a measurement — I should delete it rather than explain it. The
> comparison panel claims a keyword baseline, and on this engine it is a stub returning our
> own ranking with a different label, so both columns show the same collections. And
> session state is an in-process dictionary with no eviction on a deploy that runs up to
> five instances, so a nudge after a container restart can silently lose the listener's
> mask.

---

## 6 · Close

> What makes this worth continuing is not the catalogue — it is that the nine-axis vector
> is the durable artefact. The text fingerprinter is one function. Swapping it for
> something that genuinely listens to the audio changes that one function and nothing
> downstream: the masks, the arc granularity, the doorway, the refine loop all stay exactly
> as they are. That is why cutting the audio stage was affordable.
>
> At real scale the number I would want to move is not recommendation accuracy, it is where
> people stop. Today a listener who feels a specific way gets pointed at episode one of a
> two-hundred-episode show. The doorway is a fix for that, and it is measurable —
> completion rate on an arc-level entry against a collection-level entry, same content,
> split by listener.
>
> And concretely, the next commit I would write is hand-marked arc boundaries for these
> eight collections. Right now the cut points are arithmetic, and our own code already
> names that as the single highest-value field to curate by hand. That is a day of work,
> and it makes every entry label on every card true rather than approximately true.

---

## 7 · Q&A

**Isn't this just RAG over descriptions with extra steps?**
> Partly — let me tell you which part is not. The nine axes are the primary signal at
> nought four five against the embedding's nought three oh. The embedding is computed over
> a written vibe sentence and sensory tags, never a synopsis, because the synopsis is the
> text that produces the topical trap. And the unit indexed is the arc, not the item. On
> the deployed engine there is no embedding at all. So "RAG over synopses" is the thing we
> specifically designed against. Whether we have conclusively escaped it at two hundred
> and three tracks — no. The honest evidence would be an eval over this catalogue, which
> we have not run.

**Does anything actually listen to the audio?**
> No. Nothing here has been near an audio decoder. The audio-verified flag is hardcoded
> false by design, and the original ASR-plus-prosody pipeline was cut. Cutting it removed
> our prepared answer to your question, which is why the replacement had to be
> architectural rather than a demo trick. The listener hears the real track. We do not
> analyse it.

**Your numbers — what were they measured on?**
> The constants are real and every one cites a file and a line, so check any of them. The
> metrics are a different matter: all computed over a synthetic fixture of about fifty
> invented series, and that fixture's docstring says "not the catalogue." Nothing was
> computed over the two hundred and three songs. What I do have is behavioural regression
> tests — and one is currently failing, on the slider bug.

**Why numpy instead of a vector database?**
> At twenty-five arcs, and even a few hundred, the index fits in cache and a full scan is
> microseconds — under the noise floor of anything that follows. The stronger reason is
> filters: ours are axis-range predicates applied before search. In numpy that is a
> boolean mask a test can assert; in a vector DB it becomes a prefilter expression that can
> silently mis-parse, and a silently empty filter is the bug that ships and nobody notices.
> We overrode our own design document on this, and left an unused adapter so it is a
> decision with a migration path.

**Why are the axes hand-authored rather than model-derived?**
> Two reasons. Deployability: the model path cannot see a catalogue until an offline
> fingerprinting job has run, and we did not have that in CI, so a curated catalogue would
> have been invisible in production. And self-dealing: if a model writes the description
> and a model derives the vector, every metric becomes decorative — and the failure is
> invisible, because the numbers go up, not down. A human assigning both the tracks and the
> axes sidesteps that rather than relying on a denylist. The cost is that mood resolution
> is per collection, which is why there is a small deterministic per-arc drift on top —
> otherwise every entry point collapses to track one.

**Two hundred pop songs from a playlist. How is that a catalogue?**
> It is not, and I would call it a curated demo corpus. What is real: every track, title,
> duration and URL, all playable, all verified live. What is authored: the grouping, the
> arc labels, the synopses. Our own build script says treat this as demo data, not the eval
> set. And the precise version of the provenance claim: the gate is satisfied in spirit
> because no model wrote the synopses and no model derived the axes — a human did both —
> not because the gate verified anything. It only checks a string against a denylist.

**What if I type in Hindi?**
> On the deployed engine, nothing good and nothing loud. There is no language filter in
> production, so you get English pop ranked by whatever keywords matched, falling back to
> three default readings. On the other engine language is an exact-match hard filter the
> relax ladder never widens — which once emptied every shelf for a Hindi-tagged catalogue,
> silently, returning a polite clarifying question forever with no error anywhere. That is
> why language now defaults to no preference: writing in Hinglish is how people talk, not
> evidence of a language requirement. Also worth admitting — our crisis message is in
> romanised Hindi while all two hundred and three tracks are English. A mismatch I have not
> resolved.

**Self-harm intent in Devanagari?**
> Undetected in production, and I have verified that end to end. All twelve patterns are
> latin-script. On the other engine a live model can widen recall on top of the regexes,
> because it may raise the flag and never lower it — but production has no model, so there
> is nothing to widen it. Even in English the list is narrow: "I want to die" fires, "I
> don't want to live anymore" does not. A gap, not a mitigation, and the first safety item
> on my list.

**The panel says it compares against genre search. Is that real?**
> On the deployed engine, no — and I will say that before you click it. The genuine keyword
> baseline exists, a proper lexical index with IDF and length normalisation, deliberately
> not crippled, and it is wired only to the un-deployed engine. The simple engine stubbed
> the endpoint so the panel would not four-oh-four, and what it returns is our own ranking
> relabelled. Both columns show the same collections. I would rather disable the panel than
> leave it there.

**Who wrote the one-line explanation on each card?**
> On the deployed engine, we did, at build time — a per-collection vibe line joined to the
> arc summary, so it is the same sentence for that arc on every query. On the other engine
> the reranker returns the score and the explanation in a single call, and that is
> deliberate rather than a cost saving: a separate explanation pass writes a justification
> for a ranking it did not make, and will confabulate something plausible. Forcing one act
> of judgement to commit to both makes bad rankings visible — a weak reason is a reliable
> tell that the retrieval underneath was weak.

**Show me the safety layer blocking a result.**
> On the live URL I cannot, and that is the honest answer. The distress gate is live and you
> can trigger it now — two real helplines, retrieval never called, so there is no ranked
> list to leak. But the seven-code vocabulary, the despair mask and the trap arcs live on
> the un-deployed engine, and the traps are in the synthetic fixture production never
> imports. So what is live is the gate that matters most, and none of the fine-grained
> blocking. The weak point in that design: layer two only activates once layer one has
> identified the listener as raw, so a listener-side detection miss switches both off at
> once. It is a backstop against missing annotations, not a general backstop.

**Why ship the weaker engine to production?**
> I would argue it is the weaker ranker and the stronger demo. The alternative was a live
> URL serving fifty invented series with invented titles a juror cannot distinguish from
> real ones — and every Play button dead, because the fields carrying a playable URL only
> exist in the deployed engine. Convincing fake data is the worst option available. And it
> is a flag, not a deletion: the model path is intact, tested, one environment variable
> away. The health endpoint tells you which one you are talking to, which is the thing I
> insisted on.

---

## 8 · Demo click path

| # | Do this | Say while doing it |
|---|---|---|
| 1 | Click the **Mood Search** tab | "Notice nothing loaded — the panel mounted at app start and we only un-hide it. Cost of that choice: a track left playing keeps playing when you leave the tab, so I'll close the player before moving on." |
| 2 | Point at the label, the line, the eight cards | "One box: how do you want this to feel. The line under it is the constraint we hold ourselves to — no genres, no browse grid. And those eight are sentences, not titles. The moment we put a grid of shows there, we've rebuilt the thing we're replacing." |
| 3 | Tap the hero starter | "Three shelves, one round trip. Three incompatible readings of the same sentence, and your click is the disambiguation. Getting ahead of the obvious objection: shelves two and three share three of four collections here. Eight collections and four cards don't leave room. That's the corpus, not the ranking." |
| 4 | Point at the red pills on cards **2 and 3** | "This is the claim — not a title, a doorway. I'm pointing at these specific cards because the top card says start from the beginning: on this engine each shelf's target is its own reference collection, so that collection's first arc sits at distance zero and always wins rank one." |
| 5 | Press **Play** on card 2 | "The real track, through YouTube's player API rather than a bare iframe, because a bare iframe gives us no error codes to act on. One player for the whole list. If the first tap doesn't start audio, tap the video — we lose gesture attribution because the player is built after an async script load." |
| 6 | Press the red entry pill | "The whole surface becomes the doorway, and the list opens at track ten of twenty-six, not track one. Tracks one to nine are one button away above it — not hidden, just not where we drop you." |
| 7 | Play a row, then **Back to shelves** | "Back restores the exact previous state — same query, same listener, same three shelves, no refetch — because the mode is state, not a route. If these were routes, going back would re-ask a question you'd already answered." |
| 8 | Press **Heavier** under Sit in it | "Only that shelf dims; the other two keep their data, because a nudge shouldn't look like a fresh search. Be warned: on this engine most single drags don't move anything, and a failed nudge looks identical to one that changed nothing. If it doesn't move, I'll say so." |
| 9 | Choose a listener | "Same query, re-ranked for a different person. Two collections just vanished — that's a hard mask, not a scoring nudge; three of eight are hidden for her. A copy bug I owe you: the card says three already-finished, but it's two finished and one disliked. And completion rate and language read the same for all ten, so don't take those as per-listener modelling. These are fixtures." |
| 10 | Type a distress phrase | "No shelves, no clarifying question — and the demo controls above didn't get hidden, they never render; it's an early return. Two real helplines, retrieval never called, so there's no ranked list to leak. This is the one thing the deployed engine reuses verbatim. It's also twelve latin-script regexes, so I'll tell you now: the same sentence in Devanagari does not fire." |
| 11 | Comparison panel — **skip, or explain** | "I'll tell you what this is rather than let you find out. On this engine the baseline column is a stub — our own ranking relabelled — so both columns show the same collections, and the trace beside it is a stub too. The real keyword baseline is wired to the other engine. Not evidence today." |
| 12 | **See the full flow**, then close the player | "Five diagrams, and the constants table cites a file and line for every number. Two caveats: the diagrams describe the un-deployed engine, so read them as the design, not this URL; and mermaid is bundled from our own origin, so this part works with no internet — unlike the audio player. Now let me close the player, because we hide panels rather than unmount them." |

---

## 9 · Do not say

- ❌ "Mood comes from the voice" / any implication of audio analysis. **Nothing listens.**
- ❌ Any lift, coverage or match-rate figure "for this catalogue." Those came from the synthetic fixture.
- ❌ "The LLM parses your sentence" while demoing the live URL. It does not — `MOOD_SIMPLE=1`.
- ❌ "The baseline panel proves we beat genre search." It is a stub on this engine.
- ❌ Quoting the latency badge. It is a hardcoded constant in the deployed engine.
