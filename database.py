#this file will manage initialising firebase and pulling data
import os
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Load your local secrets from the .env file
load_dotenv()

# Find the service account json file automatically in your directory
json_files = [f for f in os.listdir('.') if f.endswith('.json')]
if not json_files:
    raise FileNotFoundError("Could not find your Firebase service account JSON file.")

# Use the first JSON file found to initialize the SDK
cred = credentials.Certificate(json_files[0])
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Connect to the cloud Firestore database
db = firestore.client()

def create_mock_project(project_name, total_balance, members):
    """Creates a project in the Firestore cloud database."""
    project_ref = db.collection('projects').document()
    project_ref.set({
        'name': project_name,
        'total_balance': total_balance,
        'members': members
    })
    return project_ref.id

def get_projects():
    """Fetches all existing collaborative projects from the database."""
    projects = []
    docs = db.collection('projects').stream()
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        projects.append(data)
    return projects