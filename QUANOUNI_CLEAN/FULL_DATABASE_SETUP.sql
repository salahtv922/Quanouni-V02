-- ============================================
-- QANOUNI-AI: FULL DATABASE SETUP SCRIPT
-- Version: 2.0 (Smart Legal Edition)
-- Date: 16 Jan 2026
--
-- INSTRUCTIONS:
-- 1. Go to Supabase SQL Editor.
-- 2. Paste this entire script.
-- 3. Run it.
-- ============================================

-- --------------------------------------------------------
-- SECTION 1: EXTENSIONS & CLEANUP
-- --------------------------------------------------------

-- Enable Vector Extension (Critical for RAG)
CREATE EXTENSION IF NOT EXISTS vector;

-- Cleanup existing tables (Uncomment if doing a full reset)
-- DROP TABLE IF EXISTS audit_logs CASCADE;
-- DROP TABLE IF EXISTS chunk CASCADE;
-- DROP TABLE IF EXISTS cases CASCADE;
-- DROP TABLE IF EXISTS documents CASCADE;
-- DROP TABLE IF EXISTS users CASCADE;


-- --------------------------------------------------------
-- SECTION 2: USERS & AUTHENTICATION
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    email TEXT,
    role TEXT DEFAULT 'normal', -- 'normal', 'premium', 'admin'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policy: Users can see own profile
DROP POLICY IF EXISTS "Users can see own profile" ON users;
CREATE POLICY "Users can see own profile" ON users
    FOR SELECT USING (auth.uid() = id);


-- --------------------------------------------------------
-- SECTION 3: DOCUMENTS & CHUNKS (RAG CORE)
-- --------------------------------------------------------

-- 3.1 Documents Table (Source Files)
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('law', 'jurisprudence_full', 'jurisprudence_summary')),
    
    -- Metadata
    jurisdiction TEXT,      -- 'محكمة_عليا', 'مجلس_الدولة'
    law_name TEXT,          -- 'Code Penal', etc.
    total_chunks INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for Documents
CREATE INDEX IF NOT EXISTS idx_docs_category ON documents(category);
CREATE INDEX IF NOT EXISTS idx_docs_jurisdiction ON documents(jurisdiction);


-- 3.2 Chunk Table (Vector Search Units)
CREATE TABLE IF NOT EXISTS chunk (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    
    content TEXT NOT NULL,
    embedding VECTOR(768), -- Gemini Embedding Dimension
    
    -- Smart Legal Facets
    chunk_type TEXT,        -- 'article', 'principle', 'reasoning'
    article_number TEXT,    -- '124', '40' (for exact lookup)
    
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Optimized Indexes for Chunks
CREATE INDEX IF NOT EXISTS chunk_embedding_idx ON chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_chunk_type ON chunk(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunk_article ON chunk(article_number);
-- Full Text Search Index (Arabic Optimized)
CREATE INDEX IF NOT EXISTS chunk_content_fts ON chunk USING gin (to_tsvector('arabic', content));


-- --------------------------------------------------------
-- SECTION 4: RPC FUNCTION (HYBRID SEARCH ENGINE)
-- --------------------------------------------------------

CREATE OR REPLACE FUNCTION match_documents(
    query_embedding VECTOR(768),
    match_count INT DEFAULT 10,
    filter_category TEXT DEFAULT NULL,
    filter_jurisdiction TEXT DEFAULT NULL,
    filter_chunk_type TEXT DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    content TEXT,
    metadata JSONB,
    similarity FLOAT,
    document_id BIGINT,
    chunk_index INT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.content,
        c.metadata,
        1 - (c.embedding <=> query_embedding) AS similarity,
        c.document_id,
        c.chunk_index
    FROM chunk c
    JOIN documents d ON c.document_id = d.id
    WHERE 
        (filter_category IS NULL OR d.category = filter_category)
        AND (filter_jurisdiction IS NULL OR d.jurisdiction = filter_jurisdiction)
        AND (filter_chunk_type IS NULL OR c.chunk_type = filter_chunk_type)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- --------------------------------------------------------
-- SECTION 5: CASES MANAGEMENT (ADVOCATE MODE)
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE, -- Link to user
    case_number TEXT NOT NULL,
    case_type TEXT NOT NULL,
    court TEXT NOT NULL,
    status TEXT DEFAULT 'جاري',
    
    -- Structured Data
    defendant_name TEXT,
    plaintiff_name TEXT,
    charges TEXT[],
    facts TEXT, 
    
    -- Rich Data
    parties JSONB DEFAULT '{}'::jsonb,
    evidence JSONB DEFAULT '{}'::jsonb,
    timeline JSONB DEFAULT '[]'::jsonb,
    
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS cases_case_number_idx ON cases(case_number);
CREATE INDEX IF NOT EXISTS cases_user_id_idx ON cases(user_id);

ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
-- Policy can be refined to restrict access to owner only
-- CREATE POLICY "Users see own cases" ON cases FOR ALL USING (user_id = auth.uid());


-- --------------------------------------------------------
-- SECTION 6: AUDIT LOGS
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    username TEXT, 
    action TEXT NOT NULL, 
    resource TEXT, 
    details JSONB DEFAULT '{}'::jsonb, 
    ip_address TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user_time ON audit_logs(user_id, timestamp DESC);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Everyone insert logs" ON audit_logs FOR INSERT WITH CHECK (true);

-- --------------------------------------------------------
-- DONE
-- --------------------------------------------------------
SELECT 'Database Setup Completed Successfully! 🚀' as status;
