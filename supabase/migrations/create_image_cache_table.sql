-- Create table for cached food images
CREATE TABLE IF NOT EXISTS cached_food_images (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    storage_path TEXT NOT NULL UNIQUE,
    storage_url TEXT NOT NULL,
    original_url TEXT,
    item_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    file_size INTEGER,
    image_width INTEGER,
    image_height INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    use_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

-- Create indexes for efficient searching
CREATE INDEX idx_cached_food_images_normalized_name ON cached_food_images(normalized_name);
CREATE INDEX idx_cached_food_images_category ON cached_food_images(category);
CREATE INDEX idx_cached_food_images_active ON cached_food_images(is_active);
CREATE INDEX idx_cached_food_images_created_at ON cached_food_images(created_at DESC);

-- Create storage bucket for cached images if it doesn't exist
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'menu-images-cache',
    'menu-images-cache',
    true,
    10485760, -- 10MB limit
    ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/gif']
)
ON CONFLICT (id) DO NOTHING;

-- Enable RLS
ALTER TABLE cached_food_images ENABLE ROW LEVEL SECURITY;

-- Allow public read access
CREATE POLICY "Allow public read access" ON cached_food_images
    FOR SELECT USING (is_active = true);

-- Allow authenticated users to insert
CREATE POLICY "Allow authenticated insert" ON cached_food_images
    FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- Allow authenticated users to update their own entries
CREATE POLICY "Allow authenticated update" ON cached_food_images
    FOR UPDATE USING (auth.role() = 'authenticated');