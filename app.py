"""
Author: Joshua Smith
Project: BusiCash
Date: 8/15/2026
Description: Main entry point for the Streamlit dashboard application.
Coordinates user identity simulation, venture creation, spending proposals,
and multi-sig co-founder voting.
"""

import streamlit as st
import database as db
import gemini_engine as ge

# Configure Streamlit page options
st.set_page_config(page_title="BusiCash - Student Sandboxing Dashboard", layout="wide")
st.title("💸 BusiCash Sandbox Dashboard")
st.subheader("Automated AI Multi-Sig Governance for Young Founders")

# ==========================================
# 1. SIDEBAR: VENTURE SELECTION & CREATION
# ==========================================
st.sidebar.header("🚀 Ventures")
venture_names = db.list_venture_names()
NEW_VENTURE_LABEL = "➕ Start a New Venture"
venture_options = venture_names + [NEW_VENTURE_LABEL]

# Retain previously selected venture across page reloads
remembered_venture = st.session_state.get("selected_venture")
if remembered_venture in venture_options:
    default_index = venture_options.index(remembered_venture)
elif venture_names:
    default_index = 0
else:
    default_index = len(venture_options) - 1

selected_option = st.sidebar.selectbox("Choose a venture", venture_options, index=default_index)

# Form to initialize a new venture pool
if selected_option == NEW_VENTURE_LABEL:
    st.sidebar.subheader("Create a New Venture Group")
    new_name_input = st.sidebar.text_input("Project / Business Name", value="")
    starting_capital_input = st.sidebar.number_input("Starting Capital Pool ($)", min_value=10, value=1000)
    partners_input = st.sidebar.text_input("Member IDs (comma separated)", value="Founder_Alice, Founder_Bob")
    parsed_members = [name.strip() for name in partners_input.split(",") if name.strip()]

    if st.sidebar.button("Launch Shared Pool"):
        if not new_name_input.strip():
            st.sidebar.error("Provide a name for the venture.")
        elif not parsed_members:
            st.sidebar.error("Add at least one member ID.")
        else:
            db.create_venture(new_name_input, starting_capital_input, parsed_members)
            st.session_state["selected_venture"] = new_name_input
            st.rerun()

    st.info("👈 Fill out the sidebar form and click **Launch Shared Pool** to create your venture.")
    st.stop()

# Set current active venture context
active_venture_name = selected_option
st.session_state["selected_venture"] = active_venture_name
venture_data = db.get_venture(active_venture_name)

if not venture_data:
    st.error("Selected venture could not be loaded.")
    st.stop()

# ==========================================
# 2. SIDEBAR: USER SIMULATION & SETTINGS
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("👤 User Context")
simulated_user = st.sidebar.selectbox(
    "Simulate Logged-in Co-founder:",
    options=venture_data.get("members", ["Founder_Alice", "Founder_Bob", "Founder_Charlie"]),
    key="current_simulated_user"
)

st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ Venture Settings & Danger Zone"):
    st.write(f"Active User: **{simulated_user}**")
    
    # Button: Exit active venture
    if st.button("🚪 Exit Venture", use_container_width=True):
        success, message = db.exit_venture(active_venture_name, simulated_user)
        if success:
            st.success(message)
            st.session_state["selected_venture"] = None
            st.rerun()
        else:
            st.error(message)

    # Button: Permanently delete active venture
    if st.button("🔥 Dissolve & Delete Venture", type="primary", use_container_width=True):
        success, message = db.delete_venture_recursive(active_venture_name)
        if success:
            st.warning(message)
            st.session_state["selected_venture"] = None
            st.rerun()
        else:
            st.error(message)

# ==========================================
# 3. MAIN DASHBOARD OVERVIEW
# ==========================================
st.header(f"📊 {active_venture_name}")
metrics_col1, metrics_col2 = st.columns(2)

with metrics_col1:
    st.metric(label="Remaining Capital Pool", value=f"${venture_data['capital_pool']:,.2f}")
with metrics_col2:
    st.write(f"**Venture Partners:** {', '.join(venture_data['members'])}")

st.divider()

# ==========================================
# 4. PURCHASE PROPOSAL SUBMISSION
# ==========================================
st.subheader("Submit a Purchase Proposal")
input_col1, input_col2 = st.columns([3, 1])

with input_col1:
    item_name_input = st.text_input("Item Name", placeholder="e.g., Marketing Ads, Software Licenses, Tools")
with input_col2:
    cost_input = st.number_input("Cost ($)", min_value=0.01, value=10.0, step=5.0)

justification_input = st.text_area(
    "Why is this essential for the business?",
    placeholder="Describe how this purchase supports project goals...",
)

if st.button("Evaluate with Gemini AI Guardrail"):
    if not item_name_input.strip():
        st.error("Please enter an item name.")
    else:
        with st.spinner("Analyzing proposal against venture goals and budget..."):
            evaluation_context = f"Business: {active_venture_name}, Pool Balance: ${venture_data['capital_pool']:.2f}"
            ai_evaluation = ge.evaluate_spend_proposal(evaluation_context, item_name_input, cost_input, justification_input)

            # Determine compliance status from AI evaluation string
            verdict_status = "REJECTED"
            if "APPROVED" in ai_evaluation.upper():
                verdict_status = "APPROVED"
            elif "REQUIRES" in ai_evaluation.upper() or "VOTE" in ai_evaluation.upper():
                verdict_status = "REQUIRES_COFOUNDER_VOTE"

            db.record_transaction(
                venture_name=active_venture_name,
                item=item_name_input,
                cost=cost_input,
                justification=justification_input,
                verdict=verdict_status,
                explanation=ai_evaluation
            )

            st.subheader("🤖 Gemini Compliance Verdict")
            if verdict_status == "APPROVED":
                st.success(ai_evaluation)
            elif verdict_status == "REQUIRES_COFOUNDER_VOTE":
                st.warning(ai_evaluation)
            else:
                st.error(ai_evaluation)

        st.rerun()

st.divider()

# ==========================================
# 5. MULTI-SIG CO-FOUNDER VOTING SECTION
# ==========================================
st.header("🗳️ Pending Co-Founder Votes")
pending_items = db.get_pending_proposals(active_venture_name)

if not pending_items:
    st.info("No active proposals currently awaiting co-founder approval.")
else:
    for proposal in pending_items:
        display_item = proposal.get("item_name", proposal.get("item", "Unspecified Item"))
        proposal_id = proposal["id"]
        
        with st.expander(f"📌 **{display_item}** — ${proposal['cost']:,.2f} (Proposed by {proposal.get('created_by', 'Co-Founder')})", expanded=True):
            st.write(f"**Justification:** {proposal.get('justification', 'No description provided.')}")
            st.info(f"🤖 **Gemini Analysis:** {proposal.get('ai_analysis', proposal.get('explanation', 'N/A'))}")

            existing_votes = proposal.get("votes", {})
            st.caption(f"Current Votes: {existing_votes if existing_votes else 'No votes cast yet.'}")

            vote_col1, vote_col2 = st.columns(2)
            
            with vote_col1:
                if st.button("✅ Approve", key=f"approve_{proposal_id}"):
                    vote_success, vote_msg = db.cast_vote(active_venture_name, proposal_id, simulated_user, "APPROVE")
                    if vote_success:
                        st.success(vote_msg)
                        st.rerun()
                    else:
                        st.error(vote_msg)

            with vote_col2:
                if st.button("❌ Deny", key=f"deny_{proposal_id}"):
                    vote_success, vote_msg = db.cast_vote(active_venture_name, proposal_id, simulated_user, "DENY")
                    if vote_success:
                        st.warning(vote_msg)
                        st.rerun()
                    else:
                        st.error(vote_msg)

st.divider()

# ==========================================
# 6. VENTURE AUDIT LEDGER
# ==========================================
st.header("📜 Venture Audit Ledger & History")
if venture_data.get("transactions"):
    st.table(venture_data["transactions"])
else:
    st.info("No recorded transactions in the audit ledger yet.")