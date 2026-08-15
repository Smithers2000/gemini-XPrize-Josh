"""
Author: Joshua Smith
Project: busicash
Date: 8/1/2026
Description: database.py - Firestore-backed persistence layer for BusiCash.

Architecture notes (v1.3 - cloud-native rewrite):
- Each venture is a document in the top-level `ventures` collection, keyed by a
  URL-safe SLUG of its name (not an auto-ID), so a lookup is a single O(1)
  `.document(slug).get()` instead of the old `.where('name', '==', ...)` query
  scan across the whole collection.
- `transactions` and `pending_votes` are SUBCOLLECTIONS, not arrays on the
  venture document. Firestore documents cap out at 1 MiB and every array
  update rewrites the whole array. Subcollections let the ledger grow
  unbounded, support pagination/cursors later, and let two people write to
  the ledger at the same time without clobbering each other's array edits.
- Capital pool deductions run inside a Firestore transaction
  (`@firestore.transactional`), so two near-simultaneous approvals can't both
  read the same stale balance and overdraw the pool - a real race condition
  once multiple co-founders are acting concurrently.
"""
import os
import re
import firebase_admin
import google.cloud.firestore as firestore
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

load_dotenv()

def _init_firebase():
    """Looks for GOOGLE_APPLICATION_CREDENTIALS first (standard for cloud
    deploys - Cloud Run, App Engine, etc. all set this), then falls back to
    any *service*.json / *firebase*.json in the project root for local dev."""
    if firebase_admin._apps:
        return

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
        return

    json_files = [
        f for f in os.listdir(".")
        if f.endswith(".json") and ("service" in f.lower() or "firebase" in f.lower())
    ]
    if json_files:
        firebase_admin.initialize_app(credentials.Certificate(json_files[0]))
        return

    raise RuntimeError(
        "No Firebase credentials found. Set GOOGLE_APPLICATION_CREDENTIALS to "
        "your service account JSON path, or place a *-service-account.json "
        "file in the project root."
    )


_init_firebase()
db = firestore.client()


def _slugify(name: str) -> str:
    """Turns a venture name into a Firestore-safe, human-readable document ID."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "venture"


def _attach_ledger_data(ref, snap):
    """Attaches transaction + pending-vote subcollections to a venture doc."""
    data = snap.to_dict()
    data["transactions"] = [
        {**doc.to_dict(), "id": doc.id}
        for doc in ref.collection("transactions")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .stream()
    ]
    data["pending_votes"] = [
        {**doc.to_dict(), "id": doc.id}
        for doc in ref.collection("pending_votes")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .stream()
    ]
    return data


def get_venture(venture_name):
    """Fetches one venture (with transactions + pending votes). None if missing."""
    ref = db.collection("ventures").document(_slugify(venture_name))
    snap = ref.get()
    if not snap.exists:
        return None
    return _attach_ledger_data(ref, snap)


def list_venture_names():
    """Cheap listing of venture display names only - does NOT touch the
    transactions/pending_votes subcollections. Use this to populate a picker;
    use get_venture(name) to fetch full details for just the one selected."""
    return sorted(
        doc.to_dict().get("name", doc.id)
        for doc in db.collection("ventures").stream()
    )


def get_all_ventures():
    """Fetches every venture - useful for a future 'browse all groups' view."""
    result = {}
    for snap in db.collection("ventures").stream():
        ref = db.collection("ventures").document(snap.id)
        data = _attach_ledger_data(ref, snap)
        result[data["name"]] = data
    return result


def create_venture(name, capital, members):
    """Creates a venture doc if it doesn't exist yet. Returns it either way."""
    ref = db.collection("ventures").document(_slugify(name))
    if not ref.get().exists:
        ref.set({
            "name": name,
            "capital_pool": float(capital),
            "members": members,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
        print(f"Created new venture in Firestore: {name}")
    return get_venture(name)


@firestore.transactional
def _deduct_and_log(transaction, ref, payload):
    """Reads the current balance, deducts, and writes the ledger entry as a
    single atomic unit - prevents lost updates under concurrent approvals."""
    snap = ref.get(transaction=transaction)
    new_balance = snap.get("capital_pool") - payload["cost"]
    transaction.update(ref, {"capital_pool": new_balance})
    transaction.set(ref.collection("transactions").document(), payload)


def _apply_approved_spend(ref, payload):
    transaction = db.transaction()
    _deduct_and_log(transaction, ref, payload)


def record_transaction(venture_name, item, cost, justification, verdict, explanation):
    """Records a spend proposal's outcome. APPROVED atomically deducts from
    capital_pool; REQUIRES_COFOUNDER_VOTE goes to pending_votes; REJECTED is
    logged straight to the ledger. Returns the updated venture, or None."""
    ref = db.collection("ventures").document(_slugify(venture_name))
    if not ref.get().exists:
        return None

    payload = {
        "item": item,
        "cost": float(cost),
        "justification": justification,
        "verdict": verdict,
        "explanation": explanation,
        "timestamp": firestore.SERVER_TIMESTAMP,
    }

    verdict_upper = verdict.upper()
    if verdict_upper == "APPROVED":
        _apply_approved_spend(ref, payload)
    elif verdict_upper == "REQUIRES_COFOUNDER_VOTE":
        ref.collection("pending_votes").add(payload)
    else:  # REJECTED
        ref.collection("transactions").add(payload)

    print(f"Recorded transaction for venture: {venture_name}")
    return get_venture(venture_name)


def resolve_vote(venture_name, vote_id, approved):
    """Moves a pending co-founder vote into the ledger once the group decides.
    Approving atomically deducts the cost from capital_pool."""
    ref = db.collection("ventures").document(_slugify(venture_name))
    vote_ref = ref.collection("pending_votes").document(vote_id)
    vote_snap = vote_ref.get()
    if not vote_snap.exists:
        return None

    vote = vote_snap.to_dict()
    vote["verdict"] = "APPROVED (co-founder vote)" if approved else "REJECTED (co-founder vote)"

    if approved:
        transaction = db.transaction()
        _deduct_and_log(transaction, ref, vote)
    else:
        ref.collection("transactions").add(vote)

    vote_ref.delete()
    return get_venture(venture_name)

def create_pending_proposal(venture: str, item_name: str, cost: float, justification: str, ai_analysis: str, created_by: str):
    # i did up to here
    """Creates a new pending proposal for a venture."""
    db = firestore.client()
    proposal = db.collection("ventures").document(venture).collection("pending_votes").document()
    if not proposal.get().exists:
        raise ValueError(f"Venture '{venture}' does not exist.")

    payload = {
        "id": proposal.id,
        "item_name": item_name,
        "cost":" float(cost)",
        "justification": justification,
        "ai_analysis": ai_analysis,
        "created_by": created_by,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "status": "PENDING",
        "votes": {} #Maps user_id -> "APPROVE" or "DENY"
    }
    proposal.set(proposal_data)
    print(f"Created new pending proposal for venture: {venture}")
    return proposal.id


"""
Recording a vote ('APPROVE' or 'DENY').
If approvals reach required_approvals, converts proposal to an official transaction pool.
"""
def cast_vote(venture:str, proposal_id: str, user_id: str, vote: str,required_approvals: int = 2):
    db = firestore.client()
    venture = db.collection("ventures").document(venture)
    proposal = venture.collection("pending_votes").document(proposal_id)

    @firestore.transactional
    def execute_vote(transaction):
        prop_doc = proposal.get(transaction=transaction)
        if not prop_doc.exists:
            return false, "Proposal not found."

        prop_data = prop_doc.to_dict()
        if prop_data.get("status") != "PENDING":
            return False, "Proposal is no longer pending."

        # Record or updating user vote
        votes = prop_data.get("votes",{})
        votes[user_id] = vote.upper()

        approve_count = sum(1 for v in votes.values() if v == "APPROVE")
        deny_count = sum(1 for v in votes.values() if v == "DENY")

        # check if consensus threshold is reached
        if approve_count >= required_approvals:
            #check venture capital pool balance
            venture_doc = venture.get(transaction = transaction)
            current_capital = venture_doc.to_dict().get("capital_pool",0.0)
            cost = prop_data["cost"]

        
            if current_capital < cost:
                #TODO? continue here next time
                transaction.update({"status:" "REJECTED_INSUFFICIENTFUNDS","votes": votes})
                return False, "Insufficient capital pool balance."

            # Deduct from capiutal pool
            transaction.update(proposal, {"capital_pool":currentcapital-cost})

            # Record in transactions subcollection
            transaction = venture.collection("transactions").document()
            transaction.set({
                "item": prop_data["item_name"],
                "cost": cost,
                "justification":prop_data["justification"],
                "explination": f"mult-sig Concensus Approved ({approve_count} votes). AI Note: {prop_data['ai_analysis']}",
                "verdict": "APPROVED"
                "timestamp": firestore.SERVER_TIMESTAMP
            }, transaction = transaction)    

            # Mark proposal as approved
            transaction.update(proposal,{"status": "APPROVED", "votes": votes})
            return True, "Consensus reached! purchase approved and recorded."

        elif deny_count >= required_approvals:
            transaction.update(proposal,{"status": "DENIED", "votes": votes})
            return true, "proposal denied by co-founders."
        else:
            #still pending more votes
            transaction.update(proposal,{"votes": votes})
            return true, f"Vote recorded ({approve_count}/required_approvals} approvals)."

    transaction = db.transaction()
    return execute_vote(transaction)


"""
Retrives all the active pending proposals for a venture.
"""
def get_pending_proposals(venture_slug: str):
    
    db=firestore.Client()
    props = db.collection("ventures").document(venture_slug).collection("pending_votes")\
        .where("status","==","pending").stream()
return[p.to_dict() for p in props]


"""
Removes a member form a venture.
if no members remain,delete the venture and its subcollections
"""
def exit_venture(venture_slug:str, user_id:str):
   db = friestore.CLient()
   venture = db.collection("ventures").document(venture_slug)

   @firstore.transactional
   def execute_exit(transaction):
        doc = venture.get(transaction = transaction)
        if not doc.exists:
           return False, "venture not found."

        data = doc.to_dict()
        members = data.get("members",[])

       #Remove the user if present
        if user_ID in members:
           members.remove(User_id)

        # if members still remain, update the member list
        if len(members) > 0:
           transaction.update(venture,{"members": members})
           return True, f"Successfully exited {data.get('name',venture_slug)}. Remaining co-founders: {len(members)}."

        #If no members are left, purge the venture document
        transaction.delete(venture)
        return Ture, f"you were the last member. Venture '{data.get('name',venture_slug)}' has been deleted."

    transaction = db.transaction()
    return execute_exit(tranaction)

def delete_venture_recurive( venture_slug: str):
    """
    Completely deletes a venture and all nested subcollections (transactions, pending_votes).
    Use this if a co-founder explicitly triggers 'Dissolve Venture'.
    """
    db= firestore.Client()
    venture = db.collection("ventures").document(venture_slug)

    # delete subcollections first
    for subColl in ["transactions","pending_votes"]:
        docs = venture.collection(subcoll).stream()
        for d in docs:
            d.reference.delete()

    # Delete main venture document
    venture.delete()
    return True,"venture and all associated ledgers/votes have been permanently deleted"        


      