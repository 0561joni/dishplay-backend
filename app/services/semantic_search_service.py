# app/services/semantic_search_service.py
import os
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from openai import OpenAI
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Configuration
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"  # Fast and cheap OpenAI model
SIMILARITY_THRESHOLD = 0.7  # Minimum cosine similarity for a match
SUPABASE_BUCKET = "menu-images"  # Bucket name
SUPABASE_FOLDER = "dishes-photos"  # Folder within bucket

# Global OpenAI client
_openai_client = None


def get_openai_client():
    """Get or create OpenAI client"""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


async def search_similar_dishes(
    query_name: str,
    query_description: Optional[str] = None,
    top_k: int = 1,
    threshold: float = SIMILARITY_THRESHOLD
) -> List[Dict[str, any]]:
    """
    Search for similar dishes using semantic search via pgvector.

    Args:
        query_name: Name of the dish to search for
        query_description: Optional description of the dish
        top_k: Number of top results to return (default: 1 - only best match)
        threshold: Minimum similarity threshold (default: 0.7)

    Returns:
        List of dicts with keys: name_opt, title, description, type, similarity, image_url
        Returns only the single best match (top_k=1)
    """
    try:
        # Build query text (combining name and description)
        query_text = query_name
        if query_description:
            query_text = f"{query_name}. {query_description}"

        logger.info(f"Searching for similar dishes: '{query_text[:100]}...'")

        # Generate embedding for the query using OpenAI
        client = get_openai_client()
        response = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=query_text
        )
        query_embedding_list = response.data[0].embedding

        # Query Supabase using pgvector similarity search
        supabase = get_supabase_client()

        # Use RPC function for vector similarity search
        # This assumes you have a stored procedure in Supabase for vector search
        response = supabase.rpc(
            'search_dish_embeddings',
            {
                'query_embedding': query_embedding_list,
                'match_threshold': threshold,
                'match_count': top_k
            }
        ).execute()

        if not response.data:
            logger.info(f"No similar dishes found above threshold {threshold}")
            return []

        results = []
        for row in response.data:
            # Build image URLs from Supabase storage (try multiple patterns)
            image_urls = get_image_urls_from_storage(row['name_opt'])

            results.append({
                'name_opt': row['name_opt'],
                'title': row['title'],
                'description': row['description'],
                'type': row['type'],
                'similarity': row['similarity'],
                'image_url': image_urls[0] if image_urls else ''  # Primary URL
            })

            logger.info(
                f"Found match: {row['title']} "
                f"(similarity: {row['similarity']:.3f})"
            )

        return results

    except Exception as e:
        logger.error(f"Error in semantic search: {str(e)}", exc_info=True)
        # Return empty list on error - will fallback to Google/DALL-E
        return []


def get_image_urls_from_storage(name_opt: str) -> List[str]:
    """
    Get possible public URLs for an image from Supabase storage.

    The name_opt format is: {id}-{sequence}-{dish-name}_{description}
    e.g., 5334-0004-yaki-udon-organic-tofu_fried-udon-noodles-with-vegetables-egg-teriyaki

    Images may have different suffixes or none at all, so we return multiple possible URLs.

    Args:
        name_opt: The name_opt identifier from the database

    Returns:
        List of possible URLs (in order of likelihood)
    """
    try:
        supabase = get_supabase_client()

        # Try different filename patterns in order of likelihood
        patterns = [
            f"{name_opt}_00001_.png",       # Most common: with _00001_ suffix
            f"{name_opt}.png",              # Without suffix
            f"{name_opt}_00001_.jpg",       # JPG with suffix
            f"{name_opt}.jpg",              # JPG without suffix
        ]

        urls = []
        for pattern in patterns:
            file_path = f"{SUPABASE_FOLDER}/{pattern}"
            public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(file_path)

            # Remove trailing '?' that Supabase client adds
            if public_url.endswith('?'):
                public_url = public_url[:-1]

            urls.append(public_url)

        logger.info(f"Generated {len(urls)} possible URLs for {name_opt}")
        return urls

    except Exception as e:
        logger.error(f"Error getting image URLs for {name_opt}: {str(e)}")
        return []


async def log_missing_dish(
    title: str,
    description: Optional[str] = None
) -> None:
    """
    Log a dish that didn't have a close semantic match to items_without_pictures table.
    Checks for duplicates before inserting.

    Args:
        title: Name of the dish
        description: Optional description of the dish
    """
    try:
        supabase = get_supabase_client()

        # Check if this item already exists (by title and description)
        desc = description or ""
        existing = supabase.table("items_without_pictures") \
            .select("id") \
            .eq("title", title) \
            .eq("description", desc) \
            .execute()

        if existing.data and len(existing.data) > 0:
            logger.info(f"Dish already in items_without_pictures: {title}")
            return

        # Insert into items_without_pictures table
        response = supabase.table("items_without_pictures").insert({
            "title": title,
            "description": desc
        }).execute()

        logger.info(f"Logged new missing dish: {title}")

    except Exception as e:
        logger.error(f"Error logging missing dish: {str(e)}")
        # Don't fail the main request if logging fails


async def search_dishes_batch(
    items: List[Dict[str, str]],
    top_k: int = 1,
    threshold: float = SIMILARITY_THRESHOLD
) -> Dict[str, List[Dict[str, any]]]:
    """
    Search for similar dishes for multiple items.

    Args:
        items: List of dicts with 'id', 'name', and optional 'description'
        top_k: Number of top results per item (default: 1 - only best match)
        threshold: Minimum similarity threshold

    Returns:
        Dict mapping item_id to list of matching dishes (single best match per item)
    """
    results = {}

    for item in items:
        item_id = item['id']
        name = item['name']
        description = item.get('description')

        matches = await search_similar_dishes(
            query_name=name,
            query_description=description,
            top_k=top_k,
            threshold=threshold
        )

        results[item_id] = matches

        # Log items without matches
        if not matches:
            await log_missing_dish(name, description)

    return results


def generate_embedding_for_text(text: str) -> List[float]:
    """
    Generate embedding for a given text using OpenAI.
    Useful for creating embeddings to upload to Supabase.

    Args:
        text: Text to embed

    Returns:
        Embedding as list of floats
    """
    client = get_openai_client()
    response = client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding
