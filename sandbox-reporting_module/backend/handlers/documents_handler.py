from uuid import uuid4
from datetime import datetime, timezone
from fastapi import HTTPException, UploadFile
from typing import Optional
from pydantic import BaseModel
import base64

from backend.security.auth import EnterpriseContext

import os
import tempfile
from markitdown import MarkItDown
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "agent_folder"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
(UPLOAD_DIR / "input").mkdir(exist_ok=True)
(UPLOAD_DIR / "output").mkdir(exist_ok=True)
(UPLOAD_DIR / "workspace").mkdir(exist_ok=True)

_documents: dict[str, dict] = {}
_document_content: dict[str, str] = {}

class WordAddinPayload(BaseModel):
    filename: Optional[str] = "output.md"
    filepath: Optional[str] = "output"
    document_base64: Optional[str] = None
    document_text: Optional[str] = None

def read_word_with_markitdown(file_bytes: bytes) -> str:
    md = MarkItDown()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        tmp_path = tmp.name

    try:
        result = md.convert(tmp_path)
        return result.text_content
    except Exception as e:
        print("MARKITDOWN ERROR:", e)
        raise
    finally:
        os.remove(tmp_path)

def _store_document(enterprise_id: str, filename: str, text: str) -> dict:
    """Common storage logic shared by both upload paths."""
    document_id = str(uuid4())

    _documents[document_id] = {
        "document_id": document_id,
        "enterprise_id": enterprise_id,
        "filename": filename,
        "created_at": datetime.now(timezone.utc),
    }
    _document_content[document_id] = text

    return {"document_id": document_id, "filename": filename}

async def upload_document(file: UploadFile, enterprise: EnterpriseContext):
    """Traditional multipart file upload (existing flow, unchanged behaviour)."""
    content = await file.read()

    filename = file.filename or "unknown"
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    if ext in ["docx", "doc"]:
        try:
            text = read_word_with_markitdown(content)
            file_path = os.path.join(UPLOAD_DIR, filename)
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to parse Word document")
    else:
        text = content.decode("utf-8", errors="ignore")

    return _store_document(enterprise.enterprise_id, filename, text)

async def upload_document_from_addin(payload: WordAddinPayload, enterprise: EnterpriseContext):
    """
    Supports: Base64 .docx (document_base64) and Plain text (document_text)
    """
    filename = payload.filename
    fileDirectory = payload.filepath
    dest_dir = UPLOAD_DIR / fileDirectory
    dest_dir.mkdir(parents=True, exist_ok=True)
    file_path = os.path.join(dest_dir, filename)

    if payload.document_base64:
        try:
            file_bytes = base64.b64decode(payload.document_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Base64 payload")

        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext in ["docx", "doc"]:
            try:
                text = read_word_with_markitdown(file_bytes)
                with open(file_path, "wb") as f:
                    f.write(file_bytes)

            except Exception:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse Word document",
                )
        else:
            text = file_bytes.decode("utf-8", errors="ignore")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)

    elif payload.document_text:
        text = payload.document_text

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)

    else:
        raise HTTPException(
            status_code=400,
            detail="No document content provided",
        )

    return _store_document(
        enterprise.enterprise_id,
        filename,
        text,
    )

async def get_document_from_addin(enterprise: EnterpriseContext):
    """
    Returns all files in UPLOAD_DIR as a JSON array of WordAddinPayload objects.
    For output.md: returns both document_text and document_base64.
    For all other files: returns only document_base64.
    """
    result = []
    dir_list = ['input', 'output']

    for file_directory in dir_list:
        filepath = Path(UPLOAD_DIR) / file_directory
        if not filepath.exists():
            continue
        for file_path in filepath.iterdir():
            if not file_path.is_file():
                continue
            filename = file_path.name
            file_bytes = file_path.read_bytes()
            b64_content = base64.b64encode(file_bytes).decode("utf-8")
            
            if file_directory == 'output' and filename == "output.md":
                with open(os.path.join(filepath, filename), "r", encoding='utf-8') as f:
                    content = f.read()

                payload = WordAddinPayload(
                    filename=filename,
                    filepath=file_directory,
                    document_base64=b64_content,
                    document_text=content,
                )
            else:
                payload = WordAddinPayload(
                    filename=filename,
                    filepath=file_directory,
                    document_base64=b64_content,
                )
            result.append(payload.model_dump())
    return result

async def get_document(document_id: str, enterprise: EnterpriseContext):
    doc = _documents.get(document_id)

    if not doc or doc["enterprise_id"] != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Document not found")

    return doc

async def read_document(document_id: str, enterprise: EnterpriseContext):
    doc = _documents.get(document_id)

    if not doc or doc["enterprise_id"] != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": document_id,
        "content": _document_content.get(document_id, "")
    }