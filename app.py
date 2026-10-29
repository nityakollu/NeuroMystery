import streamlit as st
from game.engine import GameEngine


# --------------------------------------------------
# Page setup
# --------------------------------------------------

st.set_page_config(
    page_title="NeuroMystery",
    page_icon="🕯️",
    layout="wide"
)


# --------------------------------------------------
# Game session
# --------------------------------------------------

if "game" not in st.session_state:
    st.session_state.game = GameEngine()

if "history" not in st.session_state:
    st.session_state.history = [
        {
            "role": "game",
            "text": (
                "You arrive at Blackwood Manor thirty years after "
                "Arthur Blackwood mysteriously disappeared. "
                "Three ghosts remain inside the mansion. "
                "Find the evidence, question them, and determine "
                "what happened that night."
            )
        }
    ]

game = st.session_state.game


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def format_result(result):
    if not result.get("success"):
        return result.get("message", "That action could not be completed.")

    result_type = result.get("type")

    if result_type == "look":
        text = f"**{result['room']}**\n\n{result['description']}"

        if result.get("characters"):
            text += "\n\n**Present:** " + ", ".join(result["characters"])

        return text

    if result_type == "move":
        return (
            f"**{result['message']}**\n\n"
            f"{result['description']}"
        )

    if result_type == "search":
        text = result["message"]

        for clue in result.get("clues", []):
            text += (
                f"\n\n🔎 **{clue['name']}**\n\n"
                f"{clue['description']}"
            )

        for contradiction in result.get("contradictions", []):
            text += (
                "\n\n⚠️ **New Contradiction Detected**\n\n"
                f"{contradiction['explanation']}"
            )

        return text

    if result_type == "question":
        text = (
            f"**{result['character']}**\n\n"
            f"“{result['response']}”"
        )

        for contradiction in result.get("contradictions", []):
            text += (
                "\n\n⚠️ **New Contradiction Detected**\n\n"
                f"{contradiction['explanation']}"
            )

        return text

    if result_type == "confront":
        return (
            f"⚠️ **Contradiction Confirmed**\n\n"
            f"{result['contradiction']}\n\n"
            f"**{result['character']}**\n\n"
            f"{result['response']}"
        )

    return result.get("message", str(result))


def submit_action():
    player_input = st.session_state.player_input.strip()

    if not player_input:
        return

    st.session_state.history.append({
        "role": "player",
        "text": player_input
    })

    result = game.process(player_input)

    st.session_state.history.append({
        "role": "game",
        "text": format_result(result)
    })

    st.session_state.player_input = ""


# --------------------------------------------------
# Header
# --------------------------------------------------

st.title("🕯️ NeuroMystery")
st.caption("The Blackwood Manor Disappearance")

st.markdown(
    """
    Explore the mansion, collect evidence, question its ghosts,
    and uncover the truth behind Arthur Blackwood's disappearance.
    """
)

st.divider()


# --------------------------------------------------
# Main layout
# --------------------------------------------------

main, sidebar = st.columns([2.2, 1])


# --------------------------------------------------
# Main game panel
# --------------------------------------------------

with main:
    current_room = game.state.get_current_room()

    st.subheader(f"📍 {current_room['name']}")
    st.write(current_room["description"])

    characters = current_room.get("characters", [])

    if characters:
        names = [
            game.state.get_character(character_id)["name"]
            for character_id in characters
        ]

        st.caption("Present: " + ", ".join(names))

    st.divider()

    st.subheader("Investigation")

    for item in st.session_state.history:
        if item["role"] == "player":
            with st.chat_message("user"):
                st.markdown(item["text"])
        else:
            with st.chat_message("assistant"):
                st.markdown(item["text"])

    st.text_input(
        "What do you want to do?",
        key="player_input",
        placeholder=(
            "Try: Go to the library, search the room, "
            "or ask Eleanor about the library..."
        ),
        on_change=submit_action
    )

    st.caption(
        "Examples: “Go to the library” • “Search the room” • "
        "“Ask Eleanor about the library” • "
        "“Confront Eleanor about the torn glove”"
    )


# --------------------------------------------------
# Investigation sidebar
# --------------------------------------------------

with sidebar:
    st.subheader("🧾 Evidence")

    evidence = game.get_evidence()

    if not evidence:
        st.caption("No evidence discovered yet.")
    else:
        for clue in evidence:
            with st.expander(clue["name"]):
                st.write(clue["description"])

    st.divider()

    st.subheader("⚠️ Contradictions")

    contradiction_ids = game.state.discovered_contradictions

    if not contradiction_ids:
        st.caption("No contradictions discovered yet.")
    else:
        for contradiction in game.state.mystery["contradictions"]:
            if contradiction["id"] in contradiction_ids:
                st.write(f"• {contradiction['explanation']}")

    st.divider()

    st.subheader("🗺️ Locations")

    for room_id, room in game.state.mystery["rooms"].items():
        if room_id in game.state.unlocked_rooms:
            if room_id == game.state.current_room:
                st.write(f"📍 **{room['name']}**")
            else:
                st.write(f"• {room['name']}")
        else:
            st.write("🔒 Unknown Location")

    st.divider()

    if st.button("Restart Investigation"):
        st.session_state.game = GameEngine()
        st.session_state.history = [
            {
                "role": "game",
                "text": (
                    "The investigation has restarted. "
                    "You are standing inside the entrance hall "
                    "of Blackwood Manor."
                )
            }
        ]
        st.rerun()