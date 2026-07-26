"""The story skeleton IR.

This is the contract the whole pipeline hangs off. A StorySkeleton is a
genre-neutral description of what happens in a story: who does what, what it
causes, and which parts are load-bearing. Everything a genre owns — setting,
names, imagery, prose rhythm, the literal nature of the threat — is
deliberately absent.

The Field(description=...) strings are the real instructions. Gemini's
structured-output mode carries them into the response schema it is constrained
by, so tune those first — they land closer to the generation than the system
instruction does.
"""

from typing import List, Literal

from pydantic import BaseModel, Field

Outcome = Literal["success", "failure", "reversal", "reveal", "status_quo"]


class Role(BaseModel):
    """A character function mapped back to the name used in the source text."""

    slug: str = Field(
        description=(
            "Function slug in snake_case, describing what this character DOES "
            "in the plot, never who they are. Good: 'protagonist', 'gatekeeper', "
            "'betrayer', 'confidant', 'rival_claimant'. Bad: 'priya', 'the_old_man', "
            "'the_ghost', 'the_love_interest'."
        )
    )
    name: str = Field(
        description=(
            "The name or noun phrase the source text uses for this character, "
            "verbatim. This is the ONLY field in the whole skeleton allowed to "
            "contain a proper noun."
        )
    )


class Beat(BaseModel):
    """One causal unit of plot."""

    id: str = Field(
        description="Short stable id, b1, b2, b3... in the order the events occur in the story."
    )
    actor_role: str = Field(
        description=(
            "The slug of the role that performs this beat. Must match a slug in "
            "the skeleton's roles list."
        )
    )
    action: str = Field(
        description=(
            "What happens, in abstract genre-neutral language: an actor, a verb, "
            "and an object described by its function. "
            "Good: 'the confidant reveals the withheld information to the protagonist'. "
            "Bad: 'Ravi tells her about the letter he found in the attic'. "
            "Bad: 'a cold dread settles as the truth claws its way out'. "
            "No proper nouns. No sensory detail. No genre-loaded vocabulary. "
            "One sentence."
        )
    )
    causes: List[str] = Field(
        description=(
            "Ids of the beats this beat directly triggers, or an empty list. Be "
            "honest and sparse: only include an edge if removing THIS beat would "
            "mean the other beat no longer happens or no longer makes sense. Mere "
            "chronological succession is not causation. Most beats cause zero or "
            "one other beat."
        )
    )
    outcome: Outcome = Field(
        description=(
            "The structural function of this beat. "
            "'success' the actor gets what they were after; "
            "'failure' the actor is denied; "
            "'reversal' the situation inverts against the prior expectation; "
            "'reveal' information the actor lacked becomes available; "
            "'status_quo' the situation is established or unchanged."
        )
    )
    load_bearing: bool = Field(
        description=(
            "True only if deleting this beat would collapse the story — a later "
            "beat would become unmotivated, or the ending would change. Apply the "
            "test literally: delete the beat, then re-read the ending. If the "
            "ending still arrives, this is False. Be strict. Most stories have "
            "between 3 and 6 load-bearing beats, and if you have flagged more than "
            "half the beats in the story you are not applying the test. Connective "
            "tissue, atmosphere, reaction beats, and repeated escalations of the "
            "same pressure are not load-bearing."
        )
    )


class StorySkeleton(BaseModel):
    """The genre-neutral invariant core of a story."""

    logline: str = Field(
        description=(
            "One sentence naming roles by function, not by name, stating who "
            "wants what and what stands in the way. No proper nouns."
        )
    )
    roles: List[Role] = Field(
        description=(
            "Every character function that performs at least one beat, and no "
            "others. A character who is only mentioned, who is already dead, or "
            "who acts purely as an instrument of someone else's plan is not a "
            "role — attribute their action to the role that directs it. "
            "Institutions and offices count as one role only if they act."
        )
    )
    beats: List[Beat] = Field(
        description=(
            "The causal chain, in story order. "
            "SPLIT RULE — cut a new beat at exactly the points where one of these "
            "changes, and nowhere else: (a) who holds the advantage, (b) what the "
            "protagonist knows, (c) whose decision the story is waiting on. "
            "Apply it mechanically: two people talking is ONE beat if the advantage "
            "moves once, and TWO beats if it moves twice, no matter how long the "
            "scene is. Do not split a single transaction into setup, action, and "
            "reaction — fold a reaction into the beat that caused it unless the "
            "reaction itself changes one of (a), (b) or (c). Do not merge two "
            "separate changes of advantage just because they share a scene. "
            "Aim for 8 to 15 beats for a short story. Fewer than 6 usually means "
            "you have summarised rather than decomposed."
        )
    )

    # -- helpers used by the verifier; not part of the model output --

    @property
    def load_bearing_ids(self) -> List[str]:
        return [b.id for b in self.beats if b.load_bearing]

    @property
    def causal_edges(self) -> List[tuple]:
        """Every (source_id, target_id) pair, deduped, both endpoints existing."""
        known = {b.id for b in self.beats}
        seen = set()
        edges = []
        for beat in self.beats:
            for target in beat.causes:
                if target in known and target != beat.id and (beat.id, target) not in seen:
                    seen.add((beat.id, target))
                    edges.append((beat.id, target))
        return edges

    @property
    def role_names(self) -> List[str]:
        return [r.name for r in self.roles]

    def beat(self, beat_id: str):
        for b in self.beats:
            if b.id == beat_id:
                return b
        return None
