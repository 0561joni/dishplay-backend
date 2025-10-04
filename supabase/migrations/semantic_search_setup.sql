-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create table for dish embeddings and metadata
CREATE TABLE IF NOT EXISTS dish_embeddings (
    id BIGSERIAL PRIMARY KEY,
    name_opt TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    type TEXT,
    embedding vector(1024),  -- BAAI/bge-m3 produces 1024-dimensional embeddings
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for vector similarity search (using cosine distance)
-- Using ivfflat index for better performance on larger datasets
CREATE INDEX IF NOT EXISTS dish_embeddings_embedding_idx
ON dish_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create table for items without pictures (for tracking unmatched dishes)
CREATE TABLE IF NOT EXISTS items_without_pictures (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    title TEXT NOT NULL,
    description TEXT
);

-- Create index on created_at for efficient querying
CREATE INDEX IF NOT EXISTS items_without_pictures_created_at_idx
ON items_without_pictures (created_at DESC);

-- Create function for similarity search
CREATE OR REPLACE FUNCTION search_dish_embeddings(
    query_embedding vector(1024),
    match_threshold FLOAT DEFAULT 0.8,
    match_count INT DEFAULT 3
)
RETURNS TABLE (
    name_opt TEXT,
    title TEXT,
    description TEXT,
    type TEXT,
    similarity FLOAT
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
    WHERE 1 - (dish_embeddings.embedding <=> query_embedding) >= match_threshold
    ORDER BY dish_embeddings.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at
CREATE TRIGGER update_dish_embeddings_updated_at
    BEFORE UPDATE ON dish_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comment to table
COMMENT ON TABLE dish_embeddings IS 'Stores dish embeddings for semantic search using BAAI/bge-m3 model';
COMMENT ON TABLE items_without_pictures IS 'Tracks menu items that did not have close semantic matches';
COMMENT ON FUNCTION search_dish_embeddings IS 'Performs vector similarity search on dish embeddings using cosine similarity';
