"""
Author: Joshua Smith
Project: busicash
Date: 8/1/2026
Description: entry point for the BusiCash dashboard.
"""
""" version 1.2 """
import streamlit as st
import database
import gemini_engine as ge

st.set_page_config(page_title="BusiCash - Student Sandboxing Dashboard", layout="wide")

st.title("BusiCash Sandbox Dashboard")
st.subheader("Automated AI Multi-Sig Governance for Young Founders")

# ---- Sidebar: pick an existing venture, or start a brand new one ----
st.sidebar.header("Ventures")

venture_names = database.list_venture_names()
NEW_VENTURE_LABEL = "+ Start a New Venture"
options = venture_names + [NEW_VENTURE_LABEL]

remembered = st.session_state.get("selected_venture")
if remembered in options:
    default_index = options.index(remembered)
elif venture_names:
    default_index = 0
else:
    default_index = len(options) - 1

choice = st.sidebar.selectbox("Choose a venture", options, index=default_index)

if choice == NEW_VENTURE_LABEL:
    st.sidebar.subheader("Create a New Venture Group")
    name_input = st.sidebar.text_input("Project / Business Name", value="")
    starting_capital = st.sidebar.number_input("Starting Capital Pool ($)", min_value=10, value=1000)
    partner_ids = st.sidebar.text_input("Member IDs (comma separated)", value="")
    members_list = [n.strip() for n in partner_ids.split(",") if n.strip()]

    if st.sidebar.button("Launch Shared Pool"):
        if not name_input.strip():
            st.sidebar.error("Give your venture a name first.")
        elif not members_list:
            st.sidebar.error("Add at least one member.")
        else:
            database.create_venture(name_input, starting_capital, members_list)
            st.session_state.selected_venture = name_input
            st.rerun()

    st.info("👈 Fill out the sidebar and click **Launch Shared Pool** to create your first venture.")
    st.stop()

project_name = choice
st.session_state.selected_venture = choice
venture_data = database.get_venture(project_name)

# ---- Main window ----
st.header(f"📊 {project_name}")

col1, col2 = st.columns(2)
with col1:
    st.metric(label="Remaining Capital Pool", value=f"${venture_data['capital_pool']:,.2f}")
with col2:
    st.write(f"**Venture Partners:** {', '.join(venture_data['members'])}")

st.divider()

# ---- Purchase proposal form ----
st.subheader("Submit a Purchase Proposal")
p_col1, p_col2 = st.columns([3, 1])
with p_col1:
    item_name = st.text_input("Item Name", placeholder="e.g., marketing ads, Helmets, Software License, Spare Tire")
with p_col2:
    cost = st.number_input("Cost ($)", min_value=0.0, value=1.0, step=10.0)

justification = st.text_area(
    "Why is this essential for the business?",
    placeholder="Describe how this purchase directly supports venture goals. e.g., Replacement tire for rental fleet",
)

if st.button("Evaluate with Gemini AI Guardrail"):
    with st.spinner("Analyzing proposal against the business scope and budget..."):
        context = f"Business: {project_name}, Pool Balance: ${venture_data['capital_pool']:.2f}"
        ai_response = ge.evaluate_spend_proposal(context, item_name, cost, justification)

        verdict = "REJECTED"
        if "APPROVED" in ai_response.upper():
            verdict = "APPROVED"
        elif "REQUIRES" in ai_response.upper() or "VOTE" in ai_response.upper():
            verdict = "REQUIRES_COFOUNDER_VOTE"

        database.record_transaction(project_name, item_name, cost, justification, verdict, ai_response)

        st.subheader("🤖 Gemini Compliance Verdict")
        if verdict == "APPROVED":
            st.success(ai_response)
        elif verdict == "REQUIRES_COFOUNDER_VOTE":
            st.warning(ai_response)
        else:
            st.error(ai_response)

    st.rerun()

# ---- Pending co-founder votes (this is the "multi-sig" part) ----
st.divider()
if venture_data.get("pending_votes"):
    st.header("🗳️ Pending Co-Founder Votes")
    for vote in venture_data["pending_votes"]:
        with st.container(border=True):
            st.write(f"**{vote['item']}** — ${vote['cost']:,.2f}")
            st.caption(vote["justification"])
            st.info(vote["explanation"])
            vcol1, vcol2 = st.columns(2)
            if vcol1.button("✅ Approve", key=f"approve_{vote['id']}"):
                database.resolve_vote(project_name, vote["id"], approved=True)
                st.rerun()
            if vcol2.button("❌ Reject", key=f"reject_{vote['id']}"):
                database.resolve_vote(project_name, vote["id"], approved=False)
                st.rerun()

# ---- Ledger ----
st.header("Venture Audit Ledger & History")
if venture_data.get("transactions"):
    st.table(venture_data["transactions"])
else:
    st.info("No recorded transactions yet.")