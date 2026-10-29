from game.state import GameState
from llm.parser import ActionParser

class GameEngine:
    def __init__(self):
        self.state = GameState()
        self.parser = ActionParser(self.state.mystery)

    def process(self, player_input):
        parsed = self.parser.parse(player_input)
        action = parsed.get("action")

        if action == "look":
            return self.look()

        if action == "move":
            return self.move(parsed["room"])

        if action == "search":
            return self.search()

        if action == "question":
            return self.question(
                parsed["character"],
                parsed["topic"]
            )

        if action == "confront":
            return self.confront(
                parsed["character"],
                parsed["evidence"]
            )

        return {
            "success": False,
            "type": "unknown",
            "message": (
                "I couldn't understand that action. "
                "Try moving to a room, searching, asking a ghost "
                "about something, or confronting them with evidence."
            )
        }

    def look(self):
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

    def move(self, room_id):
        room_id = room_id.lower().strip().replace(" ", "_")
        current_room = self.state.get_current_room()

        if room_id not in self.state.mystery["rooms"]:
            return {
                "success": False,
                "message": "That location does not exist."
            }

        if room_id not in current_room["connections"]:
            return {
                "success": False,
                "message": "You cannot reach that location from here."
            }

        if room_id not in self.state.unlocked_rooms:
            return {
                "success": False,
                "message": "That location is still locked."
            }

        self.state.current_room = room_id
        room = self.state.get_current_room()

        return {
            "success": True,
            "type": "move",
            "message": f"You enter {room['name']}.",
            "room": room["name"],
            "description": room["description"]
        }

    def search(self):
        room = self.state.get_current_room()
        found = []

        for clue_id in room.get("clues", []):
            if clue_id not in self.state.discovered_clues:
                self.state.discover_clue(clue_id)

                clue = self.state.get_clue(clue_id)

                found.append({
                    "id": clue_id,
                    "name": clue["name"],
                    "description": clue["description"],
                    "reveals": clue["reveals"]
                })

        contradictions = self.state.check_contradictions()

        if not found:
            return {
                "success": True,
                "type": "search",
                "message": "You search the room but find no new evidence.",
                "contradictions": contradictions
            }

        return {
            "success": True,
            "type": "search",
            "message": f"You discovered {len(found)} new clue(s).",
            "clues": found,
            "contradictions": contradictions
        }

    def question(self, character_id, topic):
        character_id = character_id.lower().strip()
        topic = topic.lower().strip()

        character = self.state.get_character(character_id)

        if character is None:
            return {
                "success": False,
                "message": "That character does not exist."
            }

        room = self.state.get_current_room()

        if character_id not in room.get("characters", []):
            return {
                "success": False,
                "message": f"{character['name']} is not in this room."
            }

        claims = character.get("claims", {})

        if topic not in claims:
            return {
                "success": False,
                "message": f"{character['name']} has nothing to say about that."
            }

        claim = claims[topic]

        self.state.record_claim(character_id, topic)

        contradictions = self.state.check_contradictions()

        return {
            "success": True,
            "type": "question",
            "character": character["name"],
            "topic": topic,
            "response": claim,
            "contradictions": contradictions
        }

    def confront(self, character_id, clue_id):
        character_id = character_id.lower().strip()
        clue_id = clue_id.lower().strip().replace(" ", "_")

        character = self.state.get_character(character_id)

        if character is None:
            return {
                "success": False,
                "message": "That character does not exist."
            }

        room = self.state.get_current_room()

        if character_id not in room.get("characters", []):
            return {
                "success": False,
                "message": f"{character['name']} is not here."
            }

        if clue_id not in self.state.discovered_clues:
            return {
                "success": False,
                "message": "You have not discovered that evidence yet."
            }

        for contradiction in self.state.mystery["contradictions"]:
            if (
                contradiction["character"] == character_id
                and contradiction["required_clue"] == clue_id
            ):
                claim_key = (
                    f'{character_id}:'
                    f'{contradiction["claim"]}'
                )

                if claim_key not in self.state.heard_claims:
                    return {
                        "success": False,
                        "message": (
                            "You have the evidence, but you have not heard "
                            "a conflicting statement from this character yet."
                        )
                    }

                if contradiction["id"] not in \
                        self.state.discovered_contradictions:
                    self.state.discovered_contradictions.append(
                        contradiction["id"]
                    )

                return {
                    "success": True,
                    "type": "confront",
                    "character": character["name"],
                    "evidence": self.state.get_clue(clue_id)["name"],
                    "contradiction": contradiction["explanation"],
                    "response": self._confrontation_response(
                        contradiction["id"]
                    )
                }

        return {
            "success": False,
            "message": (
                "This evidence does not contradict anything "
                f"{character['name']} has told you."
            )
        }

    def _confrontation_response(self, contradiction_id):
        responses = {
            "eleanor_library": (
                "Eleanor's expression changes. "
                "\"Fine. I was in the library that night. "
                "But I had a reason for keeping that from you.\""
            ),

            "thomas_study": (
                "Thomas looks away. "
                "\"All right. I entered the study. "
                "But Arthur was alive when I found him. "
                "That knife is not proof that I hurt him.\""
            )
        }

        return responses.get(
            contradiction_id,
            "The character hesitates and refuses to answer."
        )

    def get_evidence(self):
        evidence = []

        for clue_id in self.state.discovered_clues:
            clue = self.state.get_clue(clue_id)

            evidence.append({
                "id": clue_id,
                "name": clue["name"],
                "description": clue["description"]
            })

        return evidence