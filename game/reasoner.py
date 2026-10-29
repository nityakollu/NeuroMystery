"""
Symbolic reasoning over the mystery.
 
This module never changes game state. It answers three questions:
 
1. Which facts does the player's evidence support?  (evidence closure)
2. Does a character's claim conflict with that evidence?  (contradiction detection)
3. Why does the conflict exist?  (classification: lie / false belief / apparent)
 
Facts are boolean propositions identified by id (see "facts" in mystery.json).
  - world_truth          -> what actually happened (hidden from player and LLM)
  - character knows      -> facts the character knows to be true or false
  - character believes   -> facts the character holds, which may be wrong
  - claim asserts        -> what the character told the player
  - claim based_on       -> assumptions the claim relies on (e.g. the clock was right)
  - clue supports        -> facts a piece of physical evidence points to
  - inferences           -> rules that derive new facts from known ones
"""
 
 
# Contradiction kinds
LIE = "lie"                    # character knows the truth and said the opposite
FALSE_BELIEF = "false_belief"  # character sincerely believes something untrue
APPARENT = "apparent"          # the claim is actually true; the evidence misleads
UNEXPLAINED = "unexplained"    # the data does not say why (authoring gap)
 
KIND_LABELS = {
    LIE: "Lie exposed",
    FALSE_BELIEF: "Mistaken memory",
    APPARENT: "Misleading evidence",
    UNEXPLAINED: "Unresolved",
}
 
 
class Reasoner:
    def __init__(self, mystery):
        self.mystery = mystery
        self.facts = mystery.get("facts", {})
        self.truth = mystery.get("world_truth", {})
        self.inferences = mystery.get("inferences", [])
 
    # --------------------------------------------------
    # Text helpers
    # --------------------------------------------------
 
    def fact_text(self, fact_id, value=True):
        fact = self.facts.get(fact_id, {})
        text = fact.get("text", fact_id.replace("_", " "))
 
        if value:
            return text
 
        return fact.get("negated", f"it is not true that {text}")
 
    def clue_names(self, clue_ids):
        names = []
 
        for clue_id in clue_ids:
            clue = self.mystery["clues"].get(clue_id)
            names.append(clue["name"] if clue else clue_id)
 
        return names
 
    # --------------------------------------------------
    # 1. Evidence closure
    # --------------------------------------------------
 
    def evidence_facts(
        self,
        clue_ids,
        established=None,
        excluded_clues=None,
        reliable_only=False
    ):
        """
        Return every fact the given evidence supports, plus everything
        that can be inferred from it.
 
        Result format:
            {fact_id: {"value": bool, "sources": [clue ids], "inferred": bool}}
 
        reliable_only=True ignores clues marked "reliable": false. Use that
        when checking whether the player can PROVE something; use the
        default when checking what the evidence APPEARS to show.
        """
        excluded_clues = set(excluded_clues or [])
        known = {}
 
        for fact_id, value in (established or {}).items():
            known[fact_id] = {
                "value": value,
                "sources": ["testimony"],
                "inferred": False
            }
 
        for clue_id in clue_ids:
            if clue_id in excluded_clues:
                continue
 
            clue = self.mystery["clues"].get(clue_id, {})
 
            if reliable_only and not clue.get("reliable", True):
                continue
 
            for fact_id, value in clue.get("supports", {}).items():
                if fact_id not in known:
                    known[fact_id] = {
                        "value": value,
                        "sources": [clue_id],
                        "inferred": False
                    }
                elif known[fact_id]["value"] == value:
                    if clue_id not in known[fact_id]["sources"]:
                        known[fact_id]["sources"].append(clue_id)
                # If two clues disagree, the first one wins.
                # tools/check_mystery.py warns about this.
 
        # Forward chaining: keep applying inference rules until nothing new.
        changed = True
 
        while changed:
            changed = False
 
            for rule in self.inferences:
                premises = rule.get("if", {})
 
                satisfied = all(
                    fact_id in known and known[fact_id]["value"] == value
                    for fact_id, value in premises.items()
                )
 
                if not satisfied:
                    continue
 
                sources = []
 
                for fact_id in premises:
                    for source in known[fact_id]["sources"]:
                        if source not in sources:
                            sources.append(source)
 
                for fact_id, value in rule.get("then", {}).items():
                    if fact_id not in known:
                        known[fact_id] = {
                            "value": value,
                            "sources": sources,
                            "inferred": True
                        }
                        changed = True
 
        return known
 
    # --------------------------------------------------
    # 2. Contradiction detection
    # --------------------------------------------------
 
    def find_conflicts(self, claim, known):
        """
        Compare one claim against the known facts.
 
        A conflict exists when:
          - the claim asserts fact F = v, but evidence shows F = not v, or
          - the claim is based on assumption F = v, but evidence shows F = not v.
        """
        conflicts = []
 
        for field, is_basis in (("asserts", False), ("based_on", True)):
            for fact_id, claimed in claim.get(field, {}).items():
                if fact_id not in known:
                    continue
 
                evidence_value = known[fact_id]["value"]
 
                if evidence_value != claimed:
                    conflicts.append({
                        "fact": fact_id,
                        "claimed": claimed,
                        "evidence": evidence_value,
                        "sources": list(known[fact_id]["sources"]),
                        "basis": is_basis
                    })
 
        return conflicts
 
    # --------------------------------------------------
    # 3. Classification
    # --------------------------------------------------
 
    def classify(self, character_id, claim):
        """
        Use world truth and the character's mental state to decide WHY the
        claim conflicts with the evidence. This is never shown to the player
        before a confrontation.
        """
        character = self.mystery["characters"][character_id]
        knows = character.get("knows", {})
        believes = character.get("believes", {})
 
        for fact_id, claimed in claim.get("asserts", {}).items():
            actual = self.truth.get(fact_id)
 
            if actual is None or actual == claimed:
                continue
 
            if knows.get(fact_id) == actual:
                return LIE
 
            if believes.get(fact_id) == claimed:
                return FALSE_BELIEF
 
            return UNEXPLAINED
 
        # Every asserted fact is actually true, so the evidence is what misleads.
        return APPARENT
 
    # --------------------------------------------------
    # Explanation text
    # --------------------------------------------------
 
    def explain(self, character_id, claim, conflict):
        if claim.get("contradiction_text"):
            return claim["contradiction_text"]
 
        name = self.mystery["characters"][character_id]["name"]
        sources = [s for s in conflict["sources"] if s != "testimony"]
        evidence = ", ".join(self.clue_names(sources)) or "testimony"
        shown = self.fact_text(conflict["fact"], conflict["evidence"])
 
        if conflict["basis"]:
            assumed = self.fact_text(conflict["fact"], conflict["claimed"])
            return (
                f'{name} said: "{claim["text"]}" That account assumes '
                f"{assumed}, but the evidence ({evidence}) shows that {shown}."
            )
 
        return (
            f'{name} said: "{claim["text"]}" But the evidence '
            f"({evidence}) shows that {shown}."
        )