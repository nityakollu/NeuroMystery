import json
from pathlib import Path
 
from game.reasoner import Reasoner, KIND_LABELS
from game.rules import RuleEngine
 
 
# Resolve data/mystery.json relative to this file, so the game works no
# matter which folder you launch it from.
DEFAULT_MYSTERY_PATH = Path(__file__).resolve().parent.parent / "data" / "mystery.json"
 
 
class GameState:
    """
    Holds every piece of mutable game state, kept in separate layers:
 
      world truth        -> self.mystery["world_truth"]   (never changes, hidden)
      character state    -> self.mystery["characters"] + self.claim_overrides
      player knowledge   -> discovered_clues, heard_claims, statement_log,
                            contradictions, established_facts
    """
 
    def __init__(self, mystery_path=None):
        self.mystery_path = Path(mystery_path) if mystery_path else DEFAULT_MYSTERY_PATH
        self.mystery = self._load_mystery()
 
        self.reasoner = Reasoner(self.mystery)
        self.rules = RuleEngine(self.mystery.get("rules", []))
 
        # Player state
        self.current_room = self.mystery.get("metadata", {}).get(
            "start_room", "entrance_hall"
        )
        self.turn = 0
        self.discovered_clues = []
        self.heard_claims = []            # "character:topic"
        self.statement_log = []           # everything the ghosts actually said
        self.contradictions = {}          # "character:topic" -> record
        self.discovered_contradictions = []  # ids, kept for app.py compatibility
        self.confronted = []              # "character:topic"
        self.discredited_clues = set()    # clues shown to be misleading
        self.established_facts = {}       # facts confirmed by testimony
        self.solved = False
 
        # Rule / character state
        self.fired_rules = []
        self.claim_overrides = {}         # "character:topic" -> revised claim
        self.unlocked_rooms = [
            room_id
            for room_id, room in self.mystery["rooms"].items()
            if not room.get("locked", False)
        ]
        self.unlocked_topics = {
            f"{character_id}:{topic}"
            for character_id, character in self.mystery["characters"].items()
            for topic, claim in character.get("claims", {}).items()
            if not claim.get("locked", False)
        }
 
    def _load_mystery(self):
        with open(self.mystery_path, "r", encoding="utf-8") as file:
            return json.load(file)
 
    # --------------------------------------------------
    # Lookups
    # --------------------------------------------------
 
    def get_current_room(self):
        return self.mystery["rooms"][self.current_room]
 
    def get_room(self, room_id):
        return self.mystery["rooms"].get(room_id)
 
    def get_character(self, character_id):
        return self.mystery["characters"].get(character_id)
 
    def get_clue(self, clue_id):
        return self.mystery["clues"].get(clue_id)
 
    def get_claim(self, character_id, topic):
        """Current version of a claim (revised if a rule or confession changed it)."""
        key = f"{character_id}:{topic}"
 
        if key in self.claim_overrides:
            return self.claim_overrides[key]
 
        character = self.get_character(character_id)
 
        if character is None:
            return None
 
        return character.get("claims", {}).get(topic)
 
    def is_topic_available(self, character_id, topic):
        return f"{character_id}:{topic}" in self.unlocked_topics
 
    # --------------------------------------------------
    # Mutations
    # --------------------------------------------------
 
    def discover_clue(self, clue_id):
        if clue_id not in self.discovered_clues:
            self.discovered_clues.append(clue_id)
            return True
 
        return False
 
    def record_claim(self, character_id, topic):
        """Player heard this claim. Logs the exact words for later review."""
        claim_key = f"{character_id}:{topic}"
        claim = self.get_claim(character_id, topic)
 
        if claim_key not in self.heard_claims:
            self.heard_claims.append(claim_key)
 
        self.statement_log.append({
            "turn": self.turn,
            "character": character_id,
            "topic": topic,
            "text": claim["text"] if claim else "",
            "room": self.current_room,
            "revised": claim_key in self.claim_overrides
        })
 
    def revise_claim(self, character_id, topic, text, asserts=None):
        self.claim_overrides[f"{character_id}:{topic}"] = {
            "text": text,
            "asserts": asserts or {},
            "revised": True
        }
        self.unlocked_topics.add(f"{character_id}:{topic}")
 
    # --------------------------------------------------
    # Reasoning
    # --------------------------------------------------
 
    def known_facts(self, reliable_only=False):
        return self.reasoner.evidence_facts(
            self.discovered_clues,
            established=self.established_facts,
            excluded_clues=self.discredited_clues,
            reliable_only=reliable_only
        )
 
    def check_contradictions(self):
        """
        Find contradictions between claims the player has HEARD and evidence
        the player has FOUND. Returns only the newly detected ones
        (player-safe view, no hidden classification).
        """
        newly_discovered = []
        known = self.known_facts()
 
        for claim_key in self.heard_claims:
            if claim_key in self.contradictions:
                continue
 
            character_id, topic = claim_key.split(":", 1)
 
            # Compare against the version of the claim the player heard first.
            claim = self.get_character(character_id)["claims"].get(topic)
 
            if claim is None:
                continue
 
            conflicts = self.reasoner.find_conflicts(claim, known)
 
            if not conflicts:
                continue
 
            conflict = conflicts[0]
            record = {
                "id": claim_key,
                "character": character_id,
                "character_name": self.get_character(character_id)["name"],
                "topic": topic,
                "claim": claim["text"],
                "fact": conflict["fact"],
                "clues": [s for s in conflict["sources"] if s != "testimony"],
                "explanation": self.reasoner.explain(character_id, claim, conflict),
                "kind": self.reasoner.classify(character_id, claim),  # hidden
                "status": "detected"
            }
 
            self.contradictions[claim_key] = record
            self.discovered_contradictions.append(claim_key)
            newly_discovered.append(self._public_contradiction(record))
 
        return newly_discovered
 
    def refresh(self):
        """
        Run rules and contradiction detection until nothing new happens.
        Call this after every successful action.
        """
        events = []
        new_contradictions = []
 
        while True:
            messages = self.rules.run(self)
            found = self.check_contradictions()
 
            events.extend(messages)
            new_contradictions.extend(found)
 
            if not messages and not found:
                break
 
        return {"events": events, "contradictions": new_contradictions}
 
    # --------------------------------------------------
    # Player-facing views
    # --------------------------------------------------
 
    def _public_contradiction(self, record):
        public = {
            "id": record["id"],
            "character": record["character"],
            "character_name": record["character_name"],
            "topic": record["topic"],
            "claim": record["claim"],
            "evidence": self.reasoner.clue_names(record["clues"]),
            "explanation": record["explanation"],
            "status": record["status"]
        }
 
        # The kind (lie / mistaken / misleading evidence) is only revealed
        # after the player confronts the character.
        if record["status"] == "confronted":
            public["outcome"] = KIND_LABELS[record["kind"]]
 
        return public
 
    def get_discovered_contradictions(self):
        return [
            self._public_contradiction(self.contradictions[c_id])
            for c_id in self.discovered_contradictions
        ]
 
    def get_statement_log(self, character_id=None):
        return [
            entry for entry in self.statement_log
            if character_id is None or entry["character"] == character_id
        ]
 
    def get_player_knowledge(self):
        known = self.known_facts()
 
        return {
            "current_room": self.current_room,
            "discovered_clues": self.discovered_clues,
            "heard_claims": self.heard_claims,
            "discovered_contradictions": self.discovered_contradictions,
            "unlocked_rooms": self.unlocked_rooms,
            "established_facts": [
                self.reasoner.fact_text(fact_id, info["value"])
                for fact_id, info in known.items()
            ]
        }
 
    # --------------------------------------------------
    # LLM context (the only state the LLM should ever see)
    # --------------------------------------------------
 
    def get_character_context(self, character_id):
        """
        Everything the LLM needs to voice one ghost, and nothing else.
        world_truth, other characters' minds, and clues the player has not
        shown this ghost are never included.
        """
        character = self.get_character(character_id)
 
        if character is None:
            return None
 
        fact_text = self.reasoner.fact_text
 
        available_topics = [
            topic for topic in character.get("claims", {})
            if self.is_topic_available(character_id, topic)
        ]
 
        current_claims = {
            topic: self.get_claim(character_id, topic)["text"]
            for topic in available_topics
        }
 
        exposed = []
 
        for record in self.contradictions.values():
            if record["character"] == character_id and record["status"] == "confronted":
                exposed.append({
                    "topic": record["topic"],
                    "original_claim": record["claim"],
                    "evidence_shown": self.reasoner.clue_names(record["clues"]),
                    "outcome": KIND_LABELS[record["kind"]]
                })
 
        return {
            "character_id": character_id,
            "name": character["name"],
            "role": character.get("role", ""),
            "personality": character.get("personality", ""),
            "knows": [
                fact_text(f, v) for f, v in character.get("knows", {}).items()
            ],
            "believes": [
                fact_text(f, v) for f, v in character.get("believes", {}).items()
            ],
            "current_claims": current_claims,
            "said_to_player": [
                {"topic": e["topic"], "text": e["text"]}
                for e in self.get_statement_log(character_id)
            ],
            "exposed_contradictions": exposed
        }
 
    def get_player_context(self):
        """What the narrator LLM may reference when describing the player's progress."""
        return {
            "current_room": self.get_current_room()["name"],
            "evidence": [
                self.get_clue(c)["name"] for c in self.discovered_clues
            ],
            "statements_heard": [
                {
                    "character": self.get_character(e["character"])["name"],
                    "text": e["text"]
                }
                for e in self.statement_log
            ],
            "contradictions": self.get_discovered_contradictions(),
            "established_facts": self.get_player_knowledge()["established_facts"]
        }