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
    
    requests_data = []
    for text in texts:
        requests_data.append({
            "model": f"models/{settings.GEMINI_EMBEDDING_MODEL}",
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_DOCUMENT"
        })
        
    payload = {"requests": requests_data}
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        results = response.json()
        return [item['values'] for item in results.get('embeddings', [])]
    except Exception as e:
        print(f"Gemini Batch Embedding Error: {e}")
        return []
