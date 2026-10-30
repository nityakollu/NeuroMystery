class ActionParser:
    def __init__(self, mystery):
        self.mystery = mystery

    def parse(self, text):
        text = text.lower().strip()

        # SOLVE (checked first: theories mention rooms like "passage")
        if text.startswith(("solve", "accuse", "my theory", "theory", "conclusion")):
            return {
                "action": "solve",
                "theory": self._parse_theory(text)
            }

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
        # Aliases now come from each clue's "aliases" list in mystery.json,
        # so new clues work without editing the parser.
        candidates = []
 
        for clue_id, clue in self.mystery["clues"].items():
            names = clue.get("aliases", []) + [
                clue["name"].lower(),
                clue_id.replace("_", " ")
            ]
 
            for alias in names:
                candidates.append((alias.lower(), clue_id))
 
        # Longest alias first, so "grandfather clock" beats "clock".
        candidates.sort(key=lambda pair: len(pair[0]), reverse=True)
 
        for alias, clue_id in candidates:
            if alias in text:
                return clue_id
 
        return None
    
    def _parse_theory(self, text):
        """
        Turn "solve: Arthur wasn't murdered, he escaped through the passage"
        into {"arthur_murdered": False, "arthur_left_via_passage": True}
        using the keyword lists in mystery.json -> solution -> facts.
        (The LLM interpreter can replace this later and output the same dict.)
        """
        theory = {}
        facts = self.mystery.get("solution", {}).get("facts", {})
 
        for fact_id, spec in facts.items():
            # Negative phrases first: "not murdered" also contains "murdered".
            if any(k in text for k in spec.get("keywords_false", [])):
                theory[fact_id] = False
            elif any(k in text for k in spec.get("keywords_true", [])):
                theory[fact_id] = True
 
        return theory

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