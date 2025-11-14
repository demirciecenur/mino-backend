"""Video generation utilities using FAL.ai."""

import os
import httpx
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import fal_client
from PIL import Image


async def generate_character_video(
    character_name: str,
    action: str,
    profile_image_path: Optional[str] = None,
    reference_image_2_path: Optional[str] = None,
    output_dir: Path = None,
    background_style: Optional[str] = None,
    previous_action: Optional[str] = None,
    next_action: Optional[str] = None
) -> Optional[str]:
    """
    Generate character video from profile image using FAL.ai (image-to-video, 3D animation).
    Profile fotoğrafından 3D animasyonlu MP4 üretir.
    
    Args:
        character_name: Character name (e.g., "koko", "elsa")
        action: Video action (e.g., "idle", "speak", "listen", "wave", "wave_greeting", "talking", etc.)
        profile_image_path: Path to character profile image (REQUIRED for image-to-video)
        reference_image_2_path: Optional second reference image for better character consistency
        output_dir: Directory to save the video
        
    Returns:
        Path to generated video file, or None if failed
    """
    try:
        fal_api_key = os.getenv('FAL_API_KEY')
        if not fal_api_key:
            print("❌ FAL_API_KEY not found")
            return None
        
        # Profile image path'i otomatik bul (eğer verilmemişse)
        if not profile_image_path:
            # Default path: mino/Assets/characters/{character}/{character}_profile.{ext}
            project_root = Path(__file__).parent.parent.parent
            char_dir = project_root / "mino" / "Assets" / "characters" / character_name.lower()
            
            # Try different extensions
            for ext in ["png", "jpg", "jpeg"]:
                potential_path = char_dir / f"{character_name.lower()}_profile.{ext}"
                if potential_path.exists():
                    profile_image_path = str(potential_path)
                    break
        
        if not profile_image_path or not Path(profile_image_path).exists():
            print(f"❌ Profile image not found: {profile_image_path}")
            print(f"   Expected: mino/Assets/characters/{character_name.lower()}/{character_name.lower()}_profile.png/jpg")
            return None
        
        print(f"📸 Using profile image: {profile_image_path}")
        # NOT: İkinci görsel referansı kullanılmıyor (maliyetli) - sadece tek görsel kullanılıyor
        
        # FRAME-TO-FRAME CONTINUITY: Önceki videonun son frame'ini extract et
        # Eğer previous_action varsa ve önceki video mevcutsa, son frame'ini kullan
        previous_video_last_frame = None
        if previous_action and output_dir:
            previous_video_path = output_dir / f"{character_name}_{previous_action}.mp4"
            if previous_video_path.exists():
                try:
                    # FFmpeg ile son frame'i extract et
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_frame:
                        tmp_frame_path = tmp_frame.name
                    
                    # FFmpeg komutu: video'nun son frame'ini extract et
                    # -sseof -1: Video'nun sonundan 1 saniye önce başla
                    # -update 1: Sadece 1 frame al
                    # -q:v 1: Yüksek kalite
                    cmd = [
                        'ffmpeg',
                        '-sseof', '-1',  # Son 1 saniyeden başla
                        '-i', str(previous_video_path),
                        '-update', '1',  # Sadece 1 frame
                        '-q:v', '1',  # Yüksek kalite
                        '-y',  # Overwrite output
                        tmp_frame_path
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode == 0 and Path(tmp_frame_path).exists():
                        previous_video_last_frame = tmp_frame_path
                        print(f"🎬 Extracted last frame from {previous_action} video: {tmp_frame_path}")
                        print(f"   This frame will be used as the starting reference for {action}")
                    else:
                        print(f"⚠️ Failed to extract last frame from {previous_action} video")
                        if result.stderr:
                            print(f"   FFmpeg error: {result.stderr[:200]}")
                        # Clean up failed temp file
                        if Path(tmp_frame_path).exists():
                            Path(tmp_frame_path).unlink()
                except subprocess.TimeoutExpired:
                    print(f"⚠️ FFmpeg timeout while extracting frame from {previous_action}")
                except FileNotFoundError:
                    print(f"⚠️ FFmpeg not found - frame extraction skipped")
                except Exception as e:
                    print(f"⚠️ Error extracting last frame: {e}")
        
        # Image-to-video model seçimi: KALİTE ÖNCELİKLİ (telefon/mock call için)
        # Model adayları (araştırma sonuçlarına göre optimize edildi)
        # NOT: Ses üretimine gerek yok, ses dosyası ayrı oluşturuluyor
        # NOT: İki görsel desteği kaldırıldı (maliyetli) - sadece tek görsel kullanılıyor
        # HEDEF: Telefonda gösterilecek, mock call'da dönecek - 9:16 portrait, yüksek karakter tutarlılığı
        #
        # ARAŞTIRMA SONUÇLARI (Deep Search):
        # Veo 3.1: ✅ Referans görsellerle karakter tutarlılığı (en iyi), 4K kalite, gerçekçi fizik
        #          ❌ Image-to-video sadece 16:9 (beta) - 9:16 DESTEKLEMİYOR!
        #          ⚠️ Maliyet: ~$1.00/8 saniye (pahalı)
        # Kling 2.5 Turbo Pro: ✅ Image-to-video esnek, sinematik motion, 1080p
        #                      ✅ Tüm aspect ratio'ları destekliyor (9:16 dahil)
        #                      ✅ Sinematik kamera hareketleri, aksiyon sahneleri için ideal
        #                      ⚠️ Karakter tutarlılığı belirsiz (güçlü prompt ile optimize edilebilir)
        #                      ⚠️ Maliyet: Orta seviye
        #
        # SONUÇ: Kling 2.5 Turbo Pro ÖNCELİKLİ (9:16 desteği + esneklik + sinematik kalite)
        #        Veo 3.1 fallback (karakter tutarlılığı için, ama 16:9 limiti var)
        
        model_candidates = [
            "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",  # Kling 2.5 Turbo Pro - ÖNCELİKLİ! 9:16 desteği, sinematik motion, esnek
            "fal-ai/veo3.1/image-to-video",  # Veo 3.1 - Fallback (karakter tutarlılığı için, ama 16:9 limiti)
            "fal-ai/sora-2/image-to-video",  # OpenAI Sora 2 - Yüksek kalite fallback
            "fal-ai/wan/v2.2-a14b/image-to-video",  # Wan 2.2 - Fallback (açık kaynak)
            "fal-ai/wan-i2v",  # Wan 2.1 - Son çare fallback
            "fal-ai/svd",  # Son çare fallback
        ]
        
        model_path = None
        for candidate in model_candidates:
            # İlk modeli kullan, hata alırsak diğerlerini dene
            model_path = candidate
            print(f"🎥 Trying model: {model_path}")
            break  # İlk modeli kullan, hata durumunda exception handling ile diğerlerini dene
        
        # Universal Child Animation Scene Prompts (10 sahne seti)
        # Dil bağımsız, hareket, mimik, ortam ve duygu açısından zengin
        # Pixar-style 3D animation, çocuklara hitap eden parlak, pozitif, doğal
        # CRITICAL: Bu videolar story scene'leri arasında SMOOTH TRANSITIONS için kullanılacak
        # Her video, bir önceki ve bir sonraki sahne ile TUTARLI geçiş yapmalı
        # Video başlangıcı ve bitişi, diğer scene videoları ile seamless loop oluşturmalı
        scene_prompts = {
            # Wave (Universal - used for both greeting and goodbye)
            # TRANSITION NOTE: Bu video story'nin açılışında greeting, kapanışında goodbye olarak kullanılır
            # Context'e göre: opening → friendly greeting wave, closure → warm goodbye wave
            "wave": "A cute 3D cartoon character waves enthusiastically with their right hand (or both hands for goodbye). Their wrist is gently tilted in a friendly motion. They smile warmly, showing their upper teeth, with one eye half-blinking naturally and their hair/accessories softly bouncing from the wave. Their mouth moves naturally as if greeting or saying goodbye to the viewer. The character's expression is warm and inviting - friendly greeting energy at the start, affectionate farewell energy at the end. MAGICAL WAVE EFFECTS: As the character waves, beautiful magical elements appear from their hands - colorful hearts (💖) float out gently, twinkling stars (⭐) sparkle and rise, warm golden light rays (✨) emanate from their fingertips, and sweet kiss symbols (💋) float playfully in the air. These magical elements should appear naturally during the wave motion, creating a joyful, positive, and enchanting atmosphere. The effects should be subtle, child-friendly, and enhance the warm greeting/farewell feeling. Pixar-style lighting and realism. 12-second continuous animation with engaging secondary motions: subtle breathing, eye blinks every 3 seconds, gentle head movements, and natural hair/accessory physics. The wave motion should be smooth and rhythmic, creating a welcoming or farewell moment filled with magical joy. TRANSITION: Video can start from a natural pose (or from 'talking' for goodbye) and end transitioning to 'talking' (for greeting) or end in a warm farewell pose (for goodbye after 'talking'). The wave should be smooth and natural, ready to connect to speaking scenes. For greeting: natural pose → wave → talking. For goodbye: talking → wave → farewell pose. ENDING POSE (greeting): Character's hand returns to a neutral position, body facing forward, ready for 'talking' scene. ENDING POSE (goodbye): Character ends in a warm farewell pose with hand lowered, completing the story circle. BACKGROUND CONSISTENCY: If this is the first scene, establish the background theme. If this is a middle/last scene, use the EXACT same background as the first scene - same camera angle, lighting, perspective, and background elements.",
            
            # Talking & Explaining
            # TRANSITION NOTE: Bu video tüm essential action'lardan ve tüm essential action'lara smooth geçiş yapmalı
            "talking": "The same character stands calmly, speaking in a clear, friendly manner. Their mouth moves smoothly, synchronized to gentle speech. One hand moves slightly while they gesture naturally as they explain something - alternating between left and right hand gestures every 2-3 seconds to keep it engaging. Their eyes are expressive, eyebrows occasionally lifting, creating a warm storytelling atmosphere. The scene radiates calm focus and warmth. 12-second continuous animation with engaging secondary motions: subtle breathing, eye blinks every 3 seconds, gentle head nods, micro-expressions that show engagement, and natural hand gestures that vary subtly to maintain interest. The character should feel alive and present, like a caring teacher or storyteller. TRANSITION: Video loops seamlessly and can transition smoothly to 'wave' (for goodbye), 'raise_hand', 'hand_on_hip', 'lean_closer', or 'side_glance' scenes. Can also transition FROM 'wave' (greeting), 'raise_hand', 'hand_on_hip', 'lean_closer' (after question), or 'side_glance'. STARTING POSE: Character stands naturally, facing forward, hands in neutral position (ready to receive from previous scene - EXACT match to previous scene's ending). ENDING POSE: Character returns to same natural standing pose, facing forward, hands in neutral position (ready to transition to next scene - EXACT match for next scene's starting). Start and end poses should match for perfect looping. BACKGROUND CONSISTENCY: Use the EXACT same background as the first scene - same camera angle, lighting, perspective, and background elements. NO background changes, NO camera movement - seamless continuity.",
            
            # Scene 3: Raising Hand for Emphasis
            # TRANSITION NOTE: Bu video "talking" veya "hand_on_hip" sonrası kullanılır, "talking" veya "hand_on_hip" ile smooth geçiş yapmalı
            "raise_hand": "The character raises their right hand confidently, palm facing up as if making an important point. Their expression is bright and encouraging. Head slightly nods forward for emphasis. Their eyes sparkle with excitement, and their hair/accessories sway gently. The lighting highlights their face softly, creating a sense of energy and inspiration. 12-second continuous animation: hand raises smoothly (2-3 seconds), holds the gesture with subtle finger movements and slight hand adjustments (4-5 seconds), then smoothly lowers back to neutral (2-3 seconds). Throughout, engaging secondary motions: subtle breathing, eye blinks, gentle head movements, and natural body sway. The gesture should feel dynamic and engaging, like emphasizing an important teaching moment. TRANSITION: Video starts from a natural speaking pose (from 'talking' or 'hand_on_hip') and ends ready to transition back to 'talking' or 'hand_on_hip'. STARTING POSE: Character stands naturally, facing forward, hands in neutral position (EXACT match to 'talking' or 'hand_on_hip' ending - frame by frame continuity). ENDING POSE: Hand smoothly returns to neutral position, body facing forward, ready for 'talking' or 'hand_on_hip' (EXACT match for next scene's starting - seamless connection). Hand movement should be smooth and return to a neutral position for seamless looping. Bidirectional: can transition FROM and TO 'talking' and 'hand_on_hip'. BACKGROUND CONSISTENCY: Use the EXACT same background as the first scene - same camera angle, lighting, perspective, and background elements. NO background changes, NO camera movement - seamless continuity.",
            
            # Scene 4: Hand on Hip, Playful Attitude
            # TRANSITION NOTE: Bu video "instruction" sahnelerinde kullanılır, "talking", "raise_hand", "side_glance" ile smooth geçiş yapmalı
            "hand_on_hip": "The 3D character places one hand on their hip with a light, confident smile, leaning slightly to one side (5-10 degrees). Their eyebrows lift playfully, creating a teaching or 'you can do it!' vibe. The other hand gestures briefly as they talk, with natural hand movements that emphasize points. The motion is smooth and rhythmic, evoking the energy of a caring teacher or mentor in a story. 12-second continuous animation: hand moves to hip smoothly (1-2 seconds), maintains the pose with subtle body movements, gentle leans, and occasional hand gestures with the free hand (6-8 seconds), then smoothly returns to neutral (2-3 seconds). Engaging secondary motions: subtle breathing, eye blinks, gentle head movements, and natural body sway. The pose should feel confident and encouraging. TRANSITION: Video loops seamlessly and can transition to 'talking', 'raise_hand', or 'side_glance'. Can also transition FROM 'talking', 'raise_hand', or 'side_glance'. STARTING POSE: Character stands naturally, facing forward, hands in neutral position (EXACT match to 'talking', 'raise_hand', or 'side_glance' ending - frame by frame continuity). ENDING POSE: Hand returns from hip to neutral position, body facing forward, ready for 'talking', 'raise_hand', or 'side_glance' (EXACT match for next scene's starting - seamless connection). The pose should be maintainable for smooth scene connections. Bidirectional transitions ensure natural flow. BACKGROUND CONSISTENCY: Use the EXACT same background as the first scene - same camera angle, lighting, perspective, and background elements. NO background changes, NO camera movement - seamless continuity.",
            
            # Scene 5: Leaning Closer (Curious Question)
            # TRANSITION NOTE: Bu video "talking" sonrası soru sorarken kullanılır, soru cevaplandıktan sonra "talking" ile smooth geçiş yapmalı
            # CRITICAL: Karakter ekrana BELİRGİN şekilde yaklaşmalı - "slightly" değil, "clearly" ve "noticeably"
            "lean_closer": "The character CLEARLY and NOTICEABLY leans forward toward the camera, moving their upper body significantly closer to the viewer (20-30 cm forward movement). Their head tilts forward and down, bringing their face noticeably closer to the screen. Their eyes widen with interest, mouth forming the start of a question. The character's entire upper body moves forward - shoulders, chest, and head all move closer to the camera in a smooth, deliberate motion. Their smile is curious yet friendly. The scene creates an intimate, child-engaging moment with the character clearly closer to the viewer. 12-second continuous animation: smooth lean forward (2-3 seconds), holds the close position with engaging eye contact, subtle head movements, and curious expressions (4-5 seconds), then smoothly returns to neutral standing position (2-3 seconds). Engaging secondary motions: eye blinks, subtle facial expressions showing curiosity, and natural breathing. The lean should be OBVIOUS and visible, creating a moment of connection. TRANSITION: Video starts from a natural speaking pose (from 'talking'), leans in CLEARLY and NOTICEABLY, and ends in a position ready to transition back to 'talking' (after question is answered). STARTING POSE: Character stands naturally, facing forward, hands in neutral position (EXACT match to 'talking' ending - frame by frame continuity). ENDING POSE: Character returns to natural standing position, facing forward, hands in neutral position (EXACT match for 'talking' to respond - seamless connection). The lean should be OBVIOUS and visible, then return naturally for looping. Flow: talking → lean_closer (ask question) → talking (respond to answer). BACKGROUND CONSISTENCY: Use the EXACT same background as the first scene - same camera angle, lighting, perspective, and background elements. NO background changes, NO camera movement - seamless continuity. The background should remain static while only the character moves.",
            
            # Scene 6: Listening / Waiting Mode
            # TRANSITION NOTE: Bu video "lean_closer" veya "question" sonrası kullanılır, "talking" ile smooth geçiş yapmalı
            "listen": "The character stops talking and listens attentively. Their facial expression softens into a warm, patient smile. They blink naturally and maintain subtle idle movements — small head nods, slight breathing, and gentle hand relaxation. Their eyes focus on the viewer as if waiting for an answer. Soft ambient light flickers through the cozy room. TRANSITION: Video loops seamlessly and can transition smoothly to 'talking' or 'storytelling' when the character responds. The listening pose should be natural and ready for speech.",
            
            # Scene 7: Playful Foot Tap (Idle Movement)
            # TRANSITION NOTE: Bu video "followup" sahnelerinde kullanılır, "talking" ile smooth geçiş yapmalı
            # Legacy: Foot Tap (replaced by side_glance for followup scenes)
            "foot_tap": "The character stands casually, one leg bent slightly. They tap their foot rhythmically in a playful way while humming or smiling silently. Their expression is cheerful and lively. The animation shows natural balance shifts and soft cloth movement. Light shadows move subtly across the floor, keeping the scene dynamic but calm. TRANSITION: Video loops seamlessly and can transition to 'talking' or 'hand_on_hip'. The foot tap should be rhythmic and natural, ready to stop for speech. NOTE: This action is legacy - use 'side_glance' for followup scenes instead.",
            
            # Scene 8: Side Glance & Mischievous Smile
            # TRANSITION NOTE: Bu video "speak" veya "followup" sahnelerinde kullanılır, "talking" ve "hand_on_hip" ile smooth geçiş yapmalı
            "side_glance": "The character looks sideways with a mischievous grin, one eyebrow raised slightly. Their body follows with a small twist (10-15 degrees), then they glance back toward the viewer, smiling kindly. This motion is quick and expressive, showing curiosity and humor. Hair and clothing react naturally to the movement. Lighting accentuates their expression gently. 12-second continuous animation: quick side glance (1-2 seconds), holds the glance with playful expression and subtle body movement (2-3 seconds), then smoothly returns to center facing forward (1-2 seconds), maintains center position with engaging expressions (4-5 seconds). Engaging secondary motions: eye blinks, subtle head movements, natural breathing, and playful micro-expressions. The glance should feel spontaneous and engaging. TRANSITION: Video loops seamlessly and can transition to 'talking' or 'hand_on_hip'. Can also transition FROM 'talking' or 'hand_on_hip'. STARTING POSE: Character stands naturally, facing forward, hands in neutral position (EXACT match to 'talking' or 'hand_on_hip' ending - frame by frame continuity). ENDING POSE: Character returns to center, facing forward, hands in neutral position (EXACT match for 'talking' or 'hand_on_hip' starting - seamless connection). The glance should return to center naturally for smooth connections. Bidirectional transitions ensure natural flow between speaking and playful moments. BACKGROUND CONSISTENCY: Use the EXACT same background as the first scene - same camera angle, lighting, perspective, and background elements. NO background changes, NO camera movement - seamless continuity.",
            
            # Legacy: Storytelling (replaced by hand_on_hip for instruction scenes)
            # TRANSITION NOTE: Bu video artık kullanılmıyor - "instruction" sahneleri için "hand_on_hip" kullanılmalı
            "storytelling": "The character resumes speaking with enthusiastic hand gestures, expressive eyes, and a bright smile. Their movements are rhythmic, and their upper body subtly shifts as they emphasize certain phrases. Their energy feels like a cheerful storyteller addressing children directly. Smooth lip sync motion suitable for any spoken language. The atmosphere stays cozy, vivid, and emotionally warm. TRANSITION: Video loops seamlessly and can transition smoothly to 'talking', 'raise_hand', 'hand_on_hip', or 'lean_closer'. Gestures should be natural and return to center for perfect looping. NOTE: This action is legacy - use 'hand_on_hip' for instruction scenes instead.",
            
            # Legacy actions (backward compatibility - not used in new stories)
            "idle": "Character from the photo is breathing gently, very subtle body movements, calm and peaceful expression, slight head movement, soft natural 3D animation, character stays in same position with gentle breathing motion. TRANSITION: Video loops seamlessly and can transition to 'talking' or 'wave'. The idle pose should be neutral and ready for any scene transition.",
            "speak": "Character from the photo is speaking, lips moving naturally in 3D animation, mouth movements synchronized with speech, gentle hand gestures, storytelling expression, character's face animating naturally as if telling a story. TRANSITION: Video loops seamlessly and can transition to 'listen', 'talking', or 'wave'. Start and end poses should match for perfect looping."
        }
        
        # Get scene prompt or fallback to idle
        motion_prompt = scene_prompts.get(action, scene_prompts.get("idle", scene_prompts["talking"]))
        
        # Character-specific magical emoji for wave action (her karakter özel bir emoji kullanır)
        character_wave_emojis = {
            # Original characters
            "mino": "🌟",  # Star (space theme)
            "luna": "✨",  # Sparkles (magical theme)
            "tiko": "🌳",  # Tree (forest theme)
            "bubu": "💙",  # Blue heart (calm theme)
            "sunny": "☀️",  # Sun (sunny theme)
            "koko": "🦇",  # Bat (adventure theme)
            # Derivative characters
            "elsa": "❄️",  # Snowflake (ice theme)
            "elisa the ice fairy": "❄️",
            "tom": "🐱",  # Cat (cat theme)
            "sneaky cat tom": "🐱",
            "jerry": "🧀",  # Cheese (mouse theme)
            "clever mouse jerry": "🧀",
            "ninjaturtles": "🥷",  # Ninja (ninja theme)
            "shell heroes crew": "🥷",
            "spiderman": "🕷️",  # Spider (spider theme)
            "spider fighter": "🕷️",
            "minion": "💛",  # Yellow heart (yellow buddy theme)
            "yellow buddy": "💛",
            "tweety": "🐦",  # Bird (bird theme)
            "chirpy birdie": "🐦",
            "spongebob": "🧽",  # Sponge (sponge theme)
            "bubble buddy": "🧽",
        }
        
        # Eğer wave action ise, karakter özel emoji'yi prompt'a ekle
        if action == "wave":
            char_key = character_name.lower()
            wave_emoji = character_wave_emojis.get(char_key, "💖")  # Default: heart
            # Prompt'taki [CHARACTER_SPECIFIC_EMOJI] placeholder'ını gerçek emoji ile değiştir
            motion_prompt = motion_prompt.replace("[CHARACTER_SPECIFIC_EMOJI]", wave_emoji)
            print(f"✨ Wave emoji for {character_name}: {wave_emoji}")
        
        # Character-specific background styles (pre-school friendly, stable, character-appropriate)
        # Each character has a unique background theme that matches their personality and original inspiration
        character_backgrounds = {
            # Original characters
            "mino": "space adventure theme with twinkling stars, colorful planets in soft pastel hues, cozy space station interior with friendly alien decorations, gentle nebula clouds in purple and blue, warm space lighting, preschool-friendly bright and cheerful cosmic atmosphere",
            "luna": "magical dreamy forest with soft moonlit glades, twinkling stars visible through tree branches, cozy mushroom houses with warm glowing windows, pastel purple and blue tones, gentle fairy lights dancing, soft fireflies, preschool-friendly enchanting nighttime wonderland",
            "tiko": "playful forest playground with colorful trees, soft green grass, gentle sunlight filtering through leaves creating dappled shadows, friendly woodland creatures visible in background, bright green and yellow tones, natural wooden play elements, preschool-friendly adventurous forest atmosphere",
            "bubu": "calm and soothing indoor space with soft pastel walls in lavender and light blue, cozy reading nook with plush cushions and soft blankets, gentle warm lighting from a reading lamp, peaceful atmosphere with soft blue and lavender tones, preschool-friendly comforting and safe environment",
            "sunny": "bright and cheerful sunny meadow with colorful wildflowers in yellow, pink, and blue, clear blue sky with fluffy white clouds, warm golden sunlight creating soft shadows, playful butterflies fluttering, vibrant yellow and orange tones, preschool-friendly joyful and energetic atmosphere",
            "koko": "forest playground with natural wooden elements, soft earth tones of brown and green, gentle tree canopy overhead providing dappled shade, adventure-themed but safe and cozy, natural rocks and logs, preschool-friendly brave explorer atmosphere with nature elements",
            
            # Derivative characters (ASO-safe names)
            "elsa": "ice castle with soft pastel colors in blue and white, gentle snowflakes falling softly, crystal-like structures with warm glowing lights, magical winter wonderland with blue and white tones, soft ice formations, preschool-friendly enchanting frozen palace atmosphere",
            "elisa the ice fairy": "ice castle with soft pastel colors in blue and white, gentle snowflakes falling softly, crystal-like structures with warm glowing lights, magical winter wonderland with blue and white tones, soft ice formations, preschool-friendly enchanting frozen palace atmosphere",
            "spider fighter": "city playground with friendly urban elements, soft city skyline in background with colorful buildings, bright and safe urban environment, red and blue tones, friendly street elements, preschool-friendly heroic city adventure atmosphere",
            "yellow buddy": "playful laboratory with colorful gadgets in bright yellow and blue, soft bright yellow and blue tones, friendly scientific elements like test tubes and beakers, cheerful and energetic atmosphere, fun science decorations, preschool-friendly fun and educational environment",
            "chirpy birdie": "sunny garden with colorful flowers in red, yellow, and pink, soft birdhouse visible in background, gentle breeze moving leaves, warm yellow and green tones, friendly garden elements, preschool-friendly cheerful and nature-filled atmosphere",
            "bubble buddy": "underwater playground with soft coral reefs in pink, orange, and purple, friendly sea creatures like fish and starfish in background, gentle ocean currents creating soft movement, bright blue and yellow tones, preschool-friendly aquatic adventure with ocean life",
            "funny bunny": "playful meadow with soft grass, colorful flowers in various hues, gentle hills in background, warm earth tones of green and brown, natural outdoor elements, preschool-friendly comedic and playful natural atmosphere",
            "super metal hero": "futuristic tech playground with soft glowing elements in blue and orange, friendly robotic decorations, bright metallic colors with warm tones, high-tech but safe environment, preschool-friendly technological adventure with friendly robots",
            "piggy friend": "cozy family home interior with soft pastel walls in pink and yellow, friendly family decorations like photos and toys, warm and inviting atmosphere, pink and yellow tones, comfortable furniture, preschool-friendly family environment with homey feel",
            "blu pup": "playful home setting with creative toys scattered around, colorful art supplies like crayons and paper, soft family-friendly interior, bright and cheerful tones, creative workspace elements, preschool-friendly creative and imaginative atmosphere",
            "rescue pup crew": "adventure base with friendly rescue elements like safety equipment, soft hero-themed decorations, safe and encouraging environment, red and blue tones, rescue-themed props, preschool-friendly heroic and helpful atmosphere",
            "ocean dreamer moa": "ocean adventure setting with soft waves in blue and turquoise, friendly sea elements like shells and seaweed, gentle beach scene with sand and water, blue and turquoise tones, ocean-themed decorations, preschool-friendly oceanic and adventurous atmosphere",
            "super jump hero": "playful game world with colorful platforms in red, green, and yellow, friendly game elements like coins and power-ups, bright and energetic atmosphere, red and green tones, game-themed decorations, preschool-friendly gaming adventure with fun elements",
            "swamp buddy hero": "friendly swamp setting with soft natural elements like water and plants, cozy and warm atmosphere despite swamp theme, green and brown tones, natural swamp decorations made friendly, preschool-friendly natural environment with adventure feel",
            "boots knight pal": "medieval adventure setting with soft castle elements in brown and gray, friendly knight decorations like shields and banners, warm and brave atmosphere, brown and gold tones, chivalrous-themed props, preschool-friendly chivalrous and brave environment",
            "frost friend sid": "ice age playground with soft snow elements in white and blue, friendly prehistoric decorations like ice formations, cool but warm atmosphere, blue and white tones, prehistoric-themed but friendly elements, preschool-friendly prehistoric adventure with ice age feel",
            "adventure dora pal": "exploration setting with soft map elements visible, friendly adventure decorations like compass and backpack, warm and curious atmosphere, orange and purple tones, exploration-themed props, preschool-friendly exploration and discovery theme",
            "snowman buddy olaf-style": "winter wonderland with soft snow in white and light blue, friendly winter elements like snowflakes and icicles, warm and cozy atmosphere despite cold theme, white and blue tones, winter-themed decorations, preschool-friendly winter adventure with warm feeling",
            "spark buddy": "electric playground with soft energy elements in yellow and orange, friendly electric decorations like lightning bolts, bright and energetic atmosphere, yellow and orange tones, electric-themed props, preschool-friendly electric adventure with sparkly elements",
            "mystery pup buddy": "mystery setting with soft detective elements like magnifying glass, friendly mystery decorations, warm and curious atmosphere, purple and brown tones, detective-themed props, preschool-friendly mystery adventure with puzzle-solving feel",
            "sneaky cat tom": "playful home setting with soft furniture in gray and brown, friendly home decorations, warm and mischievous atmosphere, gray and brown tones, home-themed props, preschool-friendly home adventure with playful mischief",
            "clever mouse jerry": "cozy small space with soft miniature elements, friendly small decorations, warm and clever atmosphere, brown and beige tones, miniature-themed props, preschool-friendly miniature adventure with clever solutions",
            "jerry": "cozy small space with soft miniature elements, friendly small decorations, warm and clever atmosphere, brown and beige tones, miniature-themed props, preschool-friendly miniature adventure with clever solutions",
            "shell heroes crew": "urban adventure setting with soft city elements, friendly urban decorations, bright and team-oriented atmosphere, green and orange tones, team-themed props, preschool-friendly team adventure with cooperation feel",
        }
        
        # Get background style (use provided, or default from character, or generic)
        char_key = character_name.lower()
        if background_style:
            bg_description = background_style
        else:
            bg_description = character_backgrounds.get(char_key, "bright, cozy kids' room with warm, sunny tone — soft rug, pastel furniture, and stuffed animals, preschool-friendly cheerful atmosphere")
        
        # Debug: Print background selection
        print(f"🎨 Background selected for {character_name}: {bg_description[:100]}...")
        
        # Character-specific 3D animation descriptions (profile fotoğraftaki karakterin özelliklerini koru)
        character_3d_descriptions = {
            "koko": "The character from the profile photo, a wise storyteller, calm and gentle personality preserved, 3D animated character model, soft lighting, bedtime story atmosphere, maintaining character's original appearance and style",
            "elsa": "The character from the profile photo, a magical princess, graceful and kind personality preserved, 3D animated character model, elegant movements, gentle snow magic atmosphere, maintaining character's original appearance and style",
            "mino": "The character from the profile photo, a colorful space friend, friendly personality preserved, 3D animated character model, astronaut theme, warm and inviting, maintaining character's original appearance and style",
            "luna": "The character from the profile photo, a magical dream character, soft personality preserved, 3D animated character model, dreamy moonlit atmosphere, maintaining character's original appearance and style",
        }
        
        char_desc = character_3d_descriptions.get(character_name.lower(), "The character from the profile photo, gentle 3D animated character, child-friendly style, maintaining original appearance")
        
        # 3D animasyon için detaylı prompt (profile fotoğraftan karakter modeli oluştur)
        # Yeni scene prompt'ları zaten karakter açıklaması içeriyor, bu yüzden sadece teknik detayları ekle
        # Eğer yeni scene prompt kullanılıyorsa (wave_greeting, talking, etc.), char_desc ekleme
        # Essential scene actions (simplified set)
        is_new_scene = action in ["wave", "talking", "raise_hand", "hand_on_hip", 
                                  "lean_closer", "side_glance"]
        
        # Background and transition rules for preschool-friendly, stable backgrounds
        # CRITICAL: Her sahne, bir önceki sahneden devam etmeli ve sonraki sahneye geçiş yapmalı
        # Bu, tüm sahneleri birbirine bağlı, tutarlı bir animasyon çizgi film gibi yapar
        
        # Önceki ve sonraki sahne bilgisi için detaylı transition notları
        # CRITICAL: Bir sahnenin bitimi, diğer sahnenin başlangıcı olmalı
        # CRITICAL: Tüm sahneler aynı background'u kullanmalı - çizgi film gibi continuous story
        # Story flow: wave (greeting) → talking → raise_hand → hand_on_hip → lean_closer → side_glance → talking → wave (goodbye)
        # İlk wave background'u oluşturur, diğer tüm sahneler aynı background'u kullanır
        
        # Determine if this is the first scene (wave greeting) or last scene (wave goodbye)
        # Story flow: wave (greeting) → talking → raise_hand → hand_on_hip → lean_closer → side_glance → talking → wave (goodbye)
        # İlk wave background'u oluşturur, tüm sahneler aynı background'u kullanır
        is_first_scene = (action == "wave" and not previous_action)
        is_last_scene = (action == "wave" and previous_action is not None and (next_action is None or next_action == ""))
        is_middle_scene = previous_action is not None and not is_last_scene
        
        transition_notes = ""
        if is_first_scene:
            # İlk sahne (wave - greeting): Background'u establish et, tüm story için base oluştur
            transition_notes += (
                f"🎬 FIRST SCENE - BACKGROUND ESTABLISHMENT: "
                f"This is the opening scene of a continuous animated cartoon story. "
                f"Establish and LOCK the base background theme: {bg_description}. "
                f"This EXACT background (including all elements, colors, lighting, perspective, camera angle) will be used in ALL subsequent scenes. "
                f"Set the camera angle, lighting direction, perspective, and background elements - these are PERMANENTLY LOCKED for the entire story. "
                f"Character starts in a natural greeting pose, ready to begin the story. "
                f"🎯 END TRANSITION: End in a position ready for 'talking' scene - natural standing pose, facing forward, hands in neutral position. "
                f"Background, lighting, camera angle, and perspective must be IDENTICAL in the next scene - NO CHANGES WHATSOEVER. "
            )
        elif is_last_scene:
            # Son sahne (wave - goodbye): Aynı background ile sonlanır
            transition_notes += (
                f"🎬 LAST SCENE - STORY CONCLUSION: "
                f"This is the closing scene of the continuous animated cartoon story. "
                f"🔒 BACKGROUND LOCK: Background MUST be IDENTICAL to the first scene's background: {bg_description}. "
                f"Same camera angle, same lighting, same perspective, same background elements - EXACT MATCH. "
                f"🎯 START TRANSITION: Begin EXACTLY where {previous_action} scene ended. "
                f"Character's body position, pose, hand position, facial expression, and background must match PERFECTLY - frame by frame continuity. "
                f"Background, lighting, camera angle, and perspective must be IDENTICAL to {previous_action}'s ending frame - NO VISUAL DIFFERENCES. "
                f"End with a warm farewell wave, maintaining the EXACT same background theme established at the start. "
                f"This completes the continuous story - like watching one animated film from start to finish. "
            )
        elif is_middle_scene:
            # Orta sahneler: İlk sahnenin background'unu kullanır, aynı perspective
            frame_continuity_note = ""
            if previous_video_last_frame:
                frame_continuity_note = (
                    f"🎯 FRAME-TO-FRAME CONTINUITY: "
                    f"A reference image from the last frame of the previous scene ({previous_action}) is provided. "
                    f"START THIS VIDEO EXACTLY FROM THAT FRAME - character position, pose, hand position, facial expression, and background must be IDENTICAL. "
                    f"This ensures perfect frame-by-frame continuity - the last frame of {previous_action} is the first frame of this scene. "
                )
            
            transition_notes += (
                f"🎬 MIDDLE SCENE - CONTINUOUS STORY: "
                f"This is a middle scene in a continuous animated cartoon story. "
                f"🔒 BACKGROUND LOCK: Background MUST be IDENTICAL to the first scene's background: {bg_description}. "
                f"Same camera angle, same lighting direction, same perspective, same background elements - EXACT MATCH to first scene. "
                f"🎯 START TRANSITION: Begin EXACTLY where {previous_action} scene ended. "
                f"{frame_continuity_note}"
                f"Character's body position, pose, hand position, facial expression, and background must match PERFECTLY - frame by frame continuity. "
                f"Background, lighting, camera angle, and perspective must be IDENTICAL to {previous_action}'s ending frame - NO VISUAL DIFFERENCES. "
                f"This is a CONTINUOUS animation - no jump cuts, no position changes, no background changes, seamless flow like one continuous film. "
            )
            if next_action:
                transition_notes += (
                    f"🎯 END TRANSITION: End in a position that matches {next_action} scene's starting position. "
                    f"Character's final pose, hand position, body orientation, and facial expression must prepare for {next_action}. "
                    f"Background remains IDENTICAL - same perspective, same lighting, same camera angle - NO CHANGES. "
                    f"The ending frame should be a PERFECT starting point for {next_action} - seamless loop connection, like one continuous animation. "
                )
        
        # Background transition mantığı: Daha detaylı ve tutarlı
        # CRITICAL: Character position transitions are as important as background transitions
        character_transition_rules = ""
        if previous_action or next_action:
            character_transition_rules = (
                "CHARACTER POSITION TRANSITION: "
                "Character's body position, pose, and orientation must transition smoothly between scenes. "
                "If transitioning FROM another scene, start in the exact ending pose of that scene. "
                "If transitioning TO another scene, end in a pose that naturally leads to that scene's start. "
                "Hand positions, body orientation, and facial direction must be consistent. "
                "No sudden position jumps - smooth, natural movement only. "
            )
        
        # Background transition logic - KISA VE ÖZ (prompt limiti için)
        if is_first_scene:
            # İlk sahne: Background'u establish et
            background_transition_logic = (
                f"BACKGROUND: {bg_description}. "
                f"FIRST SCENE - Establish and LOCK this background for entire story. "
                f"Same camera angle, lighting, perspective in ALL subsequent scenes. "
                f"NO background changes, NO camera movement. "
            )
        elif is_middle_scene:
            # Orta sahneler: İlk sahnenin background'unu kullan
            background_transition_logic = (
                f"BACKGROUND: {bg_description}. "
                f"MIDDLE SCENE - Use EXACT SAME background as first scene. "
                f"Same camera angle, lighting, perspective - EXACT MATCH. "
                f"NO background changes, NO camera movement. "
            )
        else:
            # Son sahne: Aynı background ile sonlan
            background_transition_logic = (
                f"BACKGROUND: {bg_description}. "
                f"LAST SCENE - Use EXACT SAME background as first scene. "
                f"Same camera angle, lighting, perspective - EXACT MATCH. "
                f"NO background changes, NO camera movement. "
            )
        
        # Transition notes'u background'a ekle (kısa)
        if transition_notes:
            # Sadece kritik bilgileri ekle
            if "FIRST SCENE" in transition_notes:
                background_transition_logic += "Establish background theme now. "
            if "START TRANSITION" in transition_notes:
                background_transition_logic += "Start from previous scene's ending frame. "
            if "END TRANSITION" in transition_notes:
                background_transition_logic += "End ready for next scene. "
        
        background_rules = background_transition_logic
        
        # Teknik kurallar (tüm sahneler için geçerli) - Kısa ve öz (2500 karakter limiti)
        technical_rules = (
            "Pixar 3D, smooth motion, 9:16 portrait, 10s duration. "
            "Warm lighting, static mid-shot. "
            "Character matches input image exactly. "
            "Seamless loop, smooth scene transitions. "
            "NO AUDIO. "
        ) + background_rules
        
        if is_new_scene:
            # Yeni scene prompt'ları zaten tam açıklama içeriyor, teknik kuralları ekle
            full_prompt = f"{motion_prompt} {technical_rules}"
        else:
            # Legacy prompt'lar için char_desc + motion_prompt + teknik kurallar (kısa)
            full_prompt = f"{char_desc}. {motion_prompt}. {technical_rules} 3D animation, EXACT character match, 9:16 portrait."
        
        # Prompt uzunluğu kontrolü (2500 karakter limiti)
        prompt_length = len(full_prompt)
        if prompt_length > 2500:
            print(f"⚠️  WARNING: Prompt too long ({prompt_length} chars, limit: 2500). Truncating...")
            # Background rules'ı KORU, motion_prompt'u kısalt
            # Background kritik, bu yüzden technical_rules'ı koruyoruz
            motion_prompt_short = motion_prompt[:1800] if len(motion_prompt) > 1800 else motion_prompt
            full_prompt = f"{motion_prompt_short} {technical_rules}"
            if len(full_prompt) > 2500:
                # Son çare: technical_rules'ı da kısalt ama background'u koru
                bg_part = background_rules[:300]  # Background'u koru
                tech_part = "Pixar 3D, smooth motion, 9:16 portrait, 12s duration. Warm lighting, static mid-shot. Character matches input image exactly. Seamless loop. NO AUDIO. "
                full_prompt = f"{motion_prompt_short} {tech_part} {bg_part}"
        
        print(f"🎬 Generating {character_name}_{action}.mp4 from profile image")
        print(f"📝 3D Animation Prompt: {full_prompt[:150]}... (length: {len(full_prompt)} chars)")
        print(f"🎥 Model: {model_path} (image-to-video)")
        
        # Set FAL API key
        os.environ['FAL_KEY'] = fal_api_key
        
        # FAL.ai stable-video-diffusion: Image'i upload et
        # FAL.ai file upload için: File'ı file object olarak gönder veya URL kullan
        # En güvenilir yöntem: Image'i base64 encode edip data URL olarak gönder
        
        import base64
        with open(profile_image_path, 'rb') as f:
            image_bytes = f.read()
        
        # FAL.ai için image'i iki format ile hazırla:
        # 1. Base64 data URL (bazı modeller için)
        # 2. File upload (Kling gibi modeller için gerekebilir)
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        image_ext = Path(profile_image_path).suffix[1:].lower() if Path(profile_image_path).suffix else "png"
        
        # Data URL format: data:image/{mime_type};base64,{base64_string}
        # NOT: jpg -> jpeg, diğer formatlar için doğru MIME type kullan
        mime_type_map = {
            "jpg": "jpeg",
            "jpeg": "jpeg",
            "png": "png",
            "webp": "webp",
            "gif": "gif"
        }
        mime_type = mime_type_map.get(image_ext, "jpeg")
        image_data_url = f"data:image/{mime_type};base64,{image_base64}"
        
        # NOT: İkinci görsel referansı kullanılmıyor (maliyetli) - sadece tek görsel kullanılıyor
        
        # Kling modeli minimum 300x300 piksel gerektiriyor
        # Image boyutlarını kontrol et ve gerekirse resize et
        try:
            with Image.open(profile_image_path) as img:
                width, height = img.size
                min_size = 300
                
                if width < min_size or height < min_size:
                    print(f"⚠️ Image dimensions ({width}x{height}) are too small. Minimum: {min_size}x{min_size}")
                    print(f"   Resizing image to meet minimum requirements...")
                    
                    # Aspect ratio'yu koruyarak resize et
                    # En küçük boyutu min_size yap, diğerini orantılı olarak büyüt
                    if width < height:
                        new_width = min_size
                        new_height = int(height * (min_size / width))
                    else:
                        new_height = min_size
                        new_width = int(width * (min_size / height))
                    
                    # Resize işlemi
                    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Geçici dosyaya kaydet
                    temp_path = Path(profile_image_path).parent / f"temp_{Path(profile_image_path).name}"
                    img_resized.save(temp_path, quality=95)
                    
                    # Orijinal path'i güncelle (geçici dosyayı kullan)
                    profile_image_path = str(temp_path)
                    
                    # Image bytes'i yeniden oku (resize edilmiş dosyadan)
                    with open(profile_image_path, 'rb') as f:
                        image_bytes = f.read()
                    
                    # Base64'i yeniden encode et
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    
                    print(f"✅ Image resized to {new_width}x{new_height}")
                else:
                    print(f"✅ Image dimensions ({width}x{height}) meet minimum requirements")
        except Exception as img_error:
            print(f"⚠️ Could not check/resize image: {img_error}")
            print(f"   Proceeding with original image...")
        
        print(f"📤 Preparing profile image ({len(image_bytes)} bytes) for FAL.ai...")
        
        # Generate video from image using FAL.ai
        # Model parametreleri model'e göre değişebilir
        # 404 hatası için alternatif modelleri dene
        
        submit_result = None
        last_error = None
        successful_model = None
        
        for model_candidate in model_candidates:
            try:
                current_model = model_candidate
                print(f"🔄 Trying model: {current_model}")
                
                # Kling modeli için file upload gerekmiyor - SDK otomatik handle eder
                # FAL.ai SDK, file path'i direkt kullanarak otomatik upload eder
                
                # Model'e göre parametreler hazırla (kalite ve maliyet dengesi)
                # NOT: İki görsel desteği kaldırıldı (maliyetli) - sadece tek görsel kullanılıyor
                if "veo3.1" in current_model.lower():
                    # Google Veo 3.1: En yeni teknoloji, yüksek kalite, mükemmel karakter tutarlılığı
                    # NOT: Ses üretimine gerek yok (audio parametresi yoksa otomatik sessiz)
                    arguments = {
                        "image_url": image_data_url,
                        "prompt": full_prompt,  # Teknik kuralları içeren tam prompt
                        # Veo 3.1 parametreleri (eğer destekleniyorsa)
                        # "aspect_ratio": "9:16",  # Portrait for mobile
                        # "duration": 8,  # 6-12 seconds
                    }
                elif "kling" in current_model.lower():
                    # Kling Video 2.5 Turbo Pro: ÖNCELİKLİ MODEL! Cinematic, en iyi motion, yüksek kalite
                    # ✅ 9:16 aspect ratio desteği var (telefon/mock call için ideal)
                    # ✅ Sinematik motion, karakter tutarlılığı için güçlü prompt kullanılıyor
                    # NOT: Kling base64 data URL desteklemiyor, HTTPS URL gerekiyor
                    # FAL.ai SDK'da file'ı önce upload edip URL'ini almalıyız
                    # `fal_client.upload_file()` kullanarak file'ı upload edip URL'ini alıyoruz
                    try:
                        # FAL.ai SDK'da file upload
                        # fal_client.upload_file() fonksiyonu file path'i alıp HTTPS URL döner
                        image_upload_url = fal_client.upload_file(profile_image_path)
                        print(f"✅ File uploaded to FAL.ai CDN: {image_upload_url[:50]}...")
                        
                        # FRAME-TO-FRAME CONTINUITY: Eğer önceki videonun son frame'i varsa, onu da upload et
                        reference_image_url = None
                        if previous_video_last_frame and Path(previous_video_last_frame).exists():
                            try:
                                reference_image_url = fal_client.upload_file(previous_video_last_frame)
                                print(f"✅ Reference frame uploaded to FAL.ai CDN: {reference_image_url[:50]}...")
                                print(f"   🎯 Using last frame from {previous_action} as starting reference")
                            except Exception as ref_upload_error:
                                print(f"⚠️ Failed to upload reference frame: {ref_upload_error}")
                                # Continue without reference frame
                    except (AttributeError, TypeError) as upload_error:
                        # fal_client.upload_file() mevcut değilse veya farklı bir API kullanıyorsa
                        # Geçici olarak Kling'i atla, diğer modelleri dene
                        print(f"⚠️ Kling requires file upload, but upload mechanism failed: {upload_error}. Skipping to next model...")
                        raise Exception("Kling requires file upload, skipping to next model")
                    
                    arguments = {
                        "image_url": image_upload_url,  # Upload edilmiş HTTPS URL
                        "prompt": full_prompt,  # Teknik kuralları içeren tam prompt (karakter tutarlılığı vurgulu)
                        # Kling parametreleri (eğer destekleniyorsa)
                        # "aspect_ratio": "9:16",  # Portrait for mobile (model destekliyorsa)
                        # "duration": 8,  # 6-12 seconds
                        # Ses üretimine gerek yok
                    }
                    
                    # Eğer reference frame varsa, bazı modeller image_urls array destekleyebilir
                    # Şimdilik prompt'ta belirtiyoruz, ileride model desteği kontrol edilebilir
                    if reference_image_url:
                        # Bazı modeller reference_image_url veya image_urls parametresi destekleyebilir
                        # Şimdilik prompt'ta belirtiyoruz
                        print(f"   🎯 Reference frame available - prompt includes frame-to-frame continuity instructions")
                    
                    print(f"✅ Using Kling 2.5 Turbo Pro - optimized for 9:16 portrait and character consistency")
                    print(f"   Using uploaded URL: {image_upload_url[:50] if image_upload_url else 'N/A'}...")
                elif "sora-2" in current_model.lower():
                    # OpenAI Sora 2: Yüksek kalite, mükemmel karakter tutarlılığı
                    # NOT: Sora 2'de audio parametresi varsa kapat
                    arguments = {
                        "image_url": image_data_url,
                        "prompt": full_prompt,  # Teknik kuralları içeren tam prompt
                        # Sora 2 parametreleri (eğer destekleniyorsa)
                        # "aspect_ratio": "9:16",  # Portrait for mobile
                        # "duration": 8,  # 6-12 seconds
                    }
                    # Audio parametresi varsa kapat (ses ayrı oluşturuluyor)
                    # Sora 2'de audio parametresi genellikle yok, ama kontrol ediyoruz
                elif "wan/v2.2" in current_model.lower() or "wan-22" in current_model.lower():
                    # Wan 2.2: Açık kaynak, fallback
                    arguments = {
                        "image_url": image_data_url,
                        "prompt": full_prompt,
                        "resolution": "720p",  # Mobile için yeterli
                        "aspect_ratio": "9:16",  # Portrait for mobile/phone
                        "duration": 10,  # 10 saniye (daha uzun sahneler için)
                        # Ses üretimine gerek yok (ses ayrı oluşturuluyor)
                    }
                elif "wan-i2v" in current_model.lower() or ("wan" in current_model.lower() and "i2v" in current_model.lower()):
                    # Wan 2.1: Son çare fallback
                    arguments = {
                        "image_url": image_data_url,
                        "prompt": full_prompt,
                        "resolution": "720p",  # Mobile için yeterli
                        "aspect_ratio": "9:16",  # Portrait for mobile/phone (mock call)
                        "duration": 10,  # 10 saniye (daha uzun sahneler için) (ideal çocuk ilgisi)
                        # Ses üretimine gerek yok (ses ayrı oluşturuluyor)
                    }
                elif "minimax" in current_model.lower():
                    # Minimax Hailuo-02-Fast: EN UCUZ model (~$0.017/saniye)
                    # CRITICAL: Minimax base64 data URL'i kabul etmiyor!
                    # FAL.ai SDK file upload kullan: image parametresi ile direkt file path gönder
                    # FAL.ai SDK otomatik olarak file'ı upload eder
                    arguments = {
                        "image": profile_image_path,  # File path - SDK otomatik upload eder
                        "prompt": full_prompt,
                    }
                    # duration parametresi desteklenmiyor, image_url base64 desteklenmiyor
                elif "ovi" in current_model.lower():
                    # Ovi: Fallback
                    arguments = {
                        "image_url": image_data_url,
                        "prompt": full_prompt,
                        "duration": 12,  # 12 saniye (çocuklar için daha uzun, engaging sahneler)
                        "resolution": "720p",  # Mobile için yeterli
                        "aspect_ratio": "9:16",  # Portrait for mobile/phone
                        # Ses üretimine gerek yok (ses ayrı oluşturuluyor)
                    }
                elif "svd" in current_model.lower():
                    # SVD (Stable Video Diffusion) parametreleri
                    arguments = {
                        "image_url": image_data_url,
                        "motion_bucket_id": 127,  # Motion intensity (1-255)
                        "fps": 24,  # High frame rate için
                        "video_length": 12,  # 12 saniye (çocuklar için daha uzun, engaging sahneler)
                        # Ses üretimine gerek yok (ses ayrı oluşturuluyor)
                    }
                else:
                    # Default parameters (fallback)
                    arguments = {
                        "image_url": image_data_url,
                        "prompt": full_prompt,
                        "duration": 12,  # 12 saniye (çocuklar için daha uzun, engaging sahneler)
                        "resolution": "720p",  # Mobile için yeterli
                        "aspect_ratio": "9:16",  # Portrait for mobile/phone (mock call)
                        # Ses üretimine gerek yok (ses ayrı oluşturuluyor)
                    }
                
                submit_result = fal_client.submit(
                    current_model,
                    arguments=arguments
                )
                
                # Başarılı ise döngüden çık
                successful_model = current_model
                print(f"✅ Model {current_model} accepted")
                break
                
            except Exception as e:
                last_error = e
                error_str = str(e)
                print(f"⚠️ Model {current_model} failed: {error_str[:100]}")
                if "404" in error_str or "Not Found" in error_str or "does not exist" in error_str.lower():
                    # 404 hatası ise bir sonraki modeli dene
                    submit_result = None
                    continue
                elif "422" in error_str or "Unprocessable Entity" in error_str:
                    # 422 hatası: Parametreler yanlış, bir sonraki modeli dene
                    print(f"⚠️ Model {current_model} rejected parameters (422). Trying next model...")
                    submit_result = None
                    continue
                else:
                    # Başka bir hata ise tekrar dene veya yukarı fırlat
                    print(f"❌ Unexpected error with {current_model}: {e}")
                    # 404/422 değilse devam et (bağlantı hatası vs olabilir)
                    submit_result = None
                    continue
        
        if not submit_result:
            print(f"❌ All models failed. Last error: {last_error}")
            print(f"   Tried models: {', '.join(model_candidates)}")
            return None
        
        print(f"✅ Using successful model: {successful_model}")
        
        # Wait for result
        # CRITICAL: get() sırasında 422 hatası alınabilir (parametreler işlenemiyor)
        # Bu durumda bir sonraki modele geçmeliyiz
        try:
            result = submit_result.get()
        except Exception as get_error:
            error_str = str(get_error)
            if "422" in error_str or "Unprocessable Entity" in error_str:
                print(f"⚠️ Model {successful_model} rejected during get() (422). Trying next model...")
                # Bu model çalışmadı, bir sonraki modele geç
                # Ama zaten submit başarılı oldu, bu yüzden döngüyü yeniden başlatamayız
                # En iyi çözüm: Minimax'ı listeden çıkar veya atla ve devam et
                # Şimdilik None döndür, üst seviyede retry yapılabilir
                return None
            else:
                # Diğer hatalar için yukarı fırlat
                raise
        
        if not result:
            print(f"❌ FAL.ai returned empty result for {character_name}_{action}")
            return None
        
        # Extract video URL from result
        # MP4 döndüren modeller (Minimax, Wan-2.1, Ovi) genellikle şu yapıyı kullanır:
        # - {"video": {"url": "..."}}  (en yaygın)
        # - {"video": "..."}  (direkt string)
        # - {"url": "..."}  (direkt URL)
        # - {"output": {"url": "..."}}  (bazı modeller)
        
        video_url = None
        if isinstance(result, dict):
            # Try different possible response structures
            # 1. Check for "video" key (most common)
            if "video" in result:
                if isinstance(result["video"], dict):
                    video_url = result["video"].get("url")
                elif isinstance(result["video"], str):
                    video_url = result["video"]
            # 2. Check for "image" key (SVD model sometimes uses this)
            # NOTE: "image" key SVD'de bazen GIF döndürebilir, ama URL kontrolü yapıyoruz
            elif "image" in result and "video" not in result:
                image_value = result["image"]
                print(f"🔍 Found 'image' key in response (no 'video' key). Type: {type(image_value)}")
                print(f"⚠️ Warning: 'image' key might contain GIF/thumbnail, checking URL...")
                
                if isinstance(image_value, dict):
                    # Try video-specific keys first
                    for url_key in ["video_url", "video", "mp4_url", "content_url"]:
                        if url_key in image_value:
                            potential_url = image_value[url_key]
                            # CRITICAL: Reject GIF URLs BEFORE download (save cost)
                            url_lower = potential_url.lower()
                            if (".gif" in url_lower or 
                                url_lower.endswith(".gif") or
                                "/gif" in url_lower.split("?")[0]):
                                print(f"❌ Rejecting {url_key} - it's a GIF URL (saving cost): {potential_url[:80]}")
                                print(f"   SVD returned GIF instead of video. Trying next model...")
                                # Return None to trigger next model fallback
                                return None
                            video_url = potential_url
                            print(f"✅ Found video URL in image.{url_key}: {video_url[:50]}...")
                            break
                    
                    # If no video-specific URL found, try generic URL keys
                    if not video_url:
                        for url_key in ["url", "href", "src"]:
                            if url_key in image_value:
                                potential_url = image_value[url_key]
                                # CRITICAL: Reject GIF URLs BEFORE download
                                url_lower = potential_url.lower()
                                if (".gif" in url_lower or 
                                    url_lower.endswith(".gif") or
                                    "/gif" in url_lower.split("?")[0]):
                                    print(f"❌ Rejecting {url_key} - it's a GIF URL (saving cost): {potential_url[:80]}")
                                    print(f"   Trying next model to avoid unnecessary cost...")
                                    return None
                                video_url = potential_url
                                print(f"✅ Found URL in image.{url_key}: {video_url[:50]}...")
                                break
                    
                    # If still no URL, check all keys
                    if not video_url:
                        for key, value in image_value.items():
                            if isinstance(value, str) and ("http" in value or "fal.media" in value):
                                url_lower = value.lower()
                                if (".gif" in url_lower or url_lower.endswith(".gif")):
                                    print(f"❌ Skipping {key} - it's a GIF URL: {value[:80]}")
                                    continue
                                video_url = value
                                print(f"✅ Found URL-like value in image.{key}: {value[:50]}...")
                                break
                elif isinstance(image_value, str):
                    # Image is directly a URL string - check if it's a GIF
                    url_lower = image_value.lower()
                    if (".gif" in url_lower or url_lower.endswith(".gif")):
                        print(f"❌ Rejecting image string - it's a GIF URL (saving cost): {image_value[:80]}")
                        return None
                    video_url = image_value
                    print(f"✅ Image is a direct URL string: {video_url[:50]}...")
            
            # 3. Check for direct "url" key (only if video/image not found yet)
            if not video_url and "url" in result:
                potential_url = result["url"]
                # CRITICAL: Reject GIF URLs
                if isinstance(potential_url, str):
                    url_lower = potential_url.lower()
                    if (".gif" in url_lower or url_lower.endswith(".gif")):
                        print(f"❌ Rejecting direct 'url' - it's a GIF: {potential_url[:80]}")
                        return None
                video_url = potential_url
            # 4. Check for "output" key
            elif "output" in result:
                if isinstance(result["output"], dict):
                    video_url = result["output"].get("url")
                elif isinstance(result["output"], str):
                    video_url = result["output"]
        
        if not video_url:
            print(f"❌ Could not extract video URL from FAL.ai response")
            print(f"   Result keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
            print(f"   Result structure: {str(result)[:200]}")
            return None
        
        # CRITICAL: Final validation - reject GIF URLs
        if isinstance(video_url, str):
            url_lower = video_url.lower()
            # Check if URL ends with .gif or contains .gif in path
            if (url_lower.endswith(".gif") or 
                ".gif?" in url_lower or 
                "/gif" in url_lower.split("?")[0] or
                url_lower.count(".gif") > 0):
                print(f"❌ CRITICAL: Video URL is a GIF: {video_url[:100]}")
                print(f"   Model returned GIF instead of video. Rejecting and trying next model...")
                return None
        
        print(f"✅ Video generated: {video_url}")
        
        # Download video with content-type validation
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(video_url)
            if response.status_code != 200:
                print(f"❌ Failed to download video: {response.status_code}")
                return None
            
            # Check content type to ensure it's actually a video
            content_type = response.headers.get("content-type", "").lower()
            print(f"📦 Content-Type: {content_type}")
            
            # Validate content type - should be video, not image/GIF
            if "image" in content_type or "gif" in content_type:
                print(f"⚠️ Warning: URL returned image/GIF ({content_type}) instead of video")
                print(f"   URL: {video_url}")
                print(f"   This might be a thumbnail or preview. Trying to find actual video URL...")
                # If it's an image, we might need to look for a video URL in the response
                # For now, reject it and try next model
                return None
            
            video_data = response.content
            
            # CRITICAL: Validate video file format by checking magic bytes
            # Prevent saving GIF files as MP4
            if len(video_data) >= 6:
                # Check for GIF signature (should REJECT immediately)
                if video_data[0:6] in [b'GIF89a', b'GIF87a']:
                    print(f"❌ ERROR: Downloaded file is a GIF, not a video!")
                    print(f"   URL returned GIF instead of video. This is invalid.")
                    print(f"   Rejecting GIF and trying next model...")
                    return None
                
                # Check for valid video formats
                is_valid_video = False
                if len(video_data) >= 12:
                    # MP4 signature: bytes 4-7 should be 'ftyp'
                    if video_data[4:8] == b'ftyp':
                        is_valid_video = True
                        print(f"✅ Valid MP4 format detected (ftyp signature)")
                    # WebM signature: starts with 0x1A 0x45 0xDF 0xA3
                    elif video_data[0:4] == b'\x1a\x45\xdf\xa3':
                        is_valid_video = True
                        print(f"✅ Valid WebM format detected")
                    # MOV signature: similar to MP4
                    elif len(video_data) >= 8 and video_data[4:8] in [b'qt  ', b'moov', b'mdat']:
                        is_valid_video = True
                        print(f"✅ Valid MOV format detected")
                
                if not is_valid_video and len(video_data) >= 12:
                    print(f"⚠️ Warning: Could not validate video format. First bytes: {video_data[0:12].hex()}")
                    print(f"   Continuing anyway, but video might not play correctly")
            
            # Validate video file size (should be > 10KB for a 5-second video)
            if len(video_data) < 10240:  # 10KB
                print(f"⚠️ Warning: Video file is too small ({len(video_data)} bytes), might be invalid")
                # Continue anyway, but log warning
            
            print(f"📥 Downloaded video: {len(video_data)} bytes ({len(video_data)/1024:.1f} KB)")
            
        # Save video to output directory
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{character_name}_{action}.mp4"
            
            with open(output_path, 'wb') as f:
                f.write(video_data)
            
            # Final validation: double-check saved file is not GIF
            if output_path.exists() and output_path.stat().st_size > 0:
                saved_size = output_path.stat().st_size
                
                # Re-validate: check file is actually a video, not GIF
                with open(output_path, 'rb') as f:
                    first_bytes = f.read(12)
                    if first_bytes[0:6] in [b'GIF89a', b'GIF87a']:
                        print(f"❌ CRITICAL: Saved file is a GIF, not a video! Deleting corrupted file...")
                        output_path.unlink()
                        return None
                
                print(f"💾 Video saved: {output_path} ({saved_size} bytes, {saved_size/1024:.1f} KB)")
                return str(output_path)
            else:
                print(f"❌ Failed to save video file")
                return None
        else:
            # Return URL if no output dir specified
            return video_url
            
    except Exception as e:
        print(f"❌ Failed to generate video for {character_name}_{action}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_all_character_videos(
    character_name: str,
    profile_image_path: Optional[str] = None,
    reference_image_2_path: Optional[str] = None,
    output_base_dir: Path = None,
    background_style: Optional[str] = None
) -> dict[str, Optional[str]]:
    """
    Generate all 4 videos (idle, speak, listen, wave) for a character from profile image.
    Profile fotoğrafından 4 farklı 3D animasyonlu MP4 üretir.
    
    Args:
        character_name: Character name
        profile_image_path: Path to first profile image
        reference_image_2_path: Optional second reference image for better character consistency
        output_base_dir: Output directory
    
    Returns:
        Dict mapping action -> video_path
    """
    if output_base_dir is None:
        output_base_dir = Path(__file__).parent.parent.parent / "mino" / "Assets" / "characters" / character_name
    
    # Profile image path'i otomatik bul (eğer verilmemişse)
    if not profile_image_path:
        project_root = Path(__file__).parent.parent.parent
        char_dir = project_root / "mino" / "Assets" / "characters" / character_name.lower()
        
        for ext in ["png", "jpg", "jpeg"]:
            potential_path = char_dir / f"{character_name.lower()}_profile.{ext}"
            if potential_path.exists():
                profile_image_path = str(potential_path)
                break
    
    if not profile_image_path:
        print(f"❌ Profile image not found for {character_name}")
        print(f"   Expected: {char_dir}/{character_name.lower()}_profile.png/jpg")
        return {}
    
    # Default: generate legacy actions only (for backward compatibility)
    # Use generate_character_video directly with specific actions for new scenes
    actions = ["idle", "speak", "listen", "wave"]
    results = {}
    
    for i, action in enumerate(actions):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(actions)}] Generating {character_name}_{action}.mp4 from profile image...")
        print(f"{'='*60}")
        
        # Determine previous and next actions for smooth transitions
        previous_action = actions[i - 1] if i > 0 else None
        next_action = actions[i + 1] if i < len(actions) - 1 else None
        
        if previous_action:
            print(f"📹 Previous scene: {previous_action} (this video will start from where it ended)")
        if next_action:
            print(f"📹 Next scene: {next_action} (this video will transition to it)")
        
        video_path = await generate_character_video(
            character_name=character_name,
            action=action,
            profile_image_path=profile_image_path,
            reference_image_2_path=reference_image_2_path,
            output_dir=output_base_dir,
            background_style=background_style,
            previous_action=previous_action,
            next_action=next_action
        )
        
        results[action] = video_path
        
        if video_path:
            print(f"✅ {action} video generated successfully")
        else:
            print(f"❌ Failed to generate {action} video")
    
    return results

