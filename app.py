"""
Author: Joshua Smith
Project: busicash
Date: 8/1/2026
Description: this app.py will be the entry point to the app that will biuld a dashboard
"""
""" version 1.1 """
import streamlit as st
import database
import gemini_engine

st.set_page_config(page_title="BusiCash - Student Sandboxing Dashboard", layout="wide")

st.title("💸 BusiCash Sandbox Dashboard")
st.subheader("Automated AI Multi-Sig Governance for Young Founders")

# Sidebar to create a new collaborative project
st.sidebar.header("🚀 Create a New Venture Group")
project_name = st.sidebar.text_input("Project / Business Name", value="Electric Scooter Rental")
starting_capital = st.sidebar.number_input("Starting Capital Pool ($)", min_value=10, value=3000)
partner_ids = st.sidebar.text_input("Member IDs (comma separated)", value="Joshua, Friend1")

if st.sidebar.button("Launch Shared Pool"):
    members_list = [name.strip() for name in partner_ids.split(",")]
    new_id = database.create_mock_project(project_name, starting_capital, members_list)
    st.sidebar.success(f"Project Created Live! ID: {new_id}")

# Main Window displaying active portfolios
st.header("📊 Active Group Portfolios")
active_projects = database.get_projects()

if not active_projects:
    st.info("No active projects found yet. Use the sidebar to deploy your first joint venture project pool!")
else:
    for proj in active_projects:
        with st.expander(f"📁 {proj['name']} — Capital Pool: ${proj['total_balance']:,}", expanded=True):
            st.write("**Venture Partners:**", ", ".join(proj['members']))
            
            st.markdown("---")
            st.markdown("#### 🛒 Submit a Purchase Proposal")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                item_name = st.text_input(f"Item Name ({proj['name']})", key=f"item_{proj['id']}")
                justification = st.text_area("Why is this essential for the business?", key=f"just_{proj['id']}")
            with col2:
                amount = st.number_input("Cost ($)", min_value=1, value=150, key=f"cost_{proj['id']}")
                submit_btn = st.button("Evaluate with Gemini AI Guardrail", key=f"btn_{proj['id']}")

            if submit_btn and item_name and justification:
                with st.spinner("Gemini AI is evaluating proposal against project goals..."):
                    context = f"Business: {proj['name']}, Pool Balance: ${proj['total_balance']}"
                    verdict = gemini_engine.evaluate_spend_proposal(
                        project_context=context,
                        item_name=item_name,
                        amount=amount,
                        justification=justification
                    )
                    
                    st.markdown("### 🤖 Gemini Compliance Verdict")
                    st.info(verdict)

