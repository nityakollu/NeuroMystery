class ActionParser:
    def __init__(self, mystery):
        self.mystery = mystery

    def parse(self, text):
        text = text.lower().strip()

        # LOOK
        if text in ["look", "look around", "where am i"]:
            return {
                "action": "look"
            }

        # SEARCH
        if "search" in text or "investigate" in text:
            return {
                "action": "search"
            }

        # CONFRONT
        if "confront" in text or "challenge" in text:
            character = self._find_character(text)
            clue = self._find_clue(text)

            if character and clue:
                return {
                    "action": "confront",
                    "character": character,
                    "evidence": clue
                }

            return {"action": "unknown"}

        # QUESTION
        if (
            "ask" in text
            or "question" in text
            or "talk" in text
        ):
            character = self._find_character(text)
            topic = self._find_topic(text, character)

            if character and topic:
                return {
                    "action": "question",
                    "character": character,
                    "topic": topic
                }

            return {"action": "unknown"}

        # MOVEMENT
        if (
            "go" in text
            or "move" in text
            or "enter" in text
            or "walk" in text
            or "visit" in text
        ):
            room = self._find_room(text)

            if room:
                return {
                    "action": "move",
                    "room": room
                }

            return {"action": "unknown"}

        # Also allow the player to simply type "library"
        room = self._find_room(text)

        if room:
            return {
                "action": "move",
                "room": room
            }

        return {"action": "unknown"}

    def _find_character(self, text):
        for character_id, character in self.mystery["characters"].items():
            if character_id in text:
                return character_id

            if character["name"].lower() in text:
                return character_id

        return None

    def _find_room(self, text):
        for room_id, room in self.mystery["rooms"].items():
            names = [
                room_id,
                room_id.replace("_", " "),
                room["name"].lower()
            ]

            for name in names:
                if name in text:
                    return room_id

        return None

    def _find_clue(self, text):
        clue_aliases = {
            "torn_glove": ["torn glove", "glove"],
            "broken_clock": ["broken clock", "clock"],
            "bloodied_knife": ["bloodied knife", "knife"],
            "arthur_letter": [
                "arthur's letter",
                "arthur letter",
                "letter"
            ],
            "family_photo": [
                "family photo",
                "photograph",
                "photo"
            ],
            "muddy_footprints": [
                "muddy footprints",
                "footprints"
            ]
        }

        for clue_id, aliases in clue_aliases.items():
            for alias in aliases:
                if alias in text:
                    return clue_id

        return None

    def _find_topic(self, text, character_id=None):
        if character_id:
            character = self.mystery["characters"][character_id]

            for topic in character.get("claims", {}):
                if topic.replace("_", " ") in text:
                    return topic

        topic_aliases = {
            "library": ["library"],
            "study": ["study", "office"],
            "arthur": [
                "arthur",
                "disappearance",
                "disappeared"
            ],
            "thomas": ["thomas"],
            "knife": ["knife"],
            "passage": [
                "passage",
                "secret passage"
            ]
        }

        for topic, aliases in topic_aliases.items():
            for alias in aliases:
                if alias in text:
                    return topic

        return None