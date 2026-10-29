"""
Preconditions -> effects rule system.
 
Rules live in the "rules" list of mystery.json:
 
    {
      "id": "letter_reveals_passage",
      "when": [ {"has_clue": "arthur_letter"} ],          # ALL must hold
      "then": [ {"unlock_room": "secret_passage"},
                {"message": "..."} ]
    }
 
Each rule fires at most once.
 
Conditions
    {"has_clue": clue_id}
    {"heard_claim": "character:topic"}
    {"contradiction_found": "character:topic"}
    {"confronted": "character:topic"}
    {"in_room": room_id}
    {"fact_known": {"fact": fact_id, "value": bool}}     # from reliable evidence
    {"any": [condition, condition, ...]}                 # OR
 
Effects
    {"unlock_room": room_id}
    {"unlock_topic": "character:topic"}
    {"revise_claim": {"character", "topic", "text", "asserts"?}}
    {"establish_fact": {"fact": fact_id, "value": bool}}
    {"message": text}
"""
 
 
class RuleEngine:
    def __init__(self, rules):
        self.rules = rules or []
 
    # --------------------------------------------------
    # Conditions
    # --------------------------------------------------
 
    def condition_met(self, condition, state):
        if "any" in condition:
            return any(self.condition_met(c, state) for c in condition["any"])
 
        if "has_clue" in condition:
            return condition["has_clue"] in state.discovered_clues
 
        if "heard_claim" in condition:
            return condition["heard_claim"] in state.heard_claims
 
        if "contradiction_found" in condition:
            return condition["contradiction_found"] in state.contradictions
 
        if "confronted" in condition:
            return condition["confronted"] in state.confronted
 
        if "in_room" in condition:
            return state.current_room == condition["in_room"]
 
        if "fact_known" in condition:
            spec = condition["fact_known"]
            known = state.known_facts(reliable_only=True)
            fact = known.get(spec["fact"])
            return fact is not None and fact["value"] == spec.get("value", True)
 
        raise ValueError(f"Unknown rule condition: {condition}")
 
    # --------------------------------------------------
    # Effects
    # --------------------------------------------------
 
    def apply_effect(self, effect, state):
        """Apply one effect. Returns a player-facing message or None."""
        if "unlock_room" in effect:
            room_id = effect["unlock_room"]
 
            if room_id not in state.unlocked_rooms:
                state.unlocked_rooms.append(room_id)
 
            return None
 
        if "unlock_topic" in effect:
            state.unlocked_topics.add(effect["unlock_topic"])
            return None
 
        if "revise_claim" in effect:
            spec = effect["revise_claim"]
            state.revise_claim(
                spec["character"],
                spec["topic"],
                spec["text"],
                spec.get("asserts", {})
            )
            return None
 
        if "establish_fact" in effect:
            spec = effect["establish_fact"]
            state.established_facts[spec["fact"]] = spec.get("value", True)
            return None
 
        if "message" in effect:
            return effect["message"]
 
        raise ValueError(f"Unknown rule effect: {effect}")
 
    # --------------------------------------------------
    # Run
    # --------------------------------------------------
 
    def run(self, state):
        """
        Fire every rule whose conditions now hold and that has not fired yet.
        Returns the list of player-facing messages produced.
        """
        messages = []
 
        for rule in self.rules:
            if rule["id"] in state.fired_rules:
                continue
 
            conditions = rule.get("when", [])
 
            if all(self.condition_met(c, state) for c in conditions):
                state.fired_rules.append(rule["id"])
 
                for effect in rule.get("then", []):
                    message = self.apply_effect(effect, state)
 
                    if message:
                        messages.append(message)
 
        return messages