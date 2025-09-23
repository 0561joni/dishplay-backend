DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'menus'
          AND column_name = 'original_image_url'
    ) THEN
        ALTER TABLE public.menus RENAME COLUMN original_image_url TO title;
    END IF;
END $$;
