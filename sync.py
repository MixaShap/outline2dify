#!/usr/bin/env python3

import json
import os
import sys
import time
from pathlib import Path

import requests


# ============================================================
# Configuration
# ============================================================

OUTLINE_URL = os.getenv("OUTLINE_URL", "http://localhost:3000")
OUTLINE_API_KEY = os.getenv("OUTLINE_API_KEY")

DIFY_URL = os.getenv("DIFY_URL", "http://localhost:5001")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")

DIFY_DATASET_ID = os.getenv(
    "DIFY_DATASET_ID",
    "4bffe83f-e069-4bc6-ab15-f6e1921a8d21",
)

# Если указать collection ID — синхронизируем только её.
# Если оставить пустым — синхронизируем все документы, доступные API key.
OUTLINE_COLLECTION_ID = os.getenv("OUTLINE_COLLECTION_ID", "")

STATE_FILE = Path(os.getenv("STATE_FILE", "./outline_dify_state.json"))

REQUEST_TIMEOUT = 30


# ============================================================
# Validation
# ============================================================

if not OUTLINE_API_KEY:
    print("ERROR: OUTLINE_API_KEY is not set")
    sys.exit(1)

if not DIFY_API_KEY:
    print("ERROR: DIFY_API_KEY is not set")
    sys.exit(1)


# ============================================================
# HTTP clients
# ============================================================

outline = requests.Session()
outline.headers.update({
    "Authorization": f"Bearer {OUTLINE_API_KEY}",
    "Content-Type": "application/json",
})

dify = requests.Session()
dify.headers.update({
    "Authorization": f"Bearer {DIFY_API_KEY}",
    "Content-Type": "application/json",
})


# ============================================================
# State
# ============================================================

def load_state():
    if not STATE_FILE.exists():
        return {}

    with STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    tmp_file = STATE_FILE.with_suffix(".tmp")

    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )

    tmp_file.replace(STATE_FILE)


# ============================================================
# Outline API
# ============================================================

def outline_request(endpoint, payload):
    url = f"{OUTLINE_URL.rstrip('/')}/api/{endpoint}"

    response = outline.post(
        url,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok", True):
        raise RuntimeError(
            f"Outline API error: {data}"
        )

    return data


def get_outline_documents():
    """
    Get documents from Outline.

    Handles pagination.
    """

    documents = []
    offset = 0
    limit = 100

    while True:
        payload = {
            "offset": offset,
            "limit": limit,
        }

        if OUTLINE_COLLECTION_ID:
            payload["collectionId"] = OUTLINE_COLLECTION_ID

        result = outline_request(
            "documents.list",
            payload,
        )

        batch = result.get("data", [])

        documents.extend(batch)

        pagination = result.get("pagination", {})

        if not batch:
            break

        # Outline normally returns pagination data.
        if pagination.get("nextPath"):
            offset += limit
        else:
            # Fallback for API versions where nextPath isn't present.
            if len(batch) < limit:
                break

            offset += limit

    return documents


def get_outline_document(document_id):
    return outline_request(
        "documents.info",
        {
            "id": document_id,
        },
    )["data"]


def export_outline_document(document_id):
    result = outline_request(
        "documents.export",
        {
            "id": document_id,
        },
    )

    return result["data"]


# ============================================================
# Dify API
# ============================================================

def dify_request(method, endpoint, **kwargs):
    url = f"{DIFY_URL.rstrip('/')}/v1/{endpoint.lstrip('/')}"

    response = dify.request(
        method,
        url,
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )

    if not response.ok:
        raise RuntimeError(
            f"Dify API error {response.status_code}: "
            f"{response.text}"
        )

    return response.json() if response.content else {}


def dify_create_document(name, text):
    payload = {
        "name": name,
        "text": text,
        "indexing_technique": "high_quality",
        "process_rule": {
            "mode": "automatic"
        },
    }

    return dify_request(
        "POST",
        f"/datasets/{DIFY_DATASET_ID}/document/create-by-text",
        json=payload,
    )


def dify_update_document(document_id, name, text):
    payload = {
        "name": name,
        "text": text,
    }

    return dify_request(
        "POST",
        (
            f"/datasets/{DIFY_DATASET_ID}"
            f"/documents/{document_id}"
            f"/update-by-text"
        ),
        json=payload,
    )


def dify_delete_document(document_id):
    return dify_request(
        "DELETE",
        (
            f"/datasets/{DIFY_DATASET_ID}"
            f"/documents/{document_id}"
        ),
    )


# ============================================================
# Synchronization
# ============================================================

def sync():
    state = load_state()

    print("Loading documents from Outline...")

    outline_documents = get_outline_documents()

    print(
        f"Found {len(outline_documents)} documents in Outline."
    )

    current_ids = set()

    for outline_doc in outline_documents:

        outline_id = outline_doc["id"]
        current_ids.add(outline_id)

        title = outline_doc.get(
            "title",
            "Untitled",
        )

        revision = outline_doc.get(
            "revision"
        )

        previous = state.get(outline_id)

        # ----------------------------------------------------
        # Skip unchanged document
        # ----------------------------------------------------

        if (
            previous
            and previous.get("revision") == revision
        ):
            print(
                f"[SKIP] {title} "
                f"(revision {revision})"
            )
            continue

        print(
            f"[SYNC] {title} "
            f"(revision {revision})"
        )

        try:
            # Get complete document metadata
            document = get_outline_document(
                outline_id
            )

            title = document.get(
                "title",
                title,
            )

            revision = document.get(
                "revision",
                revision,
            )

            # Get Markdown
            markdown = export_outline_document(
                outline_id
            )

            if not markdown.strip():
                print(
                    f"  [WARNING] Empty document: {title}"
                )
                continue

            # ------------------------------------------------
            # CREATE
            # ------------------------------------------------

            if not previous:
                print(
                    f"  Creating in Dify..."
                )

                result = dify_create_document(
                    name=title,
                    text=markdown,
                )

                dify_document = result.get(
                    "document",
                    result.get("data", {}),
                )

                dify_id = dify_document.get(
                    "id"
                )

                if not dify_id:
                    raise RuntimeError(
                        f"Cannot determine Dify "
                        f"document ID from response: "
                        f"{result}"
                    )

                state[outline_id] = {
                    "dify_document_id": dify_id,
                    "revision": revision,
                    "title": title,
                }

                print(
                    f"  Created: {dify_id}"
                )

            # ------------------------------------------------
            # UPDATE
            # ------------------------------------------------

            else:
                dify_id = previous[
                    "dify_document_id"
                ]

                print(
                    f"  Updating Dify document "
                    f"{dify_id}..."
                )

                dify_update_document(
                    document_id=dify_id,
                    name=title,
                    text=markdown,
                )

                state[outline_id][
                    "revision"
                ] = revision

                state[outline_id][
                    "title"
                ] = title

                print(
                    f"  Updated."
                )

            save_state(state)

        except Exception as exc:
            print(
                f"  [ERROR] {title}: {exc}"
            )

    # --------------------------------------------------------
    # Delete documents removed from Outline
    # --------------------------------------------------------

    deleted = (
        set(state.keys()) - current_ids
    )

    for outline_id in deleted:

        entry = state[outline_id]

        dify_id = entry.get(
            "dify_document_id"
        )

        title = entry.get(
            "title",
            outline_id,
        )

        print(
            f"[DELETE] {title}"
        )

        try:
            dify_delete_document(
                dify_id
            )

            del state[outline_id]

            save_state(state)

            print(
                f"  Deleted from Dify."
            )

        except Exception as exc:
            print(
                f"  [ERROR] Delete failed: {exc}"
            )

    print("Sync finished.")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    interval = int(os.getenv("SYNC_INTERVAL", "300"))

    while True:
        try:
            sync()
        except KeyboardInterrupt:
            print("\nInterrupted.")
            sys.exit(130)
        except Exception as exc:
            print(
                f"FATAL: {exc}",
                file=sys.stderr,
            )

        print(
            f"Next sync in {interval} seconds..."
        )

        time.sleep(interval)

