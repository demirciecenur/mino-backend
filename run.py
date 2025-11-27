#!/usr/bin/env python3
"""
Development server runner for Mino Backend
"""
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("RELOAD", "true").lower() == "true"
    
    print(f"Starting Mino Backend on {host}:{port}")
    print(f"Reload: {reload}")
    
    # Configure uvicorn logging
    # Reduce log spam by filtering out bot/scanner traffic
    # Access logs will show legitimate requests (INFO level for debugging)
    import logging
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)  # Log all access requests (for debugging TTS/video requests)
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        access_log=True,  # Keep access logs but filtered by middleware
        # Filter out 404s from access logs (they're mostly bot traffic)
        # This is handled by BotTrafficFilterMiddleware
    )
