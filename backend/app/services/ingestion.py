import shutil
import os
import uuid
import json
from fastapi import UploadFile, HTTPException
from app.services.embedding import get_batch_embeddings
from app.services.database import insert_document_record, insert_chunks_records
from app.services.legal_parsers import LegalTextSplitter

UPLOAD_DIR = "data"

def save_uploaded_file(file: UploadFile) -> str:
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are allowed")
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return file_path

def read_file_content(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def process_document(file_path: str, category: str = "law"):
    """
    Ingest a document using the Smart Legal Parsing strategy.
    
    Args:
        file_path (str): Path to the .txt file
        category (str): 'law', 'jurisprudence'
    """
    content = read_file_content(file_path)
    filename = os.path.basename(file_path)
    
    print(f"🔹 Processing [{category}] {filename}...")

    # 1. Smart Parsing (The Core)
    # Returns list of dicts: {"content": "...", "chunk_type": "...", "metadata": {...}}
    raw_chunks = LegalTextSplitter.get_chunks(content, category, filename)
    print(f"   => Extracted {len(raw_chunks)} smart chunks.")

    # 2. Store Document in Supabase (with rich metadata)
    # We infer basic metadata from the first chunk or filename
    doc_metadata = {
        "source_type": category,
        "filename": filename
    }
    
    # Schema Category Mapping:
    # The DB schema requires specific categories (law, jurisprudence_full, jurisprudence_summary).
    # But user inputs 'jurisprudence'. We map it here based on what we see.
    db_category = category
    if category == "jurisprudence":
        # Heuristic: If parsing produced multiple distinct 'summary' chunks, it's a summary.
        # Otherwise it's a full decision.
        if raw_chunks and raw_chunks[0].get("chunk_type") in ["summary", "principle_summary"]:
            db_category = "jurisprudence_summary"
        else:
            db_category = "jurisprudence_full"
            
    # Attempt to extract global Law Name from filename if Law
    law_name = None
    if category == "law":
        law_name = filename.replace(".txt", "")
        doc_metadata["law_name"] = law_name
        
    # Attempt to extract Jurisdiction
    jurisdiction = None
    if "مجلس الدولة" in file_path or "مجلس_الدولة" in file_path:
        jurisdiction = "مجلس الدولة"
    elif "محكمة عليا" in file_path or "محكمة_عليا" in file_path:
        jurisdiction = "المحكمة العليا"
    
    if jurisdiction:
        doc_metadata["jurisdiction"] = jurisdiction
    
    doc_record = insert_document_record(
        filename, 
        len(raw_chunks), 
        category=db_category, 
        metadata=doc_metadata,
        law_name=law_name,
        jurisdiction=jurisdiction
    )
    doc_id = doc_record['id']
    
    # 3. Generate Embeddings
    # Extract text content for embedding
    texts_to_embed = [c["content"] for c in raw_chunks]
    embeddings = get_batch_embeddings(texts_to_embed)
    
    # 4. Prepare Data for Supabase (Pure Postgres/pgvector approach)
    supabase_chunks_data = []
    
    # Validation
    if len(embeddings) != len(raw_chunks):
        print(f"❌ Error: Embedding count mismatch ({len(embeddings)} vs {len(raw_chunks)})")
        return {"status": "error", "message": "Embedding mismatch"}
        
    for i, c in enumerate(raw_chunks):
        # Merge technical metadata with parser metadata
        final_meta = c.get("metadata", {})
        final_meta["filename"] = filename
        final_meta["chunk_type"] = c.get("chunk_type", "unknown")
        
        chunk_entry = {
            "document_id": doc_id,
            "chunk_index": i,
            "content": c["content"],
            "embedding": embeddings[i], # Direct vector list
            "chunk_type": c.get("chunk_type"),
            "article_number": c.get("article_number"),
            "metadata": final_meta
        }
        supabase_chunks_data.append(chunk_entry)
        
    # 5. Store Chunks in Supabase
    insert_chunks_records(supabase_chunks_data)
    
    # 6. Update BM25 Index (Optional / Reserved)
    # in V2 architecture, BM25 service loads directly from Supabase on startup.
    # We do not manually update the in-memory index here to avoid complexity.
    # The next time the backend restarts, it will fetch the new chunks.
    # For real-time updates, we would need a persistent index or triggered reload.
    print(f"   => Document processed. BM25 will be updated on next restart.")
    
    return {
        "file_path": file_path,
        "total_chars": len(content),
        "total_chunks": len(raw_chunks),
        "document_id": doc_id,
        "category": category,
        "status": "processed_and_stored"
    }
