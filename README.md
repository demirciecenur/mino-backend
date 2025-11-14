# Mino Backend

Python backend for the Mino iOS app using FastAPI, fal.ai, and Firebase.

## Features

- **TTS Generation**: Using fal.ai or ElevenLabs for text-to-speech
- **LLM Integration**: OpenAI GPT for generating questions and responses
- **Video Composition**: fal.ai mmaudio-v2 for combining video and audio
- **Firebase Integration**: Firestore for sessions, Storage for media files
- **Receipt Verification**: App Store receipt validation

## Setup

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Firebase Setup**:

   - Create a Firebase project
   - Download the service account JSON file
   - Place it as `firebase-service-account.json` in the backend directory
   - Update the storage bucket name in `.env`

4. **Get API Keys**:
   - **OpenAI**: Get API key from https://platform.openai.com/
   - **fal.ai**: Get API key from https://fal.ai/
   - **ElevenLabs** (optional): Get API key from https://elevenlabs.io/

## Running the Backend

```bash
# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

- `POST /tts` - Generate TTS audio
- `POST /llm/question` - Generate LLM question
- `POST /llm/followup` - Generate LLM followup
- `POST /compose` - Compose video with audio
- `POST /iap/verify` - Verify App Store receipt
- `POST /summary` - Save session summary
- `GET /health` - Health check

## fal.ai Integration

The backend uses fal.ai for:

- **TTS**: Text-to-speech generation
- **Video Composition**: Combining video and audio using mmaudio-v2 model

## Firebase Integration

- **Firestore**: Stores session data and user interactions
- **Storage**: Stores generated audio and video files

## Development Notes

- The backend is designed to work with the iOS app's state management
- All endpoints return JSON responses compatible with Swift models
- CORS is configured to allow iOS app requests
- Error handling includes proper HTTP status codes
