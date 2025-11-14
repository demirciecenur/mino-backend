"""Firebase configuration and initialization."""

import os
import firebase_admin
from firebase_admin import credentials, firestore, storage, auth
from google.cloud import firestore_v1
from typing import Optional
from .settings import Settings


class FirebaseConfig:
    """Firebase configuration and client management."""
    
    def __init__(self):
        self.db: Optional[firestore.Client] = None
        self.bucket: Optional[storage.Bucket] = None
        self._initialized = False
        
    def initialize(self) -> bool:
        """Initialize Firebase Admin SDK."""
        if self._initialized:
            return True
            
        try:
            settings = Settings()
            cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred, {
                'storageBucket': settings.FIREBASE_STORAGE_BUCKET
            })
            # Use specified database name (default: 'mino')
            # Convert Firebase Admin credentials to google-auth credentials
            from google.oauth2 import service_account
            import json
            
            # Load service account JSON to get credentials
            with open(settings.FIREBASE_SERVICE_ACCOUNT_PATH, 'r') as f:
                service_account_info = json.load(f)
            
            google_cred = service_account.Credentials.from_service_account_info(service_account_info)
            project_id = settings.FIREBASE_PROJECT_ID or service_account_info.get('project_id')
            
            # Create Firestore client with database parameter
            self.db = firestore_v1.Client(
                project=project_id,
                credentials=google_cred,
                database=settings.FIREBASE_FIRESTORE_DATABASE
            )
            self.bucket = storage.bucket()
            
            # Test if bucket exists
            try:
                self.bucket.exists()
                print(f"✅ Firebase Storage bucket connected: {self.bucket.name}")
            except Exception as e:
                print(f"⚠️ Firebase Storage bucket not accessible: {e}")
                self.bucket = None
                
            self._initialized = True
            return True
            
        except Exception as e:
            print(f"❌ Firebase initialization failed: {e}")
            self.db = None
            self.bucket = None
            return False
    
    async def verify_token(self, authorization: Optional[str]) -> Optional[str]:
        """Verify Firebase Auth token and return user ID."""
        if not authorization or not authorization.startswith("Bearer "):
            # For development, allow requests without auth
            print("⚠️ No auth token provided - allowing for development")
            return None
        
        token = authorization.replace("Bearer ", "")
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token.get("uid")
        except Exception as e:
            print(f"⚠️ Auth verification failed: {e}")
            return None


# Global Firebase config instance
_firebase_config: Optional[FirebaseConfig] = None


def get_firebase_config() -> FirebaseConfig:
    """Get Firebase configuration instance (singleton)."""
    global _firebase_config
    if _firebase_config is None:
        _firebase_config = FirebaseConfig()
        _firebase_config.initialize()
    return _firebase_config
