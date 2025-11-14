"""Delayed notification scheduler for story completion events.

Schedules push notifications to be sent 5 minutes after story completion.
Uses asyncio for simple delayed execution (no Celery dependency needed for MVP).
"""

import asyncio
from typing import Optional
from datetime import datetime
from services.push_notification_service import get_push_notification_service
from config.firebase_config import get_firebase_config
from firebase_admin import firestore


def ensure_parent_exists(db, parent_id: str) -> bool:
    """Ensure parent document exists in Firestore. Creates minimal parent record if missing.
    
    Args:
        db: Firestore client
        parent_id: Parent user ID (from Firebase Auth anonymous sign-in)
    
    Returns:
        True if parent exists or was created, False if error
    """
    if not db:
        return False
    
    try:
        parent_ref = db.collection("parents").document(parent_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            # Create minimal parent record (device token will be added later via register-device)
            parent_ref.set({
                "device_tokens": [],
                "notification_consent": False,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Auto-created parent document: {parent_id}")
        return True
    except Exception as e:
        print(f"❌ Error ensuring parent exists: {e}")
        return False


async def schedule_delayed_notification(
    event_id: str,
    parent_id: str,
    character: str,
    topic: str,
    language: str = "en",
    story_id: Optional[str] = None,
    child_name: Optional[str] = None,
    delay_minutes: int = 5
):
    """Schedule a delayed push notification for story completion.
    
    Args:
        event_id: Story event ID
        parent_id: Parent user ID
        character: Character name
        topic: Story topic
        language: Language code
        story_id: Optional story ID
        child_name: Optional child name for personalization (defaults to 'your child' if not provided)
        delay_minutes: Delay in minutes before sending (default: 5)
    """
    # Run in background task (non-blocking)
    asyncio.create_task(
        _send_delayed_notification(
            event_id=event_id,
            parent_id=parent_id,
            character=character,
            topic=topic,
            language=language,
            story_id=story_id,
            child_name=child_name,
            delay_seconds=delay_minutes * 60
        )
    )
    print(f"📅 Scheduled notification for event {event_id} in {delay_minutes} minutes")


async def _send_delayed_notification(
    event_id: str,
    parent_id: str,
    character: str,
    topic: str,
    language: str,
    story_id: Optional[str],
    child_name: Optional[str],
    delay_seconds: int
):
    """Internal function to wait and send notification."""
    try:
        # Wait for delay
        await asyncio.sleep(delay_seconds)
        
        # Get Firestore instance
        firebase_config = get_firebase_config()
        db = firebase_config.db
        
        if not db:
            print(f"⚠️ Firestore not available, skipping notification for event {event_id}")
            return
        
        # Check if event still exists and hasn't been notified
        event_ref = db.collection("story_events").document(event_id)
        event_doc = event_ref.get()
        
        if not event_doc.exists:
            print(f"⚠️ Event {event_id} not found, skipping notification")
            return
        
        event_data = event_doc.to_dict()
        if event_data.get("notified", False):
            print(f"⚠️ Event {event_id} already notified, skipping")
            return
        
        # Ensure parent exists (auto-create if missing for anonymous users)
        if not ensure_parent_exists(db, parent_id):
            print(f"⚠️ Could not ensure parent exists: {parent_id}, skipping notification")
            return
        
        # Get parent device tokens
        parent_ref = db.collection("parents").document(parent_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            print(f"⚠️ Parent {parent_id} not found after ensure_parent_exists, skipping notification")
            return
        
        parent_data = parent_doc.to_dict()
        
        # Check consent
        if not parent_data.get("notification_consent", False):
            print(f"⚠️ Parent {parent_id} has not consented to notifications")
            # Mark as notified anyway to avoid retry
            event_ref.update({"notified": True})
            return
        
        device_tokens = parent_data.get("device_tokens", [])
        if not device_tokens:
            print(f"⚠️ No device tokens for parent {parent_id}")
            # Mark as notified anyway
            event_ref.update({"notified": True})
            return
        
        # Get child_name from parent data if not provided (for future use)
        # Priority: provided child_name > parent.child_name > None (will use "your child" in template)
        notification_child_name = child_name
        if not notification_child_name:
            notification_child_name = parent_data.get("child_name")
        
        # Send notification
        push_service = get_push_notification_service()
        result = await push_service.send_story_completion_notification(
            device_tokens=device_tokens,
            character=character,
            topic=topic,
            language=language,
            child_name=notification_child_name,
            story_id=story_id
        )
        
        # Mark event as notified
        event_ref.update({
            "notified": True,
            "notification_sent_at": firestore.SERVER_TIMESTAMP,
            "notification_success": result.get("success", False)
        })
        
        if result.get("success"):
            print(f"✅ Notification sent for event {event_id} to {result.get('success_count', 0)} device(s)")
        else:
            print(f"⚠️ Notification failed for event {event_id}: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error sending delayed notification for event {event_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to mark as notified to avoid infinite retries
        try:
            firebase_config = get_firebase_config()
            db = firebase_config.db
            if db:
                event_ref = db.collection("story_events").document(event_id)
                event_ref.update({
                    "notified": True,
                    "notification_error": str(e)
                })
        except:
            pass

