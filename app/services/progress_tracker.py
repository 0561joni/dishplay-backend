from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import asyncio
import json
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class ProgressTracker:
    def __init__(self):
        self._progress_data: Dict[str, Dict[str, Any]] = {}
        self._subscribers: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
        
        # Time estimates based on historical data (in seconds)
        self.stage_estimates = {
            "image_processing": 2.0,
            "menu_extraction": 3.5,
            "language_detection": 0.5,
            "translation": 1.5,
            "image_search_per_item": 0.3,
            "database_operations": 1.0
        }
        
        self.loading_messages = [
            {"text": "Teaching AI to read chef's handwriting...", "emoji": "🤖✍️"},
            {"text": "Negotiating with the menu for better prices...", "emoji": "💰"},
            {"text": "Asking ChatGPT what 'deconstructed' actually means...", "emoji": "🤔"},
            {"text": "Converting calories to happiness units...", "emoji": "📊"},
            {"text": "Translating 'artisanal' to 'expensive'...", "emoji": "💸"},
            {"text": "Finding images prettier than the actual food...", "emoji": "📸"},
            {"text": "Convincing vegetables they're delicious...", "emoji": "🥗"},
            {"text": "Teaching our AI the difference between 'crispy' and 'burnt'...", "emoji": "🔥"},
            {"text": "Googling what a 'gastropub' is... again...", "emoji": "🍺"},
            {"text": "Making your menu 73% more appetizing...", "emoji": "✨"}
        ]
    
    async def start_tracking(self, task_id: str, estimated_items: int = 10) -> None:
        """Start tracking progress for a task"""
        async with self._lock:
            total_time = self._calculate_total_time(estimated_items)
            self._progress_data[task_id] = {
                "status": "processing",
                "stage": "starting",
                "progress": 0,
                "message": self.loading_messages[0],
                "started_at": datetime.utcnow(),
                "estimated_total_time": total_time,
                "estimated_completion": datetime.utcnow() + timedelta(seconds=total_time),
                "item_count": estimated_items,
                "menu_title": "Uploaded Menu",
                "stages_completed": [],
                "current_stage_start": datetime.utcnow()
            }
            logger.info(f"Started tracking task {task_id} with estimated time: {total_time}s")
    
    def _calculate_total_time(self, item_count: int) -> float:
        """Calculate estimated total time based on item count"""
        base_time = (
            self.stage_estimates["image_processing"] +
            self.stage_estimates["menu_extraction"] +
            self.stage_estimates["language_detection"] +
            self.stage_estimates["translation"] +
            self.stage_estimates["database_operations"]
        )
        image_search_time = self.stage_estimates["image_search_per_item"] * item_count
        return base_time + image_search_time
    
    async def update_progress(self, task_id: str, stage: str, progress: float, 
                            extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Update progress for a task"""
        async with self._lock:
            if task_id not in self._progress_data:
                logger.warning(f"Task {task_id} not found in progress tracker")
                return
            
            data = self._progress_data[task_id]
            data["stage"] = stage
            data["progress"] = progress
            
            # Update message based on progress
            message_index = min(int(progress / 10), len(self.loading_messages) - 1)
            data["message"] = self.loading_messages[message_index]
            
            # Calculate time remaining
            elapsed = (datetime.utcnow() - data["started_at"]).total_seconds()
            if progress > 0:
                estimated_total = elapsed / (progress / 100)
                remaining = max(0, estimated_total - elapsed)
                data["estimated_time_remaining"] = remaining
                data["estimated_completion"] = datetime.utcnow() + timedelta(seconds=remaining)
            
            # Update stage timing
            data["stages_completed"].append({
                "stage": stage,
                "duration": (datetime.utcnow() - data["current_stage_start"]).total_seconds()
            })
            data["current_stage_start"] = datetime.utcnow()
            
            # Add any extra data
            if extra_data:
                data.update(extra_data)
            
            # Notify subscribers
            await self._notify_subscribers(task_id, data)
    
    async def complete_task(self, task_id: str, success: bool = True) -> None:
        """Mark a task as completed"""
        async with self._lock:
            if task_id not in self._progress_data:
                return
            
            data = self._progress_data[task_id]
            data["status"] = "completed" if success else "failed"
            data["progress"] = 100 if success else data.get("progress", 0)
            data["completed_at"] = datetime.utcnow()
            data["total_duration"] = (datetime.utcnow() - data["started_at"]).total_seconds()
            
            # Final notification
            await self._notify_subscribers(task_id, data)
            
            # Clean up after a delay
            asyncio.create_task(self._cleanup_task(task_id))
    
    async def _cleanup_task(self, task_id: str, delay: int = 300):
        """Clean up task data after delay (5 minutes)"""
        await asyncio.sleep(delay)
        async with self._lock:
            self._progress_data.pop(task_id, None)
            self._subscribers.pop(task_id, None)
    
    async def get_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current progress for a task"""
        async with self._lock:
            data = self._progress_data.get(task_id)
            if data:
                # Create a copy to avoid modification
                return {
                    "status": data["status"],
                    "stage": data["stage"],
                    "progress": data["progress"],
                    "message": data["message"],
                    "estimated_time_remaining": data.get("estimated_time_remaining", 0),
                    "item_count": data.get("item_count", 0),
                    "menu_title": data.get("menu_title"),
                    "elapsed_time": (datetime.utcnow() - data["started_at"]).total_seconds()
                }
            return None
    
    async def subscribe(self, task_id: str, callback):
        """Subscribe to progress updates for a task"""
        async with self._lock:
            self._subscribers[task_id].append(callback)
    
    async def unsubscribe(self, task_id: str, callback):
        """Unsubscribe from progress updates"""
        async with self._lock:
            if task_id in self._subscribers:
                self._subscribers[task_id].remove(callback)
    
    async def _notify_subscribers(self, task_id: str, data: Dict[str, Any]):
        """Notify all subscribers of progress update"""
        for callback in self._subscribers.get(task_id, []):
            try:
                await callback(data)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")

# Global instance
progress_tracker = ProgressTracker()