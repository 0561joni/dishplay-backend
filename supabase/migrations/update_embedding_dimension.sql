-- Update dish_embeddings table to use 1536 dimensions (OpenAI text-embedding-3-small)
-- Previous: 1024 dimensions (BGE-M3)

-- Drop the existing table and recreate with correct dimensions
DROP TABLE IF EXISTS dish_embeddings;

CREATE TABLE dish_embeddings (
    id BIGSERIAL PRIMARY KEY,
    name_opt TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    type TEXT DEFAULT 'food',
    embedding vector(1536) NOT NULL,  -- Changed from 1024 to 1536
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for vector similarity search
CREATE INDEX ON dish_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Update the search function to use the new dimension
CREATE OR REPLACE FUNCTION search_dish_embeddings(
    query_embedding vector(1536),  -- Changed from 1024 to 1536
    match_threshold float DEFAULT 0.8,
    match_count int DEFAULT 3
)
RETURNS TABLE (
    name_opt text,
    title text,
    description text,
    type text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dish_embeddings.name_opt,
        dish_embeddings.title,
        dish_embeddings.description,
        dish_embeddings.type,
        1 - (dish_embeddings.embedding <=> query_embedding) AS similarity
    FROM dish_embeddings
    WHERE 1 - (dish_embeddings.embedding <=> query_embedding) > match_threshold
    ORDER BY dish_embeddings.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
