import requests
from app.core.config import settings

def get_embedding(text: str, is_query: bool = False) -> list[float]:
    # Use different task_type for queries vs documents if supported, 
    # but for raw REST API, we just send content or use specific models.
    # text-embedding-004 supports "content" and "taskType"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_EMBEDDING_MODEL}:embedContent?key={settings.GEMINI_API_KEY}"
    
    task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
    
    payload = {
        "model": f"models/{settings.GEMINI_EMBEDDING_MODEL}",
        "content": {
            "parts": [{"text": text}]
        },
        "taskType": task_type
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['embedding']['values']
    except Exception as e:
        print(f"Gemini Embedding Error: {e}")
        # Return zero vector or re-raise
        raise e

def get_batch_embeddings(texts: list[str]) -> list[list[float]]:
    # Batch embedding endpoint: batchEmbedContents
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_EMBEDDING_MODEL}:batchEmbedContents?key={settings.GEMINI_API_KEY}"
    
    # Batch size limit for Gemini API (safe limit ~100)
    BATCH_SIZE = 50
    all_embeddings = []
    
    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i:i + BATCH_SIZE]
        requests_data = []
        for text in batch_texts:
            requests_data.append({
                "model": f"models/{settings.GEMINI_EMBEDDING_MODEL}",
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_DOCUMENT"
            })
            
        payload = {"requests": requests_data}
        
        try:
            # print(f"   Using Batch {i//BATCH_SIZE + 1} ({len(batch_texts)} items)...")
            response = requests.post(url, json=payload, timeout=60)
            if response.status_code == 429:
                import time
                print("   ⚠️ Rate Limit Hit. Sleeping 10s...")
                time.sleep(10)
                response = requests.post(url, json=payload, timeout=60)
                
            response.raise_for_status()
            results = response.json()
            batch_embeddings = [item['values'] for item in results.get('embeddings', [])]
            all_embeddings.extend(batch_embeddings)
        except Exception as e:
            print(f"Gemini Batch {i} Embedding Error: {e}")
            # If a batch fails, we can't easily recover just that part without more complex logic.
            # Returning partial results is risky for index alignment.
            raise e
            
    return all_embeddings
