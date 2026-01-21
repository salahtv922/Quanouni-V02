import requests
import json
import re
import time
from dataclasses import dataclass
from typing import Optional
from app.core.config import settings
from app.services.embedding import get_embedding
from app.services.vector_store import query_chroma
# SDK removed to reduce bundle size for serverless (Vercel 250MB limit)
# import google.generativeai as genai



@dataclass
class GenerationResponse:
    text: str


def generate_with_retry(model, prompt, retries=5, delay=4):
    # Check if Groq is enabled (Preferred for Generation)
    if hasattr(settings, 'GROQ_API_KEY') and settings.GROQ_API_KEY:
        try:
            # Groq API Call
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            # Fallback to stable model if the configured one fails
            model_id = getattr(settings, 'GROQ_MODEL', None) or "llama-3.1-70b-versatile"
            print(f"[Groq] Using model: {model_id}")
            data = {
                "messages": [{"role": "user", "content": prompt}],
                "model": model_id,
                "temperature": 0.3,
                "max_tokens": 4096
            }
            
            # Simple retry logic for Groq too
            for attempt in range(3):
                try:
                    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=120)
                    if resp.status_code == 200:
                        content = resp.json()['choices'][0]['message']['content']
                        return GenerationResponse(text=content)
                    elif resp.status_code == 429:
                        print(f"Groq Rate Limit, waiting {delay}s...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"Groq Error {resp.status_code}: {resp.text[:500]}")
                except requests.exceptions.Timeout:
                    print(f"Groq Timeout (attempt {attempt+1}/3)")
                    continue
                except Exception as e:
                    print(f"Groq Exception: {type(e).__name__}: {e}")
            
            print("Groq failed, falling back to Gemini...")
        except Exception as e:
             print(f"Groq Setup Error: {e}, falling back...")

    # Fallback to Gemini REST API
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_CHAT_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192
        }
    }

    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                # Extract text from Gemini response structure
                try:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    return GenerationResponse(text=text)
                except (KeyError, IndexError):
                     print(f"Gemini Bad Response format: {result}")
                     raise ValueError("Gemini response parsing failed")
            elif resp.status_code == 429:
                 print(f"Gemini Rate Limit, waiting {delay}s...")
                 time.sleep(delay)
                 delay *= 2
            else:
                 print(f"Gemini Error {resp.status_code}: {resp.text}")
                 if attempt == retries - 1:
                     raise Exception(f"Gemini API Error: {resp.text}")
                 
        except Exception as e:
            if attempt < retries - 1:
                print(f"Gemini Exception: {e}, retrying...")
                time.sleep(delay)
            else:
                raise e

def detect_language(text: str) -> str:
    """Detect the language of the query"""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    total_chars = len([c for c in text if c.isalpha()])
    
    if total_chars == 0:
        return "ar"
    
    arabic_ratio = arabic_chars / total_chars
    
    if arabic_ratio > 0.3:
        return "ar"
    
    french_words = ['le', 'la', 'les', 'de', 'et', 'dans', 'pour', 'sont', 'peut', 'comment', 'quels', 'quel']
    text_lower = text.lower()
    if any(word in text_lower.split() for word in french_words):
        return "fr"
    
    return "en"

def rerank_with_gemini(query: str, chunks: list[str], top_k: int = 3) -> list[tuple[str, float]]:
    # Removed configure_gemini() call
    # model = genai.GenerativeModel(...) -> Just pass None as we use REST inside generate_with_retry
    model = None 

    
    chunks_text = ""
    for i, chunk in enumerate(chunks[:10], 1):
        chunks_text += f"\n\n### Chunk {i}:\n{chunk[:500]}...\n"
    
    prompt = f"""أنت خبير قانوني جزائري. مهمتك ترتيب النصوص القانونية حسب صلتها بالسؤال.

السؤال: {query}

النصوص المتاحة:
{chunks_text}

معايير التقييم (مهم جداً):
- 10: المادة القانونية التي تُعرِّف الجريمة أو تحدد العقوبة المطلوبة مباشرة
- 9-10: *الاجتهاد القضائي* (قرار المحكمة العليا/مجلس الدولة) الذي يفصل في نفس المسألة بدقة
- 8-9: مادة من نفس القانون تتحدث عن نفس الموضوع (مثلاً: سرقة، طلاق، عقد)
- 5-7: مادة أو اجتهاد ذو صلة جزئية
- 0-4: مادة من قانون آخر أو موضوع مختلف

مثال: إذا كان السؤال عن "السرقة بالعنف":
- المادة 350 مكرر (السرقة مع العنف) = 10
- قرار المحكمة العليا حول ظرف العنف = 9
- المادة 351 (السرقة المشددة) = 9
- المادة 388 (إخفاء الأشياء) = 5
- قانون الكهرباء = 0

أجب بـ JSON فقط: {{"1": 8, "2": 5, ...}}"""
    
    # OPENROUTER: Use light model for reranking to save cost/time
    try:
        response = generate_openrouter(prompt, model="google/gemini-2.0-flash-001")
        import json
        json_match = re.search(r'\{[^}]+\}', response.text)
        if json_match:
            scores = json.loads(json_match.group())
            ranked = []
            for i, chunk in enumerate(chunks[:10], 1):
                score = float(scores.get(str(i), 0)) / 10.0
                ranked.append((chunk, score))
            for chunk in chunks[10:]:
                ranked.append((chunk, 0.1))
            ranked.sort(key=lambda x: x[1], reverse=True)
            return ranked[:top_k]
        return [(chunk, 0.5) for chunk in chunks[:top_k]]
    except Exception as e:
        # Avoid printing full exception if it contains Arabic
        return [(chunk, 0.5) for chunk in chunks[:top_k]]

def generate_gemini_flash(prompt: str):
    """
    Dedicated function for Generation using Gemini Flash Latest (via REST API).
    Used for Consult and Pleading modes to ensure high-quality reasoning.
    Refactored from SDK to REST API to reduce bundle size for Vercel.
    """
    try:
        if not settings.GEMINI_API_KEY:
             raise ValueError("GEMINI_API_KEY not set")
        
        # Use the confirmed working model via REST API
        MODEL_NAME = "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={settings.GEMINI_API_KEY}"
        
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3, # Low temp for precise legal reasoning
                "maxOutputTokens": 8192
            }
        }
        
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        
        if resp.status_code == 200:
            result = resp.json()
            try:
                text = result['candidates'][0]['content']['parts'][0]['text']
                return GenerationResponse(text=text)
            except (KeyError, IndexError):
                print(f"[Gemini Flash] Bad Response format: {result}")
                raise ValueError("Gemini Flash response parsing failed")
        else:
            print(f"[Gemini Flash] Error {resp.status_code}: {resp.text[:500]}")
            raise Exception(f"Gemini Flash API Error: {resp.status_code}")
        
    except Exception as e:
        print(f"[Gemini Flash] REST Error: {e}")
        print("[Gemini Flash] Falling back to Groq/standard API...")
        return generate_with_retry(None, prompt)

def generate_openrouter(prompt: str, model: str = None):
    """
    Generate text using OpenRouter API.
    Args:
        prompt: The input prompt
        model: Optional model override. If None, uses OPENROUTER_MODEL env var (Gemini 3).
    """
    try:
        api_key = settings.OPENROUTER_API_KEY
        # Default to heavy model (Gemini 3) if not specified
        target_model = model or getattr(settings, 'OPENROUTER_MODEL', "google/gemini-2.0-flash-001")
        
        if not api_key:
            print("[OpenRouter] No API Key set, skipping to fallback (Gemini Flash Direct)...")
            return generate_gemini_flash(prompt)

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://quanouni.ai", 
            "X-Title": "Qanouni AI",
            "Content-Type": "application/json"
        }
        data = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 64000 # Support large logic
        }
        
        # print(f"[OpenRouter] Requesting model: {model}...")
        resp = requests.post(url, headers=headers, json=data, timeout=120)
        
        if resp.status_code == 200:
            result = resp.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                return GenerationResponse(text=content)
            else:
                 print(f"[OpenRouter] Empty choices: {result}")
                 return generate_gemini_flash(prompt)
        else:
            print(f"[OpenRouter] Error {resp.status_code}: {resp.text[:500]}")
            # Fallback
            print("[OpenRouter] Falling back to Gemini Flash Direct...")
            return generate_gemini_flash(prompt)
            
    except Exception as e:
        print(f"[OpenRouter] Exception: {e}")
        return generate_gemini_flash(prompt)

class RAGService:
    def __init__(self):
        # No SDK configuration needed.
        self.model = None # We don't use the SDK model object anymore

    def _retrieve(self, query, filters=None, top_k=20):
        # ... (unchanged) ...
        try:
            query_embedding = get_embedding(query, is_query=True)
            vector_results = query_chroma(query_embedding, n_results=top_k, where=filters)
            v_docs = vector_results['documents'][0] if vector_results and 'documents' in vector_results else []
            v_metas = vector_results['metadatas'][0] if vector_results and 'metadatas' in vector_results else []
        except Exception as e:
            print(f"Vector search failed")
            v_docs, v_metas = [], []

        # 2. BM25 Search
        from app.services.bm25_service import bm25_service
        bm25_results = bm25_service.search(query, top_k=top_k, filters=filters)

        # 3. RRF Fusion (BM25-heavy due to poor vector search for Arabic legal text)
        k = 60
        scores = {}
        meta_map = {}
        
        # Combine (BM25 prioritized because vector similarity is weak for Arabic)
        for r, d in enumerate(v_docs):
            scores[d] = scores.get(d, 0) + (0.3 / (k + r + 1))  # Vector: 30%
            if r < len(v_metas): meta_map[d] = v_metas[r]
            
        for r, (d, s, m) in enumerate(bm25_results):
            scores[d] = scores.get(d, 0) + (0.7 / (k + r + 1))  # BM25: 70%
            meta_map[d] = m

        ranked_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        final_docs = [d for d, s in ranked_docs[:15]]
        final_metas = [meta_map.get(d, {}) for d in final_docs]
        
        return final_docs, final_metas

    def answer_query(self, query: str, filters: dict = None, skip_generation: bool = False):
        # Standard Research Mode
        docs, metas = self._retrieve(query, filters)
        
        # Rerank
        if not skip_generation:
            reranked = rerank_with_gemini(query, docs, top_k=5)
            # Re-map metadata
            final_docs = [r[0] for r in reranked]
            final_metas = []
            for d in final_docs:
                try: 
                    idx = docs.index(d)
                    final_metas.append(metas[idx])
                except: final_metas.append({})
        else:
            final_docs, final_metas = docs[:5], metas[:5]

        # Context formatting
        context = ""
        for i, (doc, meta) in enumerate(zip(final_docs, final_metas), 1):
            title = meta.get('filename', f'Source {i}').replace('.txt', '')
            context += f"\n\n### [مصدر {i}: {title}]\n{doc}\n"

        if skip_generation:
            return {"answer": "Retrieval Only", "context": final_docs, "metadatas": final_metas}

        # Prompt - Professional Legal Research (v2.0)
        prompt = f"""أنت **باحث قانوني متخصص في القانون الجزائري**، تعمل في مكتبة قانونية أكاديمية.
مرجعيتك الحصرية هي النصوص القانونية المقدمة أدناه فقط.

## مهمتك
تحليل السؤال القانوني وتقديم إجابة دقيقة ومبررة بالنصوص.

## قواعد الإجابة الإلزامية:
1. **لا تختلق معلومات**: إذا لم تجد الإجابة في النصوص المقدمة، قل ذلك صراحة: "لم أجد نصاً صريحاً يجيب على هذا السؤال في المصادر المتاحة."
2. **الاقتباس الدقيق**: عند الاستشهاد بمادة قانونية، اقتبس نصها الحرفي بين علامات تنصيص « ».
3. **الإشارة للمصادر**: استخدم أرقام المصادر [1], [2], [3] بعد كل اقتباس أو معلومة.
4. **التنسيق الإلزامي**:
   - ابدأ بـ **## ملخص الإجابة** (3 أسطر كحد أقصى)
   - ثم **## التحليل القانوني** مع شرح مفصل وأرقام المصادر
   - اختم بـ **## المراجع** (قائمة مرقمة: اسم القانون + رقم المادة إن وجد)
5. **اللغة**: العربية الفصحى القانونية الرسمية. لا تستخدم العامية أبداً.
6. **الموضوعية**: لا تُبدِ رأياً شخصياً. التزم بما جاء في النصوص.

## النصوص القانونية المتاحة:
{context}

## السؤال:
{query}

## الإجابة:"""

        try:
            # OPENROUTER: Use light model for General Search (interactive speed)
            response = generate_openrouter(prompt, model="google/gemini-2.0-flash-001")
            # response = generate_with_retry(self.model, prompt)
            answer = response.text.replace('"]', '"]\n') # Hack for ref formatting
        except Exception as e:
            print(f"Generation failed after retries: {e}")
            answer = "عذراً، النظام مشغول جداً حالياً (ضغط على الموديل). هذه هي المصادر التي وجدتها، لكن لم أتمكن من صياغة الإجابة النهائية. يرجى المحاولة بعد قليل."
        
        return {
            "query": query, 
            "answer": answer, 
            "sources": [{
                "filename": m.get('filename'),
                "document_id": m.get('document_id'),
                "chunk_index": m.get('chunk_index', i+1),
                "content_preview": final_docs[i][:150] + "..." if len(final_docs[i]) > 150 else final_docs[i]
            } for i, m in enumerate(final_metas)]
        }

    def _extract_search_query(self, situation: str) -> str:
        """استخراج ذكي للكلمات المفتاحية باستخدام LLM لتحسين دقة البحث"""
        try:
            prompt = f"""أنت خبير قانوني ذكي. مهمتك هي تحليل موقف قانوني واستخراج أفضل كلمات البحث للعثور على القوانين والمراجع المناسبة.
            
الموقف:
{situation[:2000]}

استخرج ما يلي في سطر واحد فقط:
1. نوع القضية (مثلاً: ميراث، عمل، جنائي، أحوال شخصية)
2. 5 إلى 10 كلمات مفتاحية دقيقة للبحث في النصوص القانونية (مثلاً: استخدم "تسريح تعسفي" بدلاً من "طرد"، "قسمة تركة" بدلاً من "تقسيم الإرث")

تنسيق الإجابة المطلوب:
[نوع القضية] كلمات مفتاحية

أجب فقط بالسطر المطلوب بدون أي مقدمات أو شرح."""

            # استخدام الموديل لاستخراج الكلمات المفتاحية
            # نستخدم OpenRouter (Gemini 2 Filter) للسرعة والدقة والتكلفة
            # OPENROUTER: Use light model for extraction
            response = generate_openrouter(prompt, model="google/gemini-2.0-flash-001")
            
            if response and hasattr(response, 'text'):
                extracted_text = response.text.strip()
                print(f"[Smart Extract] LLM Output: {extracted_text}")
                
                # دمج وصف الموقف (أول 50 كلمة للسياق) مع الكلمات المستخرجة ذكياً
                # هذا يضمن وجود السياق الأصلي + المصطلحات القانونية الدقيقة
                words = situation.split()[:50]
                combined_query = " ".join(words) + " " + extracted_text
                return combined_query
            
            print("[Smart Extract] Empty response, falling back.")
            return " ".join(situation.split()[:80])

        except Exception as e:
            print(f"[Smart Extract] Error: {e}")
            # Fallback to simple truncation
            return " ".join(situation.split()[:80])

    def consult(self, situation: str):
        """وضع المستشار القانوني - استشارة قانونية احترافية"""
        # استخراج استعلام بحث مركز من الموقف
        search_query = self._extract_search_query(situation)
        
        # Search for relevant laws AND jurisprudence using focused query
        # UPGRADE: Fetch 50 docs for Gemini 3 massive context
        docs, metas = self._retrieve(search_query, top_k=50)
        
        # Rerank using original situation for context relevance
        # RE-ENABLED: Using Gemini Flash (Fast) to filter irrelevant jurisprudence effectively
        try:
            reranked = rerank_with_gemini(situation, docs, top_k=3)
            final_docs = [r[0] for r in reranked]
            final_metas = []
            doc_map = {d: m for d, m in zip(docs, metas)}
            for d in final_docs: final_metas.append(doc_map.get(d, {}))
        except Exception:
            # Fallback if reranker fails
            final_docs = docs[:20]
            final_metas = metas[:20]
        
        # Format context with source type indication (full text like Legal Search)
        context = ""
        for i, (doc, meta) in enumerate(zip(final_docs, final_metas), 1):
            source_name = meta.get('filename', f'مصدر {i}').replace('.txt', '')
            # Clean Cyrillic or bad chars in titles (OCR artifacts)
            # Robust fix for "на" (Cyrillic/Latin mix)
            # Replace specifically the known bad pattern or generic non-arabic in Arabic context
            source_name = re.sub(r'[\u0400-\u04FF]+', 'على', source_name) # Replace Cyrillic with 'على' (heuristic)
            if 'на' in source_name or 'ha' in source_name: 
                 source_name = source_name.replace(' на ', ' على ').replace(' ha ', ' على ')
            source_name = source_name.replace('_', ' ')
            
            source_type = "اجتهاد قضائي" if "قرار" in source_name or "اجتهاد" in source_name else "نص قانوني"
            context += f"\n\n### [{source_type} - مصدر {i}: {source_name}]\n{doc}\n"
        
        # Professional Legal Consultant Prompt (v2.2 - Explicit Citations)
        prompt = f"""أنت **محامٍ أول معتمد لدى المحكمة العليا الجزائرية**.
مهمتك تقديم استشارة قانونية دقيقة بناءً *حصراً* على النصوص المقدمة.

## الموقف القانوني:
{situation}

## المصادر القانونية المتاحة:
{context}

⚠️ **تعليمات صارمة للاستشهاد**:
1. **لا تقل أبداً "مصدر 1" أو "Source 1"**.
2. **استخدم اسم القانون/المرجع** المذكور في عنوان المصدر.
   - ❌ خطأ: "تنص المادة 8 من مصدر 1..."
   - ✅ صح: "تنص المادة 8 من **أمر إلزامية التأمين على السيارات**..."
3. صحح أسماء القوانين إذا ظهرت بها أخطاء إملائية (مثلاً: "на" -> "على").

## هيكلة الاستشارة (التزم بهذا الترتيب):

### 1. التكييف القانوني ⚖️
- ما هو نوع القضية؟ (مدني / جزائي / إداري / أسرة / عمل / تجاري)
- ما هي الوقائع القانونية المؤثرة؟
- من هم الأطراف وما صفاتهم القانونية؟

### 2. الأساس القانوني 📚
- **النصوص القانونية**: اذكر المواد المنطبقة مع نصها بين « »، ونسبتها إلى **اسم القانون الصريح**.
- **الاجتهاد القضائي**: إن وجد قرار من المحكمة العليا، اذكره برقم القرار والسنة.

### 3. التوجيه العملي 🎯
- ما الإجراء الواجب؟ (شكوى / دعوى / صلح / تظلم / استئناف)
- أمام أي جهة؟ (محكمة ابتدائية / مجلس قضائي / محكمة عليا / إدارة)
- ما الوثائق والأدلة اللازمة؟

### 4. التحذيرات القانونية ⚠️
- آجال التقادم أو السقوط (إن وجدت)
- المخاطر المحتملة إن لم يُتخذ إجراء سريع

### 5. الخلاصة والتوصية 📌
- ملخص الموقف في 3 أسطر
- التوصية النهائية الواضحة

---
⚠️ **تنويه**: هذه استشارة قانونية أولية مبنية على المعلومات المقدمة. يُنصح بمراجعة محامٍ متخصص لدراسة ملف القضية كاملاً."""

        try:
            # UPGRADE: Use OpenRouter (Gemini 3) for superior reasoning
            print(f"[Consult] Using OpenRouter (Gemini 3) for superior reasoning...")
            response = generate_openrouter(prompt)
            consultation_text = response.text
        except Exception as e:
            print(f"Consultation generation failed: {e}")
            consultation_text = "عذراً، لم أتمكن من صياغة الاستشارة النهائية بسبب ضغط النظام. يرجى مراجعة المصادر أدناه."

        # Build improved source titles
        sources_list = []
        for d, m in zip(final_docs, final_metas):
            title = m.get('filename', 'Source').replace('.txt', '')
            # Clean Cyrillic or bad chars in titles (OCR artifacts) - APPLY TO OUTPUT LIST TOO
            title = re.sub(r'[\u0400-\u04FF]+', 'على', title)
            if 'на' in title or 'ha' in title:
                 title = title.replace(' на ', ' على ').replace(' ha ', ' على ')
            title = title.replace('_', ' ')
            
            # 1. Try Metadata Article Number
            if m.get('article_number'):
                title = f"{title} - المادة {m['article_number']}"
            
            # 2. If Jurisprudence, try to extract decision number or date from content
            elif 'قرار' in d[:100] or 'تسريح' in title:
                # Try to find "قرار رقم X"
                match_decision = re.search(r'قرار\s+رقم\s*[:\s]\s*(\d+)', d)
                if match_decision:
                    title = f"قرار المحكمة العليا رقم {match_decision.group(1)} ({title})"
                else:
                    # Fallback: Try to find article reference in text
                    match_art = re.search(r'المادة\s+(\d+)', d)
                    if match_art:
                        title = f"{title} (إشارة للمادة {match_art.group(1)})"

            # 3. Fallback to law name
            elif m.get('law_name'): 
                law = m['law_name'].replace('.txt', '')
                if law != title:
                    title = f"{law} ({title})"
            
            sources_list.append({
                "title": title, 
                "content": d,
                "document_id": m.get('document_id'),
                "chunk_index": m.get('chunk_index'),
                "filename": m.get('filename'),
                "metadata": m
            })

        return {
            "answer": consultation_text,
            "sources": sources_list
        }

    def draft_pleading(self, case_data: dict, pleading_type="دفاع", style="formel", top_k=30):
        """
        وضع المحامي: توليد مذكرات قانونية احترافية باستخدام هيكلية المرافعات الذهبية
        Advocate Mode: Generate professional legal pleadings
        Enhanced v2.1: Few-Shot + Interactive Sources + OCR Cleaning
        """
        facts = case_data.get('facts', '')
        charges = " ".join(case_data.get('charges', []))
        defendant_name = case_data.get('defendant_name', 'المتهم')
        court = case_data.get('court', 'المحكمة المختصة')
        case_number = case_data.get('case_number', '')
        
        # Extract defense strategy if available
        defense_strategy = case_data.get('defense_strategy', {})
        main_defense = defense_strategy.get('main_argument', '')
        secondary_args = defense_strategy.get('secondary_arguments', [])
        
        # 1. Smart Extraction from Case Data
        case_context = f"التهمة: {charges}. الوقائع: {facts}"
        search_query = self._extract_search_query(case_context)
        print(f"[Pleading] Smart Query: {search_query}")

        # 2. Retrieval
        # 2. Retrieval - UPGRADE: Fetch more docs for Gemini 3 Flash Large Context
        docs, metas = self._retrieve(search_query, top_k=60) # Increased from default/30 to 60 for large context
        
        # 3. Reranking using Gemini
        # 3. Reranking using Gemini - KEEP TOP 20 INSTEAD OF 5
        reranked = rerank_with_gemini(case_context, docs, top_k=20)
        final_docs = [r[0] for r in reranked]
        final_metas = []
        
        doc_map = {d: m for d, m in zip(docs, metas)}
        for d in final_docs: final_metas.append(doc_map.get(d, {}))
        
        # 4. Build Legal Context with CLEAN source names (TRUNCATED to avoid timeout)
        context = ""
        for i, (doc, meta) in enumerate(zip(final_docs, final_metas), 1):
            source_name = meta.get('filename', f'مصدر {i}').replace('.txt', '')
            # Clean Cyrillic OCR artifacts
            source_name = re.sub(r'[\u0400-\u04FF]+', 'على', source_name)
            source_name = source_name.replace(' на ', ' على ').replace(' ha ', ' على ')
            source_name = source_name.replace('_', ' ')
            
            source_type = "اجتهاد قضائي" if "قرار" in source_name or "اجتهاد" in source_name else "نص قانوني"
            # UPGRADE: No truncation for Gemini 3 (1M Context)
            # define a very large safe limit just in case
            doc_truncated = doc[:50000] 
            context += f"\n\n### [{source_type}: {source_name}]\n{doc_truncated}\n"
        
        # 5. Few-Shot Golden Example (Expanded with Eloquence)
        golden_example = """
═══════════════════════════════════════
📜 نموذج مرافعة ذهبية (للتعلم)
═══════════════════════════════════════
**المسألة:** هل شهادة المجني عليه وحدها كافية للإدانة؟

**القاعدة:** من المستقر عليه قضاءً وفقاً للمادة 212 من قانون الإجراءات الجزائية أن "الإثبات في المواد الجزائية حر"، غير أن المحكمة العليا قررت في اجتهادها الراسخ أن "الشك يُفسَّر دائماً لمصلحة المتهم".

**التحليل:**
1. **تناقض في الوصف:** زعم المجني عليه أن الجاني "طويل القامة"، في حين أن المتهم ماثل أمامكم وقامته لا تتجاوز 160 سم، مما ينفي الصلة.
2. **استحالة الحدوث:** التوقيت المصرح به (21:00) يتزامن مع تواجد المتهم في مقر عمله المثبت بكشف الحضور.
3. **غياب السند المادي:** خلت أوراق الملف من أي محجوزات أو بصمات تؤكد الرواية.

**النتيجة:** وأمام هذا الوهن في الأدلة، لا يسع عدالتكم إلا القضاء بالبراءة، تأسيساً على أن الأحكام الجزائية تُبنى على الجزم واليقين لا على الشك والتخمين.
═══════════════════════════════════════
"""
    
        # 6. Professional Prompt with Few-Shot + Case Data
        prompt = f"""أنت محامٍ جزائري "نابغ" (Top-Tier Lawyer) تترافع أمام **{court}**.
مهمتك: صياغة **{pleading_type}** بأسلوب قانوني رفيع، يحاكي بلاغة كبار المحامين.

{golden_example}

═══════════════════════════════════════
📋 ملف القضية
═══════════════════════════════════════
• **الجهة القضائية:** {court}
• **المتهم:** {defendant_name}
• **التهمة:** {charges}
{"• **استراتيجية الدفاع:** " + main_defense if main_defense else ""}

📝 **الوقائع (Fact Pattern):**
{facts}

═══════════════════════════════════════
📚 الذخيرة القانونية (السند)
═══════════════════════════════════════
{context}

═══════════════════════════════════════
⚖️ الهيكلة المطلوبة (إلزامية العناوين)
═══════════════════════════════════════
1. **الديباجة:** (إلى السيد رئيس {court}...)
2. **أولاً: الوقائع:** (سرد موجز ومرقم).
3. **ثانياً: الإجراءات:** (فقرة واحدة).
4. **ثالثاً: المناقشة القانونية (القلب):**
   - استخدم عنوان فرعي: `### 1. في الشكل`
   - استخدم عنوان فرعي: `### 2. في الموضوع`
   - داخل الموضوع، استخدم نقاط واضحة `-` لكل دفع قانوني.
   - استخدم البنية: **الدفـع** ← **السند القانوني (المادة)** ← **التطبيق على الوقائع**.
5. **رابعاً: الطلبات:** (قائمة نقطية مرقمة).

⚠️ **تنبيهات**:
- **التنسيق:** استخدم العناوين `###` والنقاط `-` لتجميل النص وجعله مقروءاً.
- **الاقتباس:** ضع نصوص المواد بين «...».

ابدأ المرافعة فوراً:"""

        try:
            print(f"[Pleading] Sending prompt of length: {len(prompt)} chars")
            # USE DEDICATED OPENROUTER FUNCTION
            response = generate_openrouter(prompt)
            pleading_text = response.text
            
            # --- POST-PROCESSING (Cleaning) ---
            # 1. Clean Cyrillic/Russian OCR artifacts (common in scraped Algerian laws)
            pleading_text = re.sub(r'[\u0400-\u04FF]+', '', pleading_text)
            # 2. Remove any remaining bracketed placeholders if LLM hallucinated them
            pleading_text = re.sub(r'\[(?!مصدر|نص|اجتهاد).*?\]', '', pleading_text)
            
            print(f"[Pleading] SUCCESS - Generated {len(pleading_text)} chars")
        except Exception as e:
            print(f"[Pleading] FAILED: {type(e).__name__}: {e}")
            pleading_text = f"""# مذكرة {pleading_type}

⚠️ عذراً، لم أتمكن من إتمام صياغة المذكرة بسبب خطأ تقني.
**الخطأ:** {type(e).__name__}: {str(e)[:200]}

## المعلومات المتاحة:
- **المتهم**: {defendant_name}
- **التهمة**: {charges}

يرجى إعادة المحاولة."""


        # Build sources with document_id and chunk_index for interactivity
        sources_list = []
        for d, m in zip(final_docs, final_metas):
            title = m.get('filename', 'Source').replace('.txt', '')
            title = re.sub(r'[\u0400-\u04FF]+', 'على', title)
            title = title.replace(' на ', ' على ').replace(' ha ', ' على ')
            title = title.replace('_', ' ')
            sources_list.append({
                "title": title,
                "filename": m.get('filename'),
                "document_id": m.get("document_id"),
                "chunk_index": m.get("chunk_index")
            })

        return {
            "pleading": pleading_text,
            "metadata": {"total_sources": len(docs), "pleading_type": pleading_type},
            "sources": sources_list
        }


    def search_jurisprudence(self, legal_issue: str, chamber=None, top_k=20):
        # Jurisprudence Mode - Filter by Supreme Court and Conseil d'État
        
        # If chamber is specified, append it to query
        search_query = legal_issue
        if chamber:
             search_query += f" ({chamber})"
             
        # FIX: Include all jurisprudence categories (database uses 'jurisprudence_full')
        target_categories = ["jurisprudence", "jurisprudence_full", "jurisprudence_conseil_etat"]
        
        # UPGRADE: Fetch broad (200) then strictly filter in Python 
        # (RPC doesn't support $in queries, so we fetch more to be safe)
        raw_docs, raw_metas = self._retrieve(search_query, filters=None, top_k=200)
        
        docs = []
        metas = []
        
        for d, m in zip(raw_docs, raw_metas):
            if m.get("category") in target_categories:
                docs.append(d)
                metas.append(m)
        
        # Debug: Log how many jurisprudence docs were found
        print(f"[Jurisprudence] Found {len(docs)} matching documents out of {len(raw_docs)} total retrieved")
        
        # Slice to requested top_k
        docs = docs[:top_k]
        metas = metas[:top_k]
        
        # If no jurisprudence docs found, inform the user clearly
        if len(docs) == 0:
            return {
                "analysis": "⚠️ لم يتم العثور على اجتهادات قضائية مطابقة للمسألة المطروحة في قاعدة البيانات الحالية. يُرجى تجربة صياغة أخرى للسؤال أو التحقق من إدخال الاجتهادات.",
                "metadata": {"total_sources": 0},
                "sources": []
            }
        
        # RERANKING: Use Gemini to filter only jurisprudence relevant to the legal issue
        # This prevents unrelated cases (e.g., property law when searching for confession validity)
        try:
            print(f"[Jurisprudence] Reranking {len(docs)} documents for relevance...")
            # UPGRADE: Rerank more docs for Gemini 3
            reranked = rerank_with_gemini(legal_issue, docs, top_k=20)
            
            # Rebuild docs/metas based on reranked order
            reranked_docs = [r[0] for r in reranked]
            doc_to_meta = {d: m for d, m in zip(docs, metas)}
            reranked_metas = [doc_to_meta.get(d, {}) for d in reranked_docs]
            
            docs = reranked_docs
            metas = reranked_metas
            print(f"[Jurisprudence] After reranking: {len(docs)} documents retained")
        except Exception as e:
            print(f"[Jurisprudence] Reranking failed: {e}, using original order")
            # Fallback: just take top 5
        # UPGRADE: Use more docs and no truncation for Gemini 3
            docs = docs[:20]
            metas = metas[:20]
        
        # Limit context to avoid token limit - REMOVED for Gemini 3
        # We pass full content now
        context = "\n".join([f"--- قرار {i+1} ({metas[i].get('filename', 'غير معروف')}) ---\n{d}" for i, d in enumerate(docs)])
        
        prompt = f"""بصفتك باحثاً في الاجتهاد القضائي (المحكمة العليا ومجلس الدولة).
المسألة: {legal_issue}
القرارات المستخرجة:
{context}

المطلوب:
1. استخرج المبادئ القانونية بدقة من القرارات أعلاه فقط.
2. لكل مبدأ، **يجب** إدراج "نص المبدأ" كما ورد في القرار بين علامتي اقتباس.
3. اذكر رقم القرار وتاريخه إن وجد في النص، **أو اكتب "غير مذكور"**.
4. وضح هل الاجتهاد مستقر أم هناك تناقض.

⚠️ **تحذير مهم**: لا تختلق أرقام قرارات أو تواريخ أو مراجع غير موجودة في النصوص أعلاه. إذا لم تجد رقم القرار، اكتب صراحة: "رقم القرار: غير مذكور في النص".

التنسيق المطلوب:
- **المبدأ:** [شرح المبدأ]
- **النص المقتبس:** "...[النص الحرفي من القرار]..."
- **المرجع:** قرار رقم [X] بتاريخ [Y] - [الجهة] (أو "غير مذكور")"""

        # UPGRADE: Use OpenRouter for better Arabic legal understanding
        response = generate_openrouter(prompt)
        
        # Include text snippets in sources for UI
        enriched_sources = []
        for doc, meta in zip(docs, metas): # Ensure we return all reranked docs
             enriched_sources.append({
                 "filename": meta.get('filename'),
                 "document_id": meta.get('document_id'),
                 "chunk_index": meta.get('chunk_index', 1),
                 "relevance_score": 0.9,
                 "snippet": doc[:200] + "..." # Snippet for UI
             })

        return {
            "analysis": response.text,
            "metadata": {"total_sources": len(docs)},
            "sources": enriched_sources
        }

rag_service = RAGService()

def rag_pipeline(query, filters=None, skip_generation=False):
    return rag_service.answer_query(query, filters, skip_generation)
