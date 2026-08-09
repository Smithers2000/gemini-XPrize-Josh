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

# Load your local secrets from the .env file
load_dotenv()

# Find the service account json file automatically in your directory
json_files = [f for f in os.listdir('.') if f.endswith('.json') and ('service' in f.lower() or 'firebase' in f.lower())]
if not json_files:
    json_files = [f for f in os.listdir('.') if f.endswith('.json')]

# Use the first JSON file found to initialize the SDK
if json_files and not firebase_admin._apps:
    cred = credentials.Certificate(json_files[0])
    firebase_admin.initialize_app(cred)

# Connect to the cloud Firestore database
db = firestore.client() if firebase_admin._apps else None

def get_venture_by_name(venture_name):
    """Fetches a venture by name directly from cloud firestorefrom the database."""
    if not db:
        print("Firestore not initialized.")
        return None

    print(f"Searching for venture: {venture_name}")
    docs = db.collection('projects').where('name', '==', venture_name).limit(1).stream()
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None
    
def create_or_update_venture(name, capital, members):
    """Creates or updates a venture in the database. if document is in Firestore it returns the existing one., if it doesn't exist it it returns none."""
    if not db:
        print("Firestore not initialized.")
        return None

    venture = get_venture_by_name(name)
    if venture:
        return venture

    doc_ref = db.collection('projects').document()
    new_venture = {
        "name": name,
        "capital_pool": float(capital),
        "members": members,
        "transactions": [],
        "pending_votes": []
    }
    doc_ref.set(new_venture)
    new_venture['id'] = doc_ref.id
    print(f"Created new venture in Firestore with ID: {doc_ref.id}")
    return new_venture

def record_transaction(venture_name, item, cost, justification, verdict, explanation):
    #Records a transaction in the venture's history.
    #Updates venture document in Cloud Firestore with new purchase transaction and updated balance.
    if not db:
        print("Firestore not initialized.")
        return None

    venture = get_venture_by_name(venture_name)
    if not venture:
        print(f"Venture not found: {venture_name}")
        return None

    document = db.collection('projects').document(venture['id'])
    transaction = {
                "item": item,
                "cost": float(cost),
                "justification": justification,
                "verdict": verdict,
                "explanation": explanation
            }

    capital_pool = float(venture.get("capital_pool",0.0))
    transactions = venture.get("transactions",[])
    pending_votes = venture.get("pending_votes",[])        

    # Deduct the balance from the capital pool if approved by the AI
    if "APPROVED" in verdict.upper() and "REQUIRES" not in verdict.upper():
        capital_pool -= float(cost)
        transactions.append(transaction)
    elif "REQUIRES" in verdict.upper():
        pending_votes.append(transaction)
    else:     
        transactions.append(transaction)

    # Update the venture document in Firestore
    document.update({
        "capital_pool": capital_pool,
        "transactions": transactions,
        "pending_votes": pending_votes
    })

    venture["capital_pool"] = capital_pool
    venture["transactions"]=transactions
    venture["pending_votes"]=pending_votes
    print(f"Recorded transaction for venture '{venture_name}': {transaction}")
    return venture
   
""" for local testing, you can use a JSON file to simulate the database. This is useful for development without needing to connect to Firestore.
#Creates a project in the Firestore cloud database.
def create_mock_project(project_name, total_balance, members):
    if db:
        project = db.collection('projects').document()
        project.set({
            'name': project_name,
            'total_balance': total_balance,
            'members': members
        })
        print(f"Created project '{project_name}' with ID: {project.id}")
        return project.id
    return "local_mock_id"

def get_projects():
    # Fetches all existing collaborative projects from the database.
    projects = []
    if db:
        docs = db.collection('projects').stream()
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            projects.append(data)
            print(f"Fetched project: {data['name']} with ID: {doc.id}")
    return projects

def load_db():
    # Loads the database from a local JSON file.
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try:
                print("Loading database from JSON file.")
                return json.load(f)
            except json.JSONDecodeError:
                print("Error decoding JSON file.")
                return {}
    print("ventures_db.json does not exist yet. Initializing new database dictionary.")        
    return {}

def save_db(data):
    # Saves the database to a local JSON file.
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)
"""




