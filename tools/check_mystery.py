"""
Sanity-check a mystery file before playing it.
 
    python tools/check_mystery.py                 # checks data/mystery.json
    python tools/check_mystery.py path/to/other.json
 
Two passes:
  1. Static checks: every id a field points to actually exists.
  2. Playthrough: a "greedy detective" explores every reachable room, searches
     everything, asks every ghost every available topic, and confronts every
     contradiction, until nothing new happens. Then it reports what was never
     reached and whether the solution can be proven from reliable evidence.
 
Exit code 1 if any ERROR is found.
"""
 
import sys
from collections import deque
from pathlib import Path
 
# Allow running as "python tools/check_mystery.py" from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
 
from game.engine import GameEngine  # noqa: E402
from game.reasoner import KIND_LABELS  # noqa: E402
 
 
def static_checks(mystery):
    errors, warnings = [], []
    facts = mystery.get("facts", {})
    rooms = mystery["rooms"]
    clues = mystery["clues"]
    characters = mystery["characters"]
 
    def check_fact(fact_id, where):
        if fact_id not in facts:
            errors.append(f"{where}: unknown fact '{fact_id}'")
 
    for fact_id in mystery.get("world_truth", {}):
        check_fact(fact_id, "world_truth")
 
    for fact_id in facts:
        if fact_id not in mystery.get("world_truth", {}):
            warnings.append(f"fact '{fact_id}' has no world_truth value")
 
    for room_id, room in rooms.items():
        for other in room.get("connections", []):
            if other not in rooms:
                errors.append(f"room '{room_id}': connection to unknown room '{other}'")
            elif room_id not in rooms[other].get("connections", []):
                warnings.append(f"room '{room_id}' -> '{other}' is one-way")
 
        for character_id in room.get("characters", []):
            if character_id not in characters:
                errors.append(f"room '{room_id}': unknown character '{character_id}'")
 
        for clue_id in room.get("clues", []):
            if clue_id not in clues:
                errors.append(f"room '{room_id}': unknown clue '{clue_id}'")
            elif clues[clue_id].get("location") != room_id:
                warnings.append(
                    f"clue '{clue_id}' is in room '{room_id}' but its location "
                    f"says '{clues[clue_id].get('location')}'"
                )
 
    for clue_id, clue in clues.items():
        for fact_id in clue.get("supports", {}):
            check_fact(fact_id, f"clue '{clue_id}' supports")
 
    for character_id, character in characters.items():
        for field in ("knows", "believes"):
            for fact_id in character.get(field, {}):
                check_fact(fact_id, f"character '{character_id}' {field}")
 
        for topic, claim in character.get("claims", {}).items():
            if not isinstance(claim, dict) or "text" not in claim:
                errors.append(f"claim '{character_id}:{topic}' must be an object with 'text'")
                continue
 
            for field in ("asserts", "based_on"):
                for fact_id in claim.get(field, {}):
                    check_fact(fact_id, f"claim '{character_id}:{topic}' {field}")
 
    for rule in mystery.get("inferences", []):
        for fact_id in list(rule.get("if", {})) + list(rule.get("then", {})):
            check_fact(fact_id, f"inference '{rule.get('id')}'")
 
    for fact_id in mystery.get("solution", {}).get("facts", {}):
        check_fact(fact_id, "solution")
 
    # Two clues pointing to opposite values of the same fact
    seen = {}
 
    for clue_id, clue in clues.items():
        for fact_id, value in clue.get("supports", {}).items():
            if fact_id in seen and seen[fact_id][0] != value:
                warnings.append(
                    f"clues '{seen[fact_id][1]}' and '{clue_id}' support "
                    f"opposite values of '{fact_id}'"
                )
            seen.setdefault(fact_id, (value, clue_id))
 
    return errors, warnings
 
 
def reachable_rooms(state):
    start = state.current_room
    seen = {start}
    queue = deque([start])
 
    while queue:
        room_id = queue.popleft()
 
        for other in state.get_room(room_id).get("connections", []):
            if other in state.unlocked_rooms and other not in seen:
                seen.add(other)
                queue.append(other)
 
    return seen
 
 
def signature(state):
    return (
        len(state.discovered_clues),
        len(state.heard_claims),
        len(state.contradictions),
        len(state.confronted),
        len(state.unlocked_rooms),
        len(state.unlocked_topics),
        len(state.statement_log) > 0
    )
 
 
def playthrough(mystery_path=None):
    engine = GameEngine(mystery_path)
    state = engine.state
    start_room = state.current_room
 
    previous = None
 
    while signature(state) != previous:
        previous = signature(state)
 
        for room_id in sorted(reachable_rooms(state)):
            # The checker "teleports"; real players walk via connections.
            state.current_room = room_id
            engine.search()
 
            for character_id in state.get_room(room_id).get("characters", []):
                for topic in state.get_character(character_id).get("claims", {}):
                    key = f"{character_id}:{topic}"
 
                    if state.is_topic_available(character_id, topic) and key not in state.heard_claims:
                        engine.question(character_id, topic)
 
                for record in list(state.contradictions.values()):
                    if record["character"] == character_id and record["status"] != "confronted":
                        engine.confront(character_id, record["clues"][0])
 
    state.current_room = start_room
    return engine
 
 
def report(mystery_path=None):
    engine = GameEngine(mystery_path)
    mystery = engine.state.mystery
 
    errors, warnings = static_checks(mystery)
 
    if not errors:
        engine = playthrough(mystery_path)
        state = engine.state
 
        for room_id in mystery["rooms"]:
            if room_id not in state.unlocked_rooms:
                errors.append(f"room '{room_id}' can never be unlocked")
 
        for clue_id in mystery["clues"]:
            if clue_id not in state.discovered_clues:
                errors.append(f"clue '{clue_id}' can never be found")
 
        for character_id, character in mystery["characters"].items():
            for topic in character.get("claims", {}):
                if f"{character_id}:{topic}" not in state.heard_claims:
                    warnings.append(f"claim '{character_id}:{topic}' is never heard")
 
        kinds = {}
 
        for record in state.contradictions.values():
            kinds.setdefault(record["kind"], []).append(record["id"])
            if record["kind"] == "unexplained":
                warnings.append(
                    f"contradiction '{record['id']}' has no explanation in "
                    "knows/believes/world_truth"
                )
 
        solution = mystery.get("solution", {}).get("facts", {})
        theory = {f: spec["value"] for f, spec in solution.items()}
        result = engine.solve(theory)
 
        if not result.get("solved"):
            errors.append(f"solution cannot be proven: {result.get('message')}")
 
        print("Contradictions found by a complete playthrough:")
        for kind, ids in kinds.items():
            print(f"  {KIND_LABELS[kind]}: {', '.join(ids)}")
 
    for w in warnings:
        print(f"WARNING: {w}")
 
    for e in errors:
        print(f"ERROR:   {e}")
 
    if not errors:
        print("OK: mystery is consistent and solvable.")
 
    return errors, warnings
 
 
if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    found_errors, _ = report(path)
    sys.exit(1 if found_errors else 0)