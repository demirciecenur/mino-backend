# Backend Structure Documentation

## 📁 Directory Structure

```
backend/
├── config/                 # Configuration files
│   ├── __init__.py
│   ├── settings.py         # Application settings and constants
│   └── firebase_config.py  # Firebase initialization
├── models/                 # Pydantic models for API
│   ├── __init__.py
│   ├── tts_models.py       # TTS request/response models
│   ├── llm_models.py       # LLM request/response models
│   ├── video_models.py     # Video composition models
│   └── receipt_models.py   # Receipt verification models
├── services/               # Business logic services
│   ├── __init__.py
│   ├── tts_service.py     # TTS generation service
│   ├── llm_service.py     # LLM response service
│   ├── video_service.py   # Video composition service
│   └── audio_storage_service.py  # Audio file management
├── utils/                  # Utility functions
│   ├── __init__.py
│   ├── text_cleaner.py    # Text cleaning for TTS
│   ├── audio_converter.py # MP3 to WAV conversion
│   └── audio_generator.py # Silent audio generation
├── routes/                 # API route handlers
│   ├── __init__.py
│   ├── tts_routes.py      # TTS endpoints
│   ├── llm_routes.py      # LLM endpoints
│   ├── video_routes.py   # Video endpoints
│   └── audio_routes.py   # Audio serving endpoints
├── main.py                # FastAPI app initialization
├── template_renderer.py   # Scene template renderer
├── scene_templates.json   # Scene template definitions
├── generate_character_audios.py  # Script to generate all audios
└── pre_generate_cacheable_scenes.py  # Script to cache common scenes
```

## 🔄 Migration Plan

### Phase 1: Extract Configuration ✅
- [x] Move settings to `config/settings.py`
- [x] Move Firebase config to `config/firebase_config.py`

### Phase 2: Extract Models ✅
- [x] Move Pydantic models to `models/`

### Phase 3: Extract Utilities ✅
- [x] Move text cleaning to `utils/text_cleaner.py`
- [x] Move audio conversion to `utils/audio_converter.py`
- [x] Move audio generation to `utils/audio_generator.py`

### Phase 4: Extract Services ⏳
- [ ] Move TTS logic to `services/tts_service.py`
- [ ] Move LLM logic to `services/llm_service.py`
- [ ] Move video logic to `services/video_service.py`
- [ ] Move audio storage to `services/audio_storage_service.py`

### Phase 5: Extract Routes ⏳
- [ ] Move TTS endpoints to `routes/tts_routes.py`
- [ ] Move LLM endpoints to `routes/llm_routes.py`
- [ ] Move video endpoints to `routes/video_routes.py`
- [ ] Move audio serving to `routes/audio_routes.py`

### Phase 6: Refactor main.py ⏳
- [ ] Simplify `main.py` to only app initialization
- [ ] Import routes and register them
- [ ] Remove duplicate code

## 📝 Usage

### After Refactoring

**main.py** will only contain:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings
from routes import tts_routes, llm_routes, video_routes, audio_routes

app = FastAPI(title="Mino Backend API", version="1.0.0")

# CORS middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    ...
)

# Register routes
app.include_router(tts_routes.router, prefix="/api", tags=["TTS"])
app.include_router(llm_routes.router, prefix="/api", tags=["LLM"])
app.include_router(video_routes.router, prefix="/api", tags=["Video"])
app.include_router(audio_routes.router, prefix="/api", tags=["Audio"])
```

**Services** will be called from routes:
```python
# routes/tts_routes.py
from services import TTSService

@router.post("/tts")
async def generate_tts_endpoint(request: TTSRequest):
    service = TTSService()
    return await service.generate(request)
```

## ✅ Benefits

1. **Modularity**: Each module has a single responsibility
2. **Testability**: Services can be tested independently
3. **Maintainability**: Easier to find and modify code
4. **Scalability**: Easy to add new features
5. **Reusability**: Services can be used by multiple routes

