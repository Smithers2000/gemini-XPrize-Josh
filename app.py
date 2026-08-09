"""
Author: Joshua Smith
Project: busicash
Date: 8/1/2026
Description: this app.py will be the entry point to the app that will build a dashboard
"""
""" version 1.1 """
import streamlit as st
import database 
import gemini_engine as ge

st.set_page_config(page_title="BusiCash - Student Sandboxing Dashboard", layout="wide")

st.title("💸 BusiCash Sandbox Dashboard")
st.subheader("Automated AI Multi-Sig Governance for Young Founders")

# Sidebar to create a new collaborative project
st.sidebar.header("🚀 Create a New Venture Group")
project_name = st.sidebar.text_input("Project / Business Name", value="Electric Scooter Rental")
starting_capital = st.sidebar.number_input("Starting Capital Pool ($)", min_value=10, value=3000)
partner_ids = st.sidebar.text_input("Member IDs (comma separated)", value="Joshua, Friend1, Friend2")

if st.sidebar.button("Launch Shared Pool"):
    members_list = [name.strip() for name in partner_ids.split(",")]
    created_venture = database.create_or_update_venture(project_name, starting_capital, members_list)
    if created_venture:
        st.sidebar.success(f"Project Active in Firestore! ID: {created_venture.get('id')}")
    else:
        st.sidebar.error("Failed to create venture. Please check connection to Firestore or service account key.")    

# Main Window displaying active portfolios
st.header("📊 Active Group Portfolios")

venture_data = database.get_venture_by_name(project_name)
if not venture_data:
    members = [m.strip() for m in partner_ids.split(",")]
    venture_data = database.create_or_update_venture(project_name, starting_capital, members)

if venture_data:
    # Display Capital Metrics
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Remaining Capital Pool", value=f"${venture_data['capital_pool']:,.2f}")
    with col2:
        st.write(f"**Venture Partners:** {', '.join(venture_data['members'])}")

    st.divider()

    # Purchase Proposal Form
    st.subheader("Submit a Purchase Proposal")
    p_col1, p_col2 = st.columns([3, 1])
    with p_col1:
        item_name = st.text_input("Item Name", placeholder="e.g., Marketing Ads, Helmets, Software License")
    with p_col2:
        cost = st.number_input("Cost ($)", min_value=0.0, value=1.0, step=10.0)

    justification = st.text_area("Why is this essential for the business?", placeholder="Describe how this purchase directly supports venture goals...")

    if st.button("Evaluate with Gemini AI Guardrail"):
        with st.spinner("Analyzing proposal against business scope and budget..."):
            ai_response = ge.evaluate_spend_proposal(project_name, item_name, cost, justification)

        # Extract verdict direction
        verdict = "REJECTED"
        if "APPROVED" in ai_response.upper():
            verdict = "APPROVED"
        elif "REQUIRES" in ai_response.upper() or "VOTE" in ai_response.upper():
            verdict = "REQUIRES_COFOUNDER_VOTE"

        # Update database
        updated_venture = database.record_transaction(project_name, item_name, cost, justification, verdict, ai_response)

        st.subheader("🤖 Gemini Compliance Verdict")
        if verdict == "APPROVED":
            st.success(ai_response)
        elif verdict == "REQUIRES_COFOUNDER_VOTE":    
            st.warning(ai_response)
        else:
            st.error(ai_response)

        st.rerun()

    # Ledger section
    st.divider()
    st.header("Venture Audit Ledger & History")
    if venture_data.get("transactions"):
        st.table(venture_data["transactions"])
    else:
        st.info("No recorded transactions yet.")
else:
    st.error("Could not initialize database document for this venture. Verify Firebase Service Account credentials.")       

#/////////////////////////////////////////////////////////////////                  
    """ (inner context example of background)
    context = f"Business: {venture_data['name']}, Pool Balance: ${venture_data['capital_pool']}"
    verdict = ge.evaluate_spend_proposal(
        project_context=context,
        item_name=item_name,
        amount=cost,
        justification=justification
    )
    st.markdown("### 🤖 Gemini Compliance Verdict")
    st.info(verdict)"""