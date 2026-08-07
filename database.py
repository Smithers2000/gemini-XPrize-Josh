"""
Author: Joshua Smith
Project: busicash
Date: 8/1/2026
Description: this database.py will manage initializing Firebase and pulling data
"""
import os
import firebase_admin
import json
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

DB_FILE = "ventures_db.json"

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

def load_db():
    """Loads the database from a local JSON file."""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}

def save_db(data):
    """Saves the database to a local JSON file."""
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_venture_by_name(venture_name):
    """Fetches a venture by name from the database."""
    """ (INTERNAL WORKINGS)
    docs = db.collection('projects').where('name', '==', venture_name).stream()
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None
    """
    db = load_db()
    return db.get(venture_name, None)

def create_or_update_venture(name, capital, members):
    """Creates or updates a venture in the database."""
    db = load_db()
    if name not in db:
        db[name] = {
            "capital_pool": float(capital),
            "members": members,
            "transactions": [],
            "pending_votes": []
        }
        save_db(db)
        return db[name]
    """ (INTERNAL WORKINGS)
    venture = get_venture_by_name(name)
    if venture:
        # Update existing venture
        venture_ref = db.collection('projects').document(venture['id'])
        venture_ref.update({
            'total_balance': capital,
            'members': members
            ...
        })
    else:
        # Create new venture
        create_mock_project(name, capital, members)
        """ 

def record_transaction(venture_name, item, cost,justification,verdist,exlpination):
    """Records a transaction in the venture's history."""
    db = load(db)
    if ventureName_db:
        transaction = {
            "item": item,
            "cost": float (cost),
            "justification": justification,
            "verdict": verdict,
            "explination":explination
        }

        #deduct the balance from the capital pool if approved by the AI
        if "APPROVED" in verdict.upper() and "REQUEST" not in verdict.upper():
            db[venture_name]["capital_pool"] -= float(cost)
            db[venture_name]["transactions"].append(transaction)
        elif "REQUIRES" in verdict.upper():
            db[venture_name]["pending_votes"].append(transaction)
        else:     
            db[venture_name]["transactions"].append(transaction)

        save_db(db)
        return db[venture_name]
    return None    

        