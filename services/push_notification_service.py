"""FCM Push Notification Service for parent notifications.

Uses Firebase Cloud Messaging (FCM) REST API to send push notifications
to parent devices via APNs (Apple Push Notification Service).
"""

import httpx
import json
from typing import List, Optional, Dict
from datetime import datetime
import os
from config.settings import Settings
from services.notification_templates import get_notification_message


class PushNotificationService:
    """Service for sending push notifications via FCM."""
    
    def __init__(self):
        self.settings = Settings()
        # FCM uses Firebase Admin SDK credentials
        # For REST API, we need the server key from Firebase Console
        # This should be set in environment variable FCM_SERVER_KEY
        self.fcm_server_key = self.settings.FCM_SERVER_KEY or os.getenv('FCM_SERVER_KEY', '')
        self.fcm_url = "https://fcm.googleapis.com/fcm/send"
        
        # Track logged errors to avoid spam (reset every hour)
        self._logged_errors: Dict[str, datetime] = {}
        self._error_log_reset_time = datetime.now()
        
        if self.fcm_server_key:
            # Validate FCM Server Key format (should start with AAAA)
            if not self.fcm_server_key.startswith('AAAA'):
                print(f"⚠️ FCM Server Key format may be incorrect (should start with 'AAAA'): {self.fcm_server_key[:20]}...")
            else:
                print(f"✅ FCM Server Key loaded: {self.fcm_server_key[:20]}...")
        else:
            print("⚠️ FCM_SERVER_KEY not set - push notifications will be disabled")
            print("   To enable: Set FCM_SERVER_KEY in .env file (get from Firebase Console → Cloud Messaging → Server key)")
    
    def _should_log_error(self, error_key: str) -> bool:
        """Check if we should log this error (avoid spam for same errors)."""
        now = datetime.now()
        
        # Reset error log every hour
        if (now - self._error_log_reset_time).total_seconds() > 3600:
            self._logged_errors.clear()
            self._error_log_reset_time = now
        
        # Log if we haven't seen this error in the last hour
        if error_key not in self._logged_errors:
            self._logged_errors[error_key] = now
            return True
        
        # Don't log if we've seen this error recently (within last hour)
        return False
        
    async def send_notification(
        self,
        device_tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict] = None
    ) -> Dict[str, any]:
        """Send push notification to iOS devices via FCM.
        
        Args:
            device_tokens: List of FCM device tokens
            title: Notification title
            body: Notification body text
            data: Optional custom data payload
            
        Returns:
            Dict with 'success' (bool) and 'results' (list of per-token results)
        """
        if not self.fcm_server_key:
            print("⚠️ FCM_SERVER_KEY not set, skipping push notification")
            return {"success": False, "error": "FCM_SERVER_KEY not configured"}
        
        if not device_tokens:
            print("⚠️ No device tokens provided")
            return {"success": False, "error": "No device tokens"}
        
        # FCM supports up to 1000 tokens per request
        # For multiple tokens, we can use topic messaging or send individually
        # For now, send to each token individually for better error handling
        
        results = []
        success_count = 0
        
        for token in device_tokens:
            try:
                # FCM message format for iOS (APNs)
                message = {
                    "to": token,
                    "notification": {
                        "title": title,
                        "body": body,
                        "sound": "default",
                        "badge": "1"
                    },
                    "apns": {
                        "payload": {
                            "aps": {
                                "alert": {
                                    "title": title,
                                    "body": body
                                },
                                "sound": "default",
                                "badge": 1,
                                "content-available": 1
                            }
                        }
                    },
                    "priority": "high"
                }
                
                # Add custom data if provided
                if data:
                    message["data"] = data
                
                # Send via FCM REST API
                headers = {
                    "Authorization": f"key={self.fcm_server_key}",
                    "Content-Type": "application/json"
                }
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        self.fcm_url,
                        json=message,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success") == 1:
                            success_count += 1
                            results.append({"token": token, "success": True})
                            print(f"✅ Push notification sent to {token[:20]}...")
                        else:
                            error = result.get("results", [{}])[0].get("error", "Unknown error")
                            results.append({"token": token, "success": False, "error": error})
                            print(f"❌ Failed to send to {token[:20]}...: {error}")
                    else:
                        error_text = response.text[:200] if hasattr(response, 'text') else str(response.status_code)
                        results.append({"token": token, "success": False, "error": error_text})
                        
                        # Better error messages for common FCM errors (log once per error type per hour)
                        error_key = f"{response.status_code}_{token[:20]}"
                        
                        # FCM 404 errors are silently ignored (FCM Legacy API may be disabled or deprecated)
                        # No logging to avoid log spam - user has configured p8 file but Legacy API may not be available
                        if response.status_code == 404:
                            # Silently skip - FCM Legacy API endpoint not found (likely deprecated or disabled)
                            pass
                        elif response.status_code == 401:
                            if self._should_log_error("401_auth"):
                                print(f"❌ FCM API 401 error: Unauthorized - FCM Server Key is invalid")
                                print("   Fix: Get correct FCM Server Key from Firebase Console → Cloud Messaging → Server key")
                                print("   (This error will be logged once per hour)")
                        elif response.status_code == 400:
                            if self._should_log_error(error_key):
                                print(f"❌ FCM API 400 error for {token[:20]}...: Bad Request - Check message format")
                                print("   (This error will be logged once per hour per token)")
                        else:
                            if self._should_log_error(error_key):
                                print(f"❌ FCM API error for {token[:20]}...: {response.status_code} - {error_text}")
                                print("   (This error will be logged once per hour per token)")
                        
            except Exception as e:
                results.append({"token": token, "success": False, "error": str(e)})
                print(f"❌ Exception sending to {token[:20]}...: {e}")
        
        return {
            "success": success_count > 0,
            "success_count": success_count,
            "total_count": len(device_tokens),
            "results": results
        }
    
    async def send_story_completion_notification(
        self,
        device_tokens: List[str],
        character: str,
        topic: str,
        language: str = "en",
        child_name: Optional[str] = None,
        story_id: Optional[str] = None
    ) -> Dict[str, any]:
        """Send story completion notification to parents.
        
        Args:
            device_tokens: List of parent device tokens
            character: Character name (e.g., "Luna", "Mino")
            topic: Story topic (e.g., "sharing", "bedtime")
            language: Language code (en, tr, fr, de, es)
            child_name: Optional child name for personalization
            story_id: Optional story ID for deep linking
            
        Returns:
            Dict with send results
        """
        # Get notification message from templates
        message_data = get_notification_message(
            character=character,
            topic=topic,
            language=language,
            child_name=child_name
        )
        
        # Prepare custom data for deep linking
        data_payload = {
            "type": "story_completed",
            "character": character,
            "topic": topic,
            "language": language,
            "activity_tip": message_data.get("activity_tip", "")
        }
        
        if story_id:
            data_payload["story_id"] = story_id
        
        # Send notification
        return await self.send_notification(
            device_tokens=device_tokens,
            title=message_data["title"],
            body=message_data["body"],
            data=data_payload
        )


# Global service instance
_push_notification_service: Optional[PushNotificationService] = None


def get_push_notification_service() -> PushNotificationService:
    """Get push notification service instance (singleton)."""
    global _push_notification_service
    if _push_notification_service is None:
        _push_notification_service = PushNotificationService()
    return _push_notification_service

