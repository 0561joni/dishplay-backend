# app/services/semantic_search_service.py
import os
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from sentence_transformers import SentenceTransformer
import torch
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Configuration
MODEL_NAME = "BAAI/bge-m3"
SIMILARITY_THRESHOLD = 0.8  # Minimum cosine similarity for a match
SUPABASE_BUCKET = "dishes-photos"

# Global model instance (loaded once)
_model = None
_model_lock = False


def get_embedding_model():
    """Load and cache the sentence transformer model"""
    global _model, _model_lock

    if _model is not None:
        return _model

    # Prevent multiple threads from loading simultaneously
    if _model_lock:
        # Wait for the other thread to finish loading
        import time
        while _model_lock and _model is None:
            time.sleep(0.1)
        return _model

    try:
        _model_lock = True
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = SentenceTransformer(MODEL_NAME, device=device)
        logger.info(f"Model loaded successfully on {device}")
        return _model
    finally:
        _model_lock = False


async def search_similar_dishes(
    query_name: str,
    query_description: Optional[str] = None,
    top_k: int = 3,
    threshold: float = SIMILARITY_THRESHOLD
) -> List[Dict[str, any]]:
    """
    Search for similar dishes using semantic search via pgvector.

    Args:
        query_name: Name of the dish to search for
        query_description: Optional description of the dish
        top_k: Number of top results to return (default: 3)
        threshold: Minimum similarity threshold (default: 0.8)

    Returns:
        List of dicts with keys: name_opt, title, description, type, similarity, image_url
    """
    try:
        # Build query text (combining name and description)
        query_text = query_name
        if query_description:
            query_text = f"{query_name}. {query_description}"

        logger.info(f"Searching for similar dishes: '{query_text[:100]}...'")

        # Generate embedding for the query
        model = get_embedding_model()
        query_embedding = model.encode(
            [query_text],
            normalize_embeddings=True,
            convert_to_numpy=True
        )[0]

        # Convert to list for JSON serialization
        query_embedding_list = query_embedding.tolist()

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
            # Build image URL from Supabase storage
            image_url = get_image_url_from_storage(row['name_opt'])

            results.append({
                'name_opt': row['name_opt'],
                'title': row['title'],
                'description': row['description'],
                'type': row['type'],
                'similarity': row['similarity'],
                'image_url': image_url
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


def get_image_url_from_storage(name_opt: str) -> str:
    """
    Get public URL for an image from Supabase storage.

    Args:
        name_opt: The name_opt identifier from prompts_meta table

    Returns:
        Public URL to the image
    """
    try:
        supabase = get_supabase_client()

        # Images are stored with .jpg extension
        file_path = f"{name_opt}.jpg"

        # Get public URL
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(file_path)

        return public_url

    except Exception as e:
        logger.error(f"Error getting image URL for {name_opt}: {str(e)}")
        return ""


async def log_missing_dish(
    title: str,
    description: Optional[str] = None
) -> None:
    """
    Log a dish that didn't have a close semantic match to items_without_pictures table.

    Args:
        title: Name of the dish
        description: Optional description of the dish
    """
    try:
        supabase = get_supabase_client()

        # Insert into items_without_pictures table
        response = supabase.table("items_without_pictures").insert({
            "title": title,
            "description": description or ""
        }).execute()

        logger.info(f"Logged missing dish: {title}")

    except Exception as e:
        logger.error(f"Error logging missing dish: {str(e)}")
        # Don't fail the main request if logging fails


async def search_dishes_batch(
    items: List[Dict[str, str]],
    top_k: int = 3,
    threshold: float = SIMILARITY_THRESHOLD
) -> Dict[str, List[Dict[str, any]]]:
    """
    Search for similar dishes for multiple items.

    Args:
        items: List of dicts with 'id', 'name', and optional 'description'
        top_k: Number of top results per item
        threshold: Minimum similarity threshold

    Returns:
        Dict mapping item_id to list of matching dishes
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


def generate_embedding_for_text(text: str) -> np.ndarray:
    """
    Generate normalized embedding for a given text.
    Useful for creating embeddings to upload to Supabase.

    Args:
        text: Text to embed

    Returns:
        Normalized embedding as numpy array
    """
    model = get_embedding_model()
    embedding = model.encode(
        [text],
        normalize_embeddings=True,
        convert_to_numpy=True
    )[0]
    return embedding
