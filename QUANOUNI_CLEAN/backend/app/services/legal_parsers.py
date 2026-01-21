import re
from typing import List, Dict, Any

class LegalTextSplitter:
    """
    Factory class to dispatch text splitting strategy based on document category.
    """
    @staticmethod
    def get_chunks(text: str, category: str, filename: str = "") -> List[Dict[str, Any]]:
        filename = filename.lower()
        if category == 'law':
            return LawSplitter.split(text)
        elif category == 'jurisprudence':
            # Heuristic to detect if it's a summary file or full decision
            if "اجتهادات" in filename and ".txt" in filename and len(text) > 50000: 
                # Likely a compilation file like 'اجتهادات_الغرفة_الجنائية.txt'
                return JurisprudenceSummaryParser.split(text)
            else:
                # Default to full decision parser
                return JurisprudenceFullParser.split(text)
        else:
             # Fallback for generic text
            return GenericSplitter.split(text)

class LawSplitter:
    """
    Parses Legal Codes (Qanoun).
    Atomic Unit: Article.
    """
    # Regex to detect Article Start: "المادة 123" or "Article 123"
    ARTICLE_PATTERN = re.compile(r'^(المادة\s+\d+|Article\s+\d+)', re.MULTILINE)

    @staticmethod
    def split(text: str) -> List[Dict[str, Any]]:
        chunks = []
        
        # 1. Split text by Article pattern
        # re.split with capturing group returns: [preamble, match1, content1, match2, content2...]
        parts = LawSplitter.ARTICLE_PATTERN.split(text)
        
        # Preamble (Text before first article)
        if parts[0].strip():
            chunks.append({
                "content": parts[0].strip(),
                "chunk_type": "preamble",
                "article_number": None,
                "metadata": {"section": "preamble"}
            })
        
        # Iterate over matches (Article Header + Content)
        for i in range(1, len(parts), 2):
            header = parts[i].strip() # e.g., "المادة 15"
            content = parts[i+1].strip() if i+1 < len(parts) else ""
            
            full_article = f"{header}\n{content}"
            
            # Extract Article Number
            number_match = re.search(r'\d+', header)
            article_number = number_match.group(0) if number_match else None
            
            # Handling huge articles (rare but possible) -> Parent/Child chunking could be added here
            # For now, we keep it atomic as per strict user rule.
            
            chunks.append({
                "content": full_article,
                "chunk_type": "article",
                "article_number": article_number,
                "metadata": {"header": header}
            })
            
        return chunks

class JurisprudenceFullParser:
    """
    Parses Single Full Decisions (Arrêts).
    Structure: Header -> Form -> Reasoning (Fond) -> Operative (Dispositif).
    """
    @staticmethod
    def split(text: str) -> List[Dict[str, Any]]:
        chunks = []
        
        # Heuristics for sections
        # Normalize slightly for matching
        clean_text = text.replace('أ', 'ا').replace('إ', 'ا') 
        
        # 1. Operative Part (Dispositif) - High Priority
        operative_start = -1
        operative_keywords = ["لهذه الاسباب", "ولهذه الاسباب", "par ces motifs"]
        for kw in operative_keywords:
            idx = clean_text.find(kw)
            if idx != -1:
                operative_start = idx
                break
        
        # 2. Reasoning (Fond) - Medium Priority
        reasoning_start = -1
        reasoning_keywords = ["من حيث الموضوع", "في الموضوع", "sur le fond", "حيث"]
        # "Hithou" (حيث) is tricky as it repeats, we want the block start. 
        # Usually "Sur la forme" comes before.
        
        form_start = -1
        form_keywords = ["من حيث الشكل", "في الشكل", "sur la forme", "من حيث الاجراءات"]
        for kw in form_keywords:
            idx = clean_text.find(kw)
            if idx != -1:
                form_start = idx
                break

        # Define Boundaries (simplified logic)
        # Header: 0 -> form_start or reasoning_start
        # Form: form_start -> reasoning_start (if exists)
        # Reasoning: reasoning_start -> operative_start
        # Operative: operative_start -> end
        
        # Allow fallback if structural keywords missing
        if operative_start == -1 and form_start == -1:
             return GenericSplitter.split(text, chunk_type="full_decision_fallback")

        current_pos = 0
        
        # Header Chunk
        end_header = form_start if form_start != -1 else (operative_start if operative_start != -1 else len(text))
        if end_header > 0:
            chunks.append({
                "content": text[0:end_header].strip(),
                "chunk_type": "header",
                "metadata": {"section": "header"}
            })
            current_pos = end_header
            
        # Form Chunk
        if form_start != -1:
            end_form = operative_start if operative_start != -1 else len(text)
            # Refine: Reasoning often starts between Form and Operative
            # Let's try to split Form/Reasoning roughly by "Hithou" density or specific header
            # For simplicity in V1, we lump Form+Reasoning unless we found "Min Haythou Mawdou" inside
            
            # Try to find Reasoning start AFER Form start
            sub_text = clean_text[form_start:end_form]
            rel_reasoning_idx = -1
            for kw in ["من حيث الموضوع", "في الموضوع"]:
                found = sub_text.find(kw)
                if found != -1:
                    rel_reasoning_idx = found
                    break
            
            if rel_reasoning_idx != -1:
                abs_reasoning = form_start + rel_reasoning_idx
                # Form
                chunks.append({
                    "content": text[form_start:abs_reasoning].strip(),
                    "chunk_type": "form",
                    "metadata": {"section": "form"}
                })
                # Reasoning
                reasoning_text = text[abs_reasoning:end_form]
                # Reasoning is KEY -> Split it if too long
                reasoning_chunks = GenericSplitter.split_by_tokens(reasoning_text, 1000, 100)
                for i, rc in enumerate(reasoning_chunks):
                    chunks.append({
                        "content": rc,
                        "chunk_type": "reasoning",
                        "chunk_index_internal": i,
                        "metadata": {"section": "reasoning"}
                    })
            else:
                # Lumped Form/Reasoning
                chunks.append({
                    "content": text[form_start:end_form].strip(),
                    "chunk_type": "form_and_reasoning",
                    "metadata": {"section": "form_reasoning"}
                })
        
        # Operative Chunk
        if operative_start != -1:
            chunks.append({
                "content": text[operative_start:].strip(),
                "chunk_type": "operative",
                "metadata": {"section": "operative"}
            })
            
        return chunks

class JurisprudenceSummaryParser:
    """
    Parses compilations of summaries (e.g. from compilation files).
    Splits by visual separators '---' or '## القرار'.
    """
    @staticmethod
    def split(text: str) -> List[Dict[str, Any]]:
        chunks = []
        # Split by the common separator used in the viewed files
        raw_parts = re.split(r'\n-{3,}\n', text)
        
        for part in raw_parts:
            if not part.strip(): continue
            
            # Basic Classification
            ctype = "summary"
            if "المبدأ القانوني" in part:
                ctype = "principle_summary"
            
            # Extract Decision Number if possible
            num_match = re.search(r'القرار رقم\s*(\d+)', part)
            decision_num = num_match.group(1) if num_match else None
            
            chunks.append({
                "content": part.strip(),
                "chunk_type": ctype,
                "article_number": decision_num, # Overloaded field for Decision ID
                "metadata": {"decision_number": decision_num}
            })
        return chunks

class GenericSplitter:
    @staticmethod
    def split(text: str, chunk_type="generic") -> List[Dict[str, Any]]:
        raw_chunks = GenericSplitter.split_by_tokens(text)
        return [{"content": rc, "chunk_type": chunk_type, "metadata": {}} for rc in raw_chunks]

    @staticmethod
    def split_by_tokens(text: str, chunk_size=800, overlap=100) -> List[str]:
        # Simple word-based approx for speed (1 word ~= 1.3 tokens for Arabic approx)
        # Better to just split by chars for robustness if no tokenizer library
        # Avg char/token in Arabic is ~4-5
        char_limit = chunk_size * 4 
        overlap_char = overlap * 4
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + char_limit
            # Try to find a space near the end to avoid breaking words
            if end < len(text):
                while end > start and text[end] not in [' ', '\n', '.', '،']:
                    end -= 1
                if end == start: # Force split if no delimiter found
                    end = start + char_limit
            
            chunks.append(text[start:end])
            start = end - overlap_char
            if start < 0: start = 0 # Safety
            if start >= len(text): break # Avoid infinite loop
            
        return chunks
