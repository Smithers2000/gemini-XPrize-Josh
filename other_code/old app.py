""" version 1.0 ///
#this is the main entry point where i will build a simple, clean app dashboard
import streamlit as st
import database

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

# Main Window displaying current tracked projects
st.header("📊 Active Group Portfolios")
active_projects = database.get_projects()

if not active_projects:
    st.info("No active projects found yet. Use the sidebar to deploy your first joint venture project pool!")
else:
    for proj in active_projects:
        with st.container():
            st.markdown(f"### 📁 {proj['name']}")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Shared Capital", f"${proj['total_balance']:,}")
            with col2:
                st.write("**Venture Partners:**", ", ".join(proj['members']))
            st.divider()
"""