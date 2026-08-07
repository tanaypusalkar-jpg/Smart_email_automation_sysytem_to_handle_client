"""
Lightweight RAG layer.

Stores past email templates/sent emails in a local Chroma vector store,
and retrieves the closest matches to use as style/context reference when
drafting a new email.
"""

import logging
import uuid
import chromadb

from app.config import get_settings

logger = logging.getLogger("email_automation.rag")

settings = get_settings()
_collection = None


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=settings.vector_db_path)
        _collection = client.get_or_create_collection(name="email_templates")
    return _collection


def seed_default_templates() -> None:
    """Populate a few starter templates so the demo works out of the box."""
    collection = get_collection()
    if collection.count() > 0:
        return

    starters = [
        {
            "title": "Follow-up after no response",
            "body": (
                "Hi {name},\n\nJust floating this back to the top of your inbox in case it got "
                "buried. Happy to answer any questions or jump on a quick call this week.\n\n"
                "Best,\n{sender}"
            ),
            "tags": "follow-up,sales",
        },
        {
            "title": "Declining a request politely",
            "body": (
                "Hi {name},\n\nThanks for thinking of me for this. I won't be able to take it on "
                "right now, but I wanted to let you know quickly rather than leave you waiting.\n\n"
                "Best,\n{sender}"
            ),
            "tags": "decline,support",
        },
        {
            "title": "Meeting confirmation",
            "body": (
                "Hi {name},\n\nConfirming our meeting on {date} at {time}. I'll send a calendar "
                "invite separately - let me know if anything needs to shift.\n\nBest,\n{sender}"
            ),
            "tags": "scheduling,personal",
        },
    ]
    for item in starters:
        add_template(item["title"], item["body"], item["tags"].split(","))
    logger.info("Seeded %d default templates into vector store.", len(starters))


def add_template(title: str, body: str, tags: list[str]) -> str:
    collection = get_collection()
    doc_id = str(uuid.uuid4())
    collection.add(
        ids=[doc_id],
        documents=[f"{title}\n{body}"],
        metadatas=[{"title": title, "tags": ",".join(tags)}],
    )
    return doc_id


def retrieve_similar(query: str, top_k: int = 2) -> list[str]:
    """
    Return the top_k most similar template bodies for the given query.

    Fails soft: if the vector store or its embedding model is unavailable
    (e.g. blocked network), composing an email should still work - it just
    won't have retrieved style context.
    """
    try:
        collection = get_collection()
        if collection.count() == 0:
            return []
        results = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))
        return results.get("documents", [[]])[0]
    except Exception:
        logger.exception("RAG retrieval failed - continuing without context.")
        return []
