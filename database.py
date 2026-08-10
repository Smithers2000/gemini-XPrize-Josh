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


def attech_ledger_data(ref, snap):
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
    return _hydrate(ref, snap)


def get_all_ventures():
    """Fetches every venture - useful for a future 'browse all groups' view."""
    result = {}
    for snap in db.collection("ventures").stream():
        ref = db.collection("ventures").document(snap.id)
        data = _hydrate(ref, snap)
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