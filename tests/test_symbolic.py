import pytest
 
from game.engine import GameEngine
from tools.check_mystery import report
 
 
@pytest.fixture
def game():
    return GameEngine()
 
 
def go(game, *rooms):
    for room in rooms:
        result = game.move(room)
        assert result["success"], result
 
 
# --------------------------------------------------
# Preconditions
# --------------------------------------------------
 
def test_cannot_confront_without_evidence(game):
    go(game, "library")
    game.question("eleanor", "library")
    result = game.confront("eleanor", "torn_glove")
    assert not result["success"]
    assert result["constraint"] == "has_evidence"
 
 
def test_cannot_confront_before_hearing_claim(game):
    go(game, "library")
    game.search()
    result = game.confront("eleanor", "torn_glove")
    assert not result["success"]
    assert result["constraint"] == "heard_claim"
 
 
def test_unrelated_evidence_is_rejected(game):
    go(game, "library")
    game.search()
    game.question("eleanor", "library")
    result = game.confront("eleanor", "broken_clock")
    assert not result["success"]
    assert result["constraint"] == "evidence_conflicts_with_claim"
 
 
def test_failed_action_changes_nothing(game):
    before = (list(game.state.discovered_clues), game.state.current_room)
    game.move("secret_passage")  # not adjacent and locked
    after = (list(game.state.discovered_clues), game.state.current_room)
    assert before == after
 
 
def test_secret_passage_unlocks_from_letter(game):
    go(game, "library")
    assert not game.move("secret_passage")["success"]
 
    go(game, "entrance_hall", "study")
    result = game.search()
    assert any("Secret Passage" in e for e in result["events"])
 
    go(game, "entrance_hall", "library", "secret_passage")
 
 
# --------------------------------------------------
# Contradiction detection (order independent)
# --------------------------------------------------
 
def test_contradiction_claim_then_evidence(game):
    go(game, "library")
    assert game.question("eleanor", "library")["contradictions"] == []
    found = game.search()["contradictions"]
    assert [c["id"] for c in found] == ["eleanor:library"]
 
 
def test_contradiction_evidence_then_claim(game):
    go(game, "library")
    game.search()
    found = game.question("eleanor", "library")["contradictions"]
    assert [c["id"] for c in found] == ["eleanor:library"]
 
 
def test_kind_hidden_until_confronted(game):
    go(game, "library")
    game.search()
    record = game.question("eleanor", "library")["contradictions"][0]
    assert "outcome" not in record
    assert "kind" not in record
 
 
# --------------------------------------------------
# Classification
# --------------------------------------------------
 
def test_lie(game):
    go(game, "library")
    game.search()
    game.question("eleanor", "library")
    result = game.confront("eleanor", "glove")
    assert result["success"]
    assert result["outcome"] == "Lie exposed"
 
 
def test_false_belief_through_assumption(game):
    # Clara's claim relies on the clock being right; the broken clock undermines it.
    go(game, "drawing_room")
    game.question("clara", "arthur")
    go(game, "entrance_hall", "library")
    found = game.search()["contradictions"]
    assert "clara:arthur" in [c["id"] for c in found]
 
    go(game, "entrance_hall", "drawing_room")
    result = game.confront("clara", "broken_clock")
    assert result["outcome"] == "Mistaken memory"
 
 
def test_apparent_contradiction_discredits_evidence(game):
    go(game, "study")
    game.search()
    game.question("thomas", "arthur")
    result = game.confront("thomas", "bloodied_knife")
    assert result["outcome"] == "Misleading evidence"
    assert "bloodied_knife" in game.state.discredited_clues
    assert "arthur_harmed_in_study" not in game.state.known_facts()
 
 
# --------------------------------------------------
# Rule effects after confrontation
# --------------------------------------------------
 
def test_confronting_eleanor_unlocks_passage_topic(game):
    go(game, "library")
    assert not game.question("eleanor", "passage")["success"]
 
    game.search()
    game.question("eleanor", "library")
    result = game.confront("eleanor", "torn_glove")
    assert result["events"]
 
    assert game.question("eleanor", "passage")["success"]
 
 
def test_confronting_thomas_revises_knife_story(game):
    go(game, "study")
    before = game.question("thomas", "knife")["response"]
    game.search()
    game.question("thomas", "study")
    game.confront("thomas", "groundskeeper_keys")
 
    after = game.question("thomas", "knife")
    assert after["response"] != before
    assert after["revised"]
 
 
def test_statement_log_keeps_original_and_revision(game):
    go(game, "library")
    game.search()
    game.question("eleanor", "library")
    game.confront("eleanor", "torn_glove")
    log = game.state.get_statement_log("eleanor")
    assert log[0]["text"] == "I never entered the library that night."
    assert log[-1]["revised"]
 
 
# --------------------------------------------------
# LLM context isolation
# --------------------------------------------------
 
def test_character_context_hides_world_truth(game):
    context = game.state.get_character_context("eleanor")
    flat = str(context)
    assert "world_truth" not in flat
    # Eleanor doesn't know this; it's in Thomas's head only.
    assert "Thomas found the knife" not in flat
    # Locked topic must not leak before it's unlocked.
    assert "passage" not in context["current_claims"]
 
 
# --------------------------------------------------
# Solving
# --------------------------------------------------
 
def test_correct_theory_without_proof_is_rejected(game):
    result = game.solve({"arthur_murdered": False, "arthur_left_via_passage": True})
    assert not result["solved"]
    assert "can't prove" in result["message"]
 
 
def test_wrong_theory(game):
    result = game.solve({"arthur_murdered": True, "arthur_left_via_passage": True})
    assert not result["solved"]
 
 
def test_full_solve_through_parser(game):
    for command in [
        "go to the study", "search the room",
        "go to the entrance hall", "go to the library",
        "go to the secret passage", "search",
        "solve: Arthur wasn't murdered, he escaped through the passage",
    ]:
        result = game.process(command)
 
    assert result["solved"], result
 
 
# --------------------------------------------------
# Parser hooks
# --------------------------------------------------
 
@pytest.mark.parametrize("text, clue", [
    ("confront eleanor about the glove", "torn_glove"),
    ("challenge clara with the grandfather clock", "broken_clock"),
    ("confront thomas about his keys", "groundskeeper_keys"),
])
def test_parser_finds_clues(game, text, clue):
    assert game.parser.parse(text)["evidence"] == clue
 
 
def test_parser_theory_negation(game):
    theory = game.parser.parse("solve: he was not murdered")["theory"]
    assert theory["arthur_murdered"] is False
 
 
# --------------------------------------------------
# Data file
# --------------------------------------------------
 
def test_mystery_file_is_consistent_and_solvable():
    errors, _ = report()
    assert errors == []