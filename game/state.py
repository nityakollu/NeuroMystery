import json
from pathlib import Path


class GameState:
    def __init__(self, mystery_path="data/mystery.json"):
        self.mystery_path = Path(mystery_path)
        self.mystery = self._load_mystery()

        # Player state
        self.current_room = "entrance_hall"
        self.discovered_clues = []
        self.heard_claims = []
        self.discovered_contradictions = []

        # The secret passage begins locked.
        self.unlocked_rooms = [
            room_id
            for room_id, room in self.mystery["rooms"].items()
            if not room.get("locked", False)
        ]

    def _load_mystery(self):
        with open(self.mystery_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def get_current_room(self):
        return self.mystery["rooms"][self.current_room]

    def get_room(self, room_id):
        return self.mystery["rooms"].get(room_id)

    def get_character(self, character_id):
        return self.mystery["characters"].get(character_id)

    def get_clue(self, clue_id):
        return self.mystery["clues"].get(clue_id)

    def discover_clue(self, clue_id):
        if clue_id not in self.discovered_clues:
            self.discovered_clues.append(clue_id)
            self._check_unlocks()
            return True

        return False

    def record_claim(self, character_id, topic):
        claim_key = f"{character_id}:{topic}"

        if claim_key not in self.heard_claims:
            self.heard_claims.append(claim_key)

    def _check_unlocks(self):
        for room_id, room in self.mystery["rooms"].items():
            required_clue = room.get("unlock_requires")

            if (
                required_clue
                and required_clue in self.discovered_clues
                and room_id not in self.unlocked_rooms
            ):
                self.unlocked_rooms.append(room_id)

    def check_contradictions(self):
        newly_discovered = []

        for contradiction in self.mystery["contradictions"]:
            contradiction_id = contradiction["id"]

            if contradiction_id in self.discovered_contradictions:
                continue

            required_clue = contradiction["required_clue"]
            claim_key = (
                f'{contradiction["character"]}:'
                f'{contradiction["claim"]}'
            )

            # A contradiction only exists from the player's perspective
            # after they have both heard the claim and found the evidence.
            if (
                required_clue in self.discovered_clues
                and claim_key in self.heard_claims
            ):
                self.discovered_contradictions.append(contradiction_id)
                newly_discovered.append(contradiction)

        return newly_discovered

    def get_player_knowledge(self):
        return {
            "current_room": self.current_room,
            "discovered_clues": self.discovered_clues,
            "heard_claims": self.heard_claims,
            "discovered_contradictions": self.discovered_contradictions,
            "unlocked_rooms": self.unlocked_rooms
        }