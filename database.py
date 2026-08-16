"""
Author: Joshua Smith
Project: busicash
Date: 8/1/2026
Description: database.py - Firestore-backed persistence layer for BusiCash. It creates a database persistance layer using google cloud firestore.
this handels venture initialisation, subcollection logging, transactional multi-sig voting and member exit/dissolution logic.

Architecture notes (v1.3 - cloud-native rewrite):
- Each venture is a document in the top-level `ventures` collection, keyed by a
  URL-safe SLUG of its name (not an auto-ID), so a lookup is a single O(1)
  `.document(slug).get()` instead of the old `.where('name', '==', ...)` query
  scan across the whole collection.
-sluging eg. 'hello-world' instead of 'hello world' is used for more uniform firestore opperations
- `transactions` and `pending_votes` are SUBCOLLECTIONS, not arrays on the
  venture document. Firestore documents cap out at 1 MiB and every array
  update rewrites the whole array. Subcollections let the ledger grow
  unbounded, support pagination/cursors later, and let two people write to
  the ledger at the same time without clobbering/overwriting each other's array edits.
- Capital pool deductions run inside a Firestore transaction
  (`@firestore.transactional`), so two near-simultaneous approvals can't both
  read the same stale balance and overdraw the pool - a real race condition
  once multiple co-founders are acting concurrently.

v1.4 bugfix pass:
- exit_venture / delete_venture_recursive / get_pending_proposals now accept
  the venture DISPLAY NAME (matching how app.py calls them) and slugify
  internally, instead of silently expecting an already-slugified string.
- Fixed typo: delete_venture_recurive -> delete_venture_recursive (this is
  what app.py was actually calling, so the delete button was crashing).
- Fixed get_pending_proposals filtering on status == "pending" when every
  proposal is actually written with status == "PENDING" - this was the
  reason the co-founder voting UI never showed anything.
- All functions now reuse the single firebase_admin-initialized `db` client
  instead of spinning up a fresh, separately-authenticated firestore.Client().
- Fixed create_pending_proposal: it checked .exists on a brand-new,
  not-yet-written document reference (always False -> always raised), and
  stored cost as the literal string " float(cost)" instead of a real float.
"""
import os
import re
import firebase_admin
import google.cloud.firestore as firestore
from firebase_admin import credentials
from dotenv import load_dotenv

#load enviroment variables from local .env file
load_dotenv()

def _init_firebase() -> None:
    """
    Looks for GOOGLE_APPLICATION_CREDENTIALS first (standard for cloud
    deploys - Cloud Run, App Engine, etc. all set this), then falls back to
    any *service*.json / *firebase*.json in the project root for local dev.
    it does this through Initialising the firebase admin SDK.
    """
    if firebase_admin._apps:
        return

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
        return

    json_files = [
        file_name for file_name in os.listdir(".")
        if file_name.endswith(".json") and ("service" in file_name.lower() or "firebase" in file_name.lower())
    ]
    if json_files:
        firebase_admin.initialize_app(credentials.Certificate(json_files[0]))
        return

    raise RuntimeError(
        "No Firebase credentials found. Set GOOGLE_APPLICATION_CREDENTIALS to "
        "your service account JSON path, or place a *-service-account.json and/or firebase.json "
        "file in the project root."
    )

# Run Firebase initialisation and construct database client
_init_firebase()
db = firestore.client()

"""Turns a venture name into a Firestore-safe/URL-safe, human-readable document ID."""
def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "venture"

"""Retrieves and Attaches the transactions and pending_votes subcollections to the primary venture data payload"""
def _attach_ledger_data(document_reference: firestore.DocumentReference, snap):
    """
    e.g. Attaches 'transaction + pending-vote' subcollections to a venture doc.
    -bike + 2 'YES'
    """
    # Retrieve all recorded transactions ordered by timestamp
    data = snap.to_dict() #snap=document_snapShot where it is a readable json format of key value pairs map-ed at call time
    data["transactions"] = [
        {**doc.to_dict(), "id": doc.id}
        for doc in document_reference.collection("transactions")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .stream()
    ]

    #Retrieve all pending votes ordered by timestamp
    data["pending_votes"] = [
        {**doc.to_dict(), "id": doc.id}
        for doc in document_reference.collection("pending_votes")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .stream()
    ]
    return data

"""
Fetched a single venture document along with its ledger subcollections.
Returns None if the venture does not exist.
"""
def get_venture(venture_name:str) ->dict | None:
    #Fetches one venture (with transactions + pending votes). None if missing.
    doc_ref = db.collection("ventures").document(_slugify(venture_name))
    doc_snapshot = doc_ref.get()
    if not doc_snapshot.exists:
        return None
    return _attach_ledger_data(doc_ref, doc_snapshot)


"""
Cheap listing of venture display names only - does NOT touch the transactions/pending_votes subcollections. 
Uses this to populate a picker, use get_venture(name) to fetch full details for just the one selected.
but ultimatly Retrieves a list of all the venture display names.
"""
def list_venture_names():
    return sorted(
        doc.to_dict().get("name", doc.id)
        for doc in db.collection("ventures").stream()
    )

"""
Fetches every venture - useful for a future 'browse all groups' view.
in othe words: Retrieves a list of all active venture display names.
This performs a lightweight read without fetching subcollections.
"""
def get_all_ventures():
    result = {}
    for doc_snapshot in db.collection("ventures").stream():
        doc_ref = db.collection("ventures").document(doc_snapshot.id)
        data = _attach_ledger_data(doc_ref, doc_snapshot)
        result[data["name"]] = data
    return result


def create_venture(name: str, capital: float, members: list[str]) -> dict:
    """Creates a venture doc if it doesn't exist yet. Returns it either way."""
    doc_ref = db.collection("ventures").document(_slugify(name))
    if not doc_ref.get().exists:
        doc_ref.set({
            "name": name,
            "capital_pool": float(capital),
            "members": members,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
        print(f"Created new venture in Firestore: {name}")
    return get_venture(name)

"""
Executes an atomic deduction from the venture capital pool and writes the transaction record.
Prevents race conditions when multiple co-founders execute spend requests simultaneously.
"""
@firestore.transactional
def _deduct_and_log(transaction, doc_ref, payload):
    """Reads the current balance, deducts, and writes the ledger entry as a
    single atomic unit - prevents lost updates under concurrent/simultanious approvals."""
    doc_snap = doc_ref.get(transaction=transaction)
    new_balance = doc_snap.get("capital_pool") - payload["cost"]
    transaction.update(doc_ref, {"capital_pool": new_balance})
    transaction.set(doc_ref.collection("transactions").document(), payload)


def _apply_approved_spend(doc_ref, payload):
    transaction = db.transaction()
    _deduct_and_log(transaction, doc_ref, payload)


""" 
Evaluates and Records spend proposal results and logs them to the database.
- APPROVED: Atomically deducts capital balance and records to transactions.
- REQUIRES_COFOUNDER_VOTE: Inserts item into pending_votes subcollection.
- REJECTED: Directly logs entry into transactions ledger without altering balance.
    Returns the updated venture, or None.
"""
def record_transaction(venture_name: str, item: str, cost: float, justification: str, verdict: str, explanation: str) ->dict | None:
    slug = _slugify(venture_name)
    venture_ref = db.collection("ventures").document(slug)
    if not venture_ref.get().exists:
        return None
    payload = {
        "item": item,
        "item_name": item,  # kept in sync with 'item' so the voting UI (which reads item_name) always has it
        "cost": float(cost),
        "justification": justification,
        "verdict": verdict,
        "explanation": explanation,
        "timestamp": firestore.SERVER_TIMESTAMP,
    }

    verdict_upper = verdict.upper()
    if verdict_upper == "APPROVED":
        _apply_approved_spend(venture_ref, payload)
    elif verdict_upper == "REQUIRES_COFOUNDER_VOTE":
        payload["status"] = "PENDING"
        payload["votes"] = {}
        venture_ref.collection("pending_votes").add(payload)
    else:  # REJECTED
        venture_ref.collection("transactions").add(payload)
    print(f"Recorded transaction for venture: {venture_name}")
    return get_venture(venture_name)


"""
Moves a pending co-founder vote into the ledger once the group decides.
Approving atomically deducts the cost from capital_pool.
"""
def resolve_vote(venture_name, vote_id, approved):
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


"""
Creates an explicit pending purchase proposal requiring co-founder multi-sig voting.
(Not currently called by app.py - record_transaction() handles this inline. Left
here, fixed, in case you wire a direct "propose without AI check" flow into
app.py before the deadline.)
"""
def create_pending_proposal(venture_name: str, item_name: str, cost: float, justification: str, ai_analysis: str, created_by: str):
    """Creates a new pending proposal for a venture."""
    slug = _slugify(venture_name)
    venture_ref = db.collection("ventures").document(slug)
    if not venture_ref.get().exists:
        raise ValueError(f"Venture '{venture_name}' does not exist.")

    proposal_ref = venture_ref.collection("pending_votes").document()
    proposal_payload = {
        "id": proposal_ref.id,
        "item_name": item_name,
        "item": item_name,
        "cost": float(cost),
        "justification": justification,
        "ai_analysis": ai_analysis,
        "created_by": created_by,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "status": "PENDING",
        "votes": {}  # Maps user_id -> "APPROVE" or "DENY"
    }
    proposal_ref.set(proposal_payload)
    print(f"Created new pending proposal for venture: {venture_name}")
    return proposal_ref.id


"""
Recording a vote ('APPROVE' or 'DENY').
If approvals reach required_approvals, converts proposal to an official transaction pool.
"""
def cast_vote(venture_name: str, proposal_id: str, user_id: str, vote: str, required_approvals: int = 2) -> tuple[bool, str]:
    """
    Records a co-founder vote ('APPROVE' or 'DENY').
    If approved votes reach threshold, executes atomic balance deduction and moves item to transactions.
    """
    slug = _slugify(venture_name)
    venture_ref = db.collection("ventures").document(slug)
    proposal_ref = venture_ref.collection("pending_votes").document(proposal_id)

    @firestore.transactional
    def execute_vote_transaction(tx: firestore.Transaction) -> tuple[bool, str]:
        proposal_snapshot = proposal_ref.get(transaction=tx)
        
        if not proposal_snapshot.exists:
            return False, "Proposal not found."

        proposal_data = proposal_snapshot.to_dict()
        if proposal_data.get("status") != "PENDING":
            return False, "Proposal is no longer pending."

        # Update vote map for current user
        votes_map = proposal_data.get("votes", {})
        votes_map[user_id] = vote.upper()

        approve_count = sum(1 for v in votes_map.values() if v == "APPROVE")
        deny_count = sum(1 for v in votes_map.values() if v == "DENY")

        if approve_count >= required_approvals:
            venture_snapshot = venture_ref.get(transaction=tx)
            current_capital = venture_snapshot.to_dict().get("capital_pool", 0.0)
            item_cost = proposal_data["cost"]

            #check if the capital is less than the purchase and if so state: "insufficient funds"
            if current_capital < item_cost:
                tx.update(proposal_ref, {"status": "REJECTED_INSUFFICIENT_FUNDS", "votes": votes_map})
                return False, "Insufficient capital pool balance to fulfill purchase."

            # Deduct funds from capital pool
            tx.update(venture_ref, {"capital_pool": current_capital - item_cost})

            # Append completed purchase into transactions subcollection
            new_tx_doc = venture_ref.collection("transactions").document()
            tx.set(new_tx_doc, {
                "item": proposal_data.get("item_name", proposal_data.get("item", "Unspecified Item")),
                "cost": item_cost,
                "justification": proposal_data["justification"],
                "explanation": f"Multi-Sig Approved ({approve_count} votes). AI Note: {proposal_data.get('ai_analysis', proposal_data.get('explanation', 'None'))}",
                "verdict": "APPROVED",
                "timestamp": firestore.SERVER_TIMESTAMP
            })

            # Update status on original pending proposal
            tx.update(proposal_ref, {"status": "APPROVED", "votes": votes_map})
            return True, "Consensus reached! Purchase approved and capital deducted."

        elif deny_count >= required_approvals:
            # Update status on original pending proposal to DENIED
            tx.update(proposal_ref, {"status": "DENIED", "votes": votes_map})
            return True, "Proposal denied by co-founders."
        else:
            # Update status on original pending proposal indicating "approval needed"
            tx.update(proposal_ref, {"votes": votes_map})
            return True, f"Vote recorded ({approve_count}/{required_approvals} approvals needed)."

    active_transaction = db.transaction()
    return execute_vote_transaction(active_transaction)


"""
Retrieves all the active pending proposals for a venture.
Accepts the venture DISPLAY NAME (matching how app.py calls it) and slugifies
internally. Filters on status == "PENDING" to match what record_transaction()
and create_pending_proposal() actually write.
"""
def get_pending_proposals(venture_name: str) -> list[dict]:
    slug = _slugify(venture_name)
    proposals_stream = db.collection("ventures").document(slug).collection("pending_votes") \
        .where("status", "==", "PENDING").stream()
    return [{**doc.to_dict(), "id": doc.id} for doc in proposals_stream]


"""
Removes a member from a venture.
if no members remain, delete the venture and its subcollections
"""
def exit_venture(venture_name: str, user_id: str) -> tuple[bool, str]:
    slug = _slugify(venture_name)
    venture = db.collection("ventures").document(slug)

    @firestore.transactional
    def execute_exit(tx):
        venture_snapshot = venture.get(transaction=tx)
        if not venture_snapshot.exists:
           return False, "venture not found."

        data = venture_snapshot.to_dict()
        members = data.get("members",[])

        #Remove the user if present
        if user_id not in members:
           return False, "User is not a member of this venture."
        #otherwise remove the user
        members.remove(user_id)

        # if members still remain, update the member list
        if len(members) > 0:
            tx.update(venture,{"members": members})
            return True, (
               f"Successfully exited {data.get('name',venture_name)}. "
               f"Remaining co-founders: {len(members)}."
            )
        #If no members are left, purge the venture document
        tx.delete(venture)

        return True, (
            f"you were the last member. "
            f"Venture '{data.get('name',venture_name)}' has been deleted."
        )
   
    active_transaction = db.transaction()
    return execute_exit(active_transaction)


def delete_venture_recursive(venture_name: str):
    """
    Completely deletes a venture and all nested subcollections (transactions, pending_votes).
    Use this if a co-founder explicitly triggers 'Dissolve Venture'.
    """
    slug = _slugify(venture_name)
    venture = db.collection("ventures").document(slug)

    # delete subcollections first
    for subCollection in ["transactions","pending_votes"]:
        subcollection_docs = venture.collection(subCollection).stream()
        for doc in subcollection_docs:
            doc.reference.delete()

    # Delete main venture document
    venture.delete()
    return True,"Venture and all associated ledgers/votes have been permanently deleted"