from game.state import GameState
from game.reasoner import LIE, FALSE_BELIEF, APPARENT, KIND_LABELS
from llm.parser import ActionParser
 
 
class GameEngine:
    """
    Every action goes through the same pipeline (proposal Figure 1):
 
        parse -> validate -> (fail: no state change + constraint)
                          -> (ok:   apply -> refresh rules/contradictions)
 
    Validators never change state. Appliers only run after validation passes.
    """
 
    ACTIONS = ("look", "move", "search", "question", "confront", "solve")
 
    def __init__(self, mystery_path=None):
        self.state = GameState(mystery_path)
        self.parser = ActionParser(self.state.mystery)
 
    # --------------------------------------------------
    # Pipeline
    # --------------------------------------------------
 
    def process(self, player_input):
        self.state.turn += 1
        parsed = self.parser.parse(player_input)
        return self.execute(parsed)
 
    def execute(self, action):
        """Run an already-structured action, e.g. {"action": "search"}."""
        name = action.get("action")
 
        if name not in self.ACTIONS:
            return {
                "success": False,
                "type": "unknown",
                "message": (
                    "I couldn't understand that action. "
                    "Try moving to a room, searching, asking a ghost "
                    "about something, or confronting them with evidence."
                )
            }
 
        check = getattr(self, f"_validate_{name}")(action)
 
        if not check["ok"]:
            return {
                "success": False,
                "type": name,
                "message": check["reason"],
                "constraint": check.get("constraint")
            }
 
        result = getattr(self, f"_apply_{name}")(check)
 
        update = self.state.refresh()
        result["contradictions"] = (
            result.get("contradictions", []) + update["contradictions"]
        )
        result["events"] = update["events"]
 
        return result
 
    @staticmethod
    def _fail(reason, constraint):
        return {"ok": False, "reason": reason, "constraint": constraint}
 
    # Thin wrappers so other code (and tests) can call actions directly.
    def look(self):
        return self.execute({"action": "look"})
 
    def move(self, room_id):
        return self.execute({"action": "move", "room": room_id})
 
    def search(self):
        return self.execute({"action": "search"})
 
    def question(self, character_id, topic):
        return self.execute(
            {"action": "question", "character": character_id, "topic": topic}
        )
 
    def confront(self, character_id, clue_id):
        return self.execute(
            {"action": "confront", "character": character_id, "evidence": clue_id}
        )
 
    def solve(self, theory):
        return self.execute({"action": "solve", "theory": theory})
 
    # --------------------------------------------------
    # LOOK
    # --------------------------------------------------
 
    def _validate_look(self, action):
        return {"ok": True}
 
    def _apply_look(self, check):
        room = self.state.get_current_room()
 
        return {
            "success": True,
            "type": "look",
            "room": room["name"],
            "description": room["description"],
            "characters": [
                self.state.get_character(character_id)["name"]
                for character_id in room.get("characters", [])
            ]
        }
 
    # --------------------------------------------------
    # MOVE
    # --------------------------------------------------
 
    def _validate_move(self, action):
        room_id = str(action.get("room", "")).lower().strip().replace(" ", "_")
        current_room = self.state.get_current_room()
 
        if room_id not in self.state.mystery["rooms"]:
            return self._fail("That location does not exist.", "room_exists")
 
        if room_id == self.state.current_room:
            return self._fail("You are already here.", "not_current_room")
 
        if room_id not in current_room["connections"]:
            return self._fail(
                "You cannot reach that location from here.", "room_adjacent"
            )
 
        if room_id not in self.state.unlocked_rooms:
            return self._fail("That location is still locked.", "room_unlocked")
 
        return {"ok": True, "room_id": room_id}
 
    def _apply_move(self, check):
        self.state.current_room = check["room_id"]
        room = self.state.get_current_room()
 
        return {
            "success": True,
            "type": "move",
            "message": f"You enter {room['name']}.",
            "room": room["name"],
            "description": room["description"]
        }
 
    # --------------------------------------------------
    # SEARCH
    # --------------------------------------------------
 
    def _validate_search(self, action):
        return {"ok": True}
 
    def _apply_search(self, check):
        room = self.state.get_current_room()
        found = []
 
        for clue_id in room.get("clues", []):
            if self.state.discover_clue(clue_id):
                clue = self.state.get_clue(clue_id)
                found.append({
                    "id": clue_id,
                    "name": clue["name"],
                    "description": clue["description"],
                    "reveals": clue["reveals"]
                })
 
        if not found:
            return {
                "success": True,
                "type": "search",
                "message": "You search the room but find no new evidence.",
                "clues": []
            }
 
        return {
            "success": True,
            "type": "search",
            "message": f"You discovered {len(found)} new clue(s).",
            "clues": found
        }
 
    # --------------------------------------------------
    # QUESTION
    # --------------------------------------------------
 
    def _validate_question(self, action):
        character_id = str(action.get("character", "")).lower().strip()
        topic = str(action.get("topic", "")).lower().strip()
        character = self.state.get_character(character_id)
 
        if character is None:
            return self._fail("That character does not exist.", "character_exists")
 
        if character_id not in self.state.get_current_room().get("characters", []):
            return self._fail(
                f"{character['name']} is not in this room.", "character_present"
            )
 
        # Locked topics get the same message as missing ones so the player
        # can't fish for hidden topics.
        if (
            self.state.get_claim(character_id, topic) is None
            or not self.state.is_topic_available(character_id, topic)
        ):
            return self._fail(
                f"{character['name']} has nothing to say about that.",
                "topic_available"
            )
 
        return {"ok": True, "character_id": character_id, "topic": topic}
 
    def _apply_question(self, check):
        character_id, topic = check["character_id"], check["topic"]
        claim = self.state.get_claim(character_id, topic)
 
        self.state.record_claim(character_id, topic)
 
        return {
            "success": True,
            "type": "question",
            "character": self.state.get_character(character_id)["name"],
            "character_id": character_id,
            "topic": topic,
            "response": claim["text"],
            "revised": bool(claim.get("revised"))
        }
 
    # --------------------------------------------------
    # CONFRONT
    # --------------------------------------------------
 
    def _validate_confront(self, action):
        character_id = str(action.get("character", "")).lower().strip()
        raw_clue = str(action.get("evidence", "")).lower().strip()
        clue_id = raw_clue.replace(" ", "_")
 
        # Accept aliases too ("glove" -> "torn_glove"), in case the LLM
        # interpreter outputs a name instead of an id.
        if clue_id not in self.state.mystery["clues"]:
            clue_id = self.parser._find_clue(raw_clue) or clue_id
 
        character = self.state.get_character(character_id)
 
        if character is None:
            return self._fail("That character does not exist.", "character_exists")
 
        if character_id not in self.state.get_current_room().get("characters", []):
            return self._fail(f"{character['name']} is not here.", "character_present")
 
        if clue_id not in self.state.discovered_clues:
            return self._fail(
                "You have not discovered that evidence yet.", "has_evidence"
            )
 
        # Contradictions already detected for this character that use this clue
        matches = [
            record for record in self.state.contradictions.values()
            if record["character"] == character_id and clue_id in record["clues"]
        ]
 
        if matches:
            open_matches = [r for r in matches if r["status"] != "confronted"]
 
            if not open_matches:
                return self._fail(
                    f"You have already confronted {character['name']} about that.",
                    "not_already_confronted"
                )
 
            return {"ok": True, "record": open_matches[0], "clue_id": clue_id}
 
        # No detected contradiction. Would this clue contradict a claim the
        # player simply hasn't heard yet?
        known = self.state.known_facts()
 
        for topic, claim in character.get("claims", {}).items():
            if f"{character_id}:{topic}" in self.state.heard_claims:
                continue
 
            for conflict in self.state.reasoner.find_conflicts(claim, known):
                if clue_id in conflict["sources"]:
                    return self._fail(
                        "You have the evidence, but you have not heard "
                        "a conflicting statement from this character yet.",
                        "heard_claim"
                    )
 
        return self._fail(
            "This evidence does not contradict anything "
            f"{character['name']} has told you.",
            "evidence_conflicts_with_claim"
        )
 
    def _apply_confront(self, check):
        record = check["record"]
        clue_id = check["clue_id"]
        character_id = record["character"]
        character = self.state.get_character(character_id)
        claim = character["claims"][record["topic"]]
        kind = record["kind"]
 
        record["status"] = "confronted"
        self.state.confronted.append(record["id"])
 
        if kind in (LIE, FALSE_BELIEF):
            default = (
                f"{character['name']} falls silent, then admits it wasn't true."
                if kind == LIE else
                f"{character['name']} hesitates. \"I... I was so sure. "
                "Maybe I remembered it wrong.\""
            )
            response = claim.get("confession", default)
 
            # The character's story changes. Their new statement is consistent
            # with what they actually know.
            truthful = {
                fact_id: self.state.mystery["world_truth"][fact_id]
                for fact_id in claim.get("asserts", {})
                if fact_id in self.state.mystery["world_truth"]
            }
            self.state.revise_claim(character_id, record["topic"], response, truthful)
 
        elif kind == APPARENT:
            # The character was telling the truth. The evidence was misleading,
            # so it no longer counts toward what the player "knows".
            response = claim.get(
                "stands_firm",
                f"{character['name']} doesn't waver. \"I told you the truth.\""
            )
            self.state.discredited_clues.add(clue_id)
 
        else:
            response = f"{character['name']} hesitates and refuses to answer."
 
        self.state.statement_log.append({
            "turn": self.state.turn,
            "character": character_id,
            "topic": record["topic"],
            "text": response,
            "room": self.state.current_room,
            "revised": True
        })
 
        return {
            "success": True,
            "type": "confront",
            "character": character["name"],
            "evidence": self.state.get_clue(clue_id)["name"],
            "contradiction": record["explanation"],
            "outcome": KIND_LABELS[kind],
            "response": response
        }
 
    # --------------------------------------------------
    # SOLVE
    # --------------------------------------------------
 
    def _validate_solve(self, action):
        theory = action.get("theory") or {}
 
        if not theory:
            questions = [
                spec.get("question", fact_id)
                for fact_id, spec in self.state.mystery["solution"]["facts"].items()
            ]
            return self._fail(
                "State your theory. It should answer: " + " ".join(questions),
                "theory_given"
            )
 
        return {"ok": True, "theory": theory}
 
    def _apply_solve(self, check):
        theory = check["theory"]
        solution = self.state.mystery["solution"]
        required = solution["facts"]
        proven = self.state.known_facts(reliable_only=True)
 
        missing = [f for f in required if f not in theory]
        wrong = [f for f in required if f in theory and theory[f] != required[f]["value"]]
        unproven = [
            f for f in required
            if f in theory and f not in wrong
            and (f not in proven or proven[f]["value"] != theory[f])
        ]
 
        if wrong:
            message = (
                "You lay out your theory, but the ghosts exchange knowing looks. "
                "At least part of it doesn't fit what really happened."
            )
        elif missing:
            message = "Your theory is incomplete. You still need to answer: " + " ".join(
                required[f].get("question", f) for f in missing
            )
        elif unproven:
            message = "You might be right, but you can't prove it yet. You lack evidence that " + "; ".join(
                self.state.reasoner.fact_text(f, theory[f]) for f in unproven
            ) + "."
        else:
            self.state.solved = True
            message = "Case closed. " + solution["summary"]
 
        return {
            "success": True,
            "type": "solve",
            "solved": self.state.solved,
            "message": message
        }
 
    # --------------------------------------------------
    # Views used by app.py
    # --------------------------------------------------
 
    def get_evidence(self):
        evidence = []
 
        for clue_id in self.state.discovered_clues:
            clue = self.state.get_clue(clue_id)
            evidence.append({
                "id": clue_id,
                "name": clue["name"],
                "description": clue["description"],
                "discredited": clue_id in self.state.discredited_clues
            })
 
        return evidence