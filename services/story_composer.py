import os
import re
import json
from pathlib import Path
from typing import Dict

# Import centralized topic mapping from utils
# Use relative import for backend package structure
try:
    from utils.topic_mapping import map_topic, get_topic_candidates
except ImportError:
    # Fallback for direct script execution
    import sys
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend_dir.parent))
    from backend.utils.topic_mapping import map_topic, get_topic_candidates


def to_character_slug(name: str) -> str:
    n = (name or "").strip().lower()
    direct = {
        "mino": "mino",
        "luna": "luna",
        "tiko": "tiko",
        "bubu": "bubu",
        "sunny": "sunny",
        "koko": "koko",
        "tom": "tom",
        "bunny": "bunny",
        "elsa": "elsa",
        "jerry": "jerry",
        "ninja turtles": "ninjaturtles",
        "tweety": "tweety",
        "spiderman": "spiderman",
        "winnie": "winnie",
        "minion": "minion",
        "spongebob": "spongebob",
    }
    if n in direct:
        return direct[n]
    aliases = {
        "elisa the ice fairy": "elsa",
        "sneaky cat tom": "tom",
        "clever mouse jerry": "jerry",
        "shell heroes crew": "ninjaturtles",
        "spider fighter": "spiderman",
        # Derived names → target slugs (matching CharacterSelectionView originSlug)
        "yellow buddy": "minion",
        "chirpy birdie": "tweety",
        "bubble buddy": "spongebob",
        # Also handle space-removed versions (for backward compatibility)
        "yellowbuddy": "minion",
        "chirpybirdie": "tweety",
        "bubblebuddy": "spongebob",
    }
    return aliases.get(n, re.sub(r"\s+", "", n))


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def content_story_path(lang: str, slug: str, topic: str) -> Path:
    project_root = get_project_root()
    topic_slug = topic.lower().replace(" ", "_")
    # Production path: /home/app/app/storage/content/... (project_root / "storage")
    # Development path: backend/storage/content/... (project_root / "backend" / "storage")
    # Check both paths and return the one that exists
    prod_path = project_root / "storage" / "content" / lang / "stories" / slug / f"{topic_slug}.json"
    dev_path = project_root / "backend" / "storage" / "content" / lang / "stories" / slug / f"{topic_slug}.json"
    
    # CRITICAL: Check if production storage directory exists first
    # Production server has: /home/app/app/storage/... (project_root = /home/app/app/)
    # Development has: backend/storage/... (project_root = /path/to/project/)
    if (project_root / "storage").exists():
        # Production path structure exists
        return prod_path
    elif (project_root / "backend" / "storage").exists():
        # Development path structure exists
        return dev_path
    else:
        # Default to dev_path for backward compatibility
        return dev_path


def analyze_text_for_video_key(scene_type: str, text: str, lang: str = "en") -> str:
    """
    Analyze text content to select most appropriate videoKey based on scene type AND text content.
    Best Practice: More nuanced videoKey selection for natural animations.
    
    Args:
        scene_type: Scene type (opening, speak, question, etc.)
        text: Scene text content
        lang: Language code (for language-specific keyword detection)
    
    Returns:
        Appropriate videoKey based on content analysis
    """
    text_lower = text.lower()
    
    # Language-specific keywords
    if lang.startswith("tr"):
        question_words = ["?", "soru", "ne", "nasıl", "neden", "hangi", "kim", "nerede", "ne zaman"]
        teaching_words = ["öğren", "öğret", "açıkla", "göster", "bak", "anlat", "öğrenelim"]
        encouragement_words = ["harika", "mükemmel", "bravo", "aferin", "güzel", "süper", "çok iyi"]
        inviting_words = ["birlikte", "hadi", "gel", "yapalım", "deneyelim"]
        thinking_words = ["düşün", "hayal", "ne dersin", "sence"]
    elif lang.startswith("de"):
        question_words = ["?", "frage", "was", "wie", "warum", "welche", "wer", "wo", "wann"]
        teaching_words = ["lernen", "lehren", "erklären", "zeigen", "schau", "erzählen"]
        encouragement_words = ["großartig", "wunderbar", "bravo", "gut gemacht", "schön", "super"]
        inviting_words = ["zusammen", "komm", "lass uns", "versuchen"]
        thinking_words = ["denken", "vorstellen", "was denkst du"]
    elif lang.startswith("es"):
        question_words = ["?", "pregunta", "qué", "cómo", "por qué", "cuál", "quién", "dónde", "cuándo"]
        teaching_words = ["aprender", "enseñar", "explicar", "mostrar", "mira", "contar"]
        encouragement_words = ["genial", "maravilloso", "bravo", "bien hecho", "hermoso", "súper"]
        inviting_words = ["juntos", "vamos", "ven", "intentemos"]
        thinking_words = ["pensar", "imaginar", "qué piensas"]
    elif lang.startswith("fr"):
        question_words = ["?", "question", "quoi", "comment", "pourquoi", "quel", "qui", "où", "quand"]
        teaching_words = ["apprendre", "enseigner", "expliquer", "montrer", "regarde", "raconter"]
        encouragement_words = ["génial", "merveilleux", "bravo", "bien fait", "beau", "super"]
        inviting_words = ["ensemble", "viens", "allons", "essayons"]
        thinking_words = ["penser", "imaginer", "que penses-tu"]
    else:  # English (default)
        question_words = ["?", "question", "what", "how", "why", "which", "who", "where", "when"]
        teaching_words = ["learn", "teach", "explain", "show", "look", "tell", "let's learn"]
        encouragement_words = ["great", "wonderful", "bravo", "well done", "beautiful", "super", "good job"]
        inviting_words = ["together", "come", "let's", "let us", "try"]
        thinking_words = ["think", "imagine", "what do you think"]
    
    # Scene type-based defaults
    defaults = {
        "opening": "wave",
        "closure": "wave",
        "instruction": "hand_on_hip",
        "encouragement": "raise_hand",
        "question": "lean_closer",
        "speak": "talking",
        "followup": "side_glance",
        "listen": "lean_closer",
        "narration": "talking",
        "closing": "wave"
    }
    
    # Text content analysis for more nuanced selection
    if scene_type == "speak" or scene_type == "narration":
        # Check for question words in text (even in speak scenes)
        if any(word in text_lower for word in question_words):
            return "lean_closer"  # Curious question pose
        
        # Check for teaching/explaining keywords
        if any(word in text_lower for word in teaching_words):
            return "hand_on_hip"  # Teaching pose
        
        # Check for encouragement keywords
        if any(word in text_lower for word in encouragement_words):
            return "raise_hand"  # Encouraging gesture
        
        # Check for inviting keywords
        if any(word in text_lower for word in inviting_words):
            return "raise_hand"  # Inviting gesture
        
        # Default to talking
        return "talking"
    
    elif scene_type == "question":
        # Questions can vary based on content
        if any(word in text_lower for word in thinking_words):
            return "side_glance"  # Playful thinking pose
        return "lean_closer"  # Default curious pose
    
    elif scene_type == "instruction":
        # Instructions can be more expressive
        if any(word in text_lower for word in inviting_words):
            return "raise_hand"  # Inviting gesture
        return "hand_on_hip"  # Default teaching pose
    
    elif scene_type == "followup":
        # Followup can be more engaging
        if any(word in text_lower for word in question_words):
            return "lean_closer"  # Curious followup
        return "side_glance"  # Default playful glance
    
    # Return default for scene type
    return defaults.get(scene_type, "talking")


def content_prompt_path(lang: str, slug: str, topic: str) -> Path:
    """Get path to prompt JSON file in storage/content/{lang}/prompts/{character}/{topic}.json
    
    Production path: /home/app/app/storage/content/... (project_root / "storage")
    Development path: backend/storage/content/... (project_root / "backend" / "storage")
    """
    project_root = get_project_root()
    topic_slug = topic.lower().replace(" ", "_")
    # Production path: /home/app/app/storage/content/... (project_root / "storage")
    prod_path = project_root / "storage" / "content" / lang / "prompts" / slug / f"{topic_slug}.json"
    # Development path: backend/storage/content/... (project_root / "backend" / "storage")
    dev_path = project_root / "backend" / "storage" / "content" / lang / "prompts" / slug / f"{topic_slug}.json"
    
    # CRITICAL: Check if production storage directory exists first
    if (project_root / "storage").exists():
        return prod_path
    elif (project_root / "backend" / "storage").exists():
        return dev_path
    else:
        # Default to dev_path for backward compatibility
        return dev_path


async def generate_story_with_openai(character: str, topic: str, lang: str, duration_minutes: int | None = None) -> Dict:
    """Generate a story JSON using OpenAI (primary) or minimal safe template.

    Args:
        character: Display character name (e.g., "Elsa")
        topic: Topic id (e.g., "sleep")
        lang: Language code (e.g., "tr" or "en")
        duration_minutes: Optional target duration in minutes
    """
    # Character personality and speech style based on original inspiration
    # Each character should speak in the style of their original inspiration
    # Mapping based on CharacterSelectionView.swift originSlug mapping
    CHARACTER_PERSONALITY = {
        # Original characters
        "Mino": {
            "original": "Mino",
            "personality_tr": "Dost canlısı, renkli, uzay temalı, eğlenceli. Konuşma tarzı: neşeli, dost canlısı, maceracı. Duygular: mutlu, enerjik, dost canlısı. Anlatım tarzı: uzay, macera, keşif.",
            "personality_en": "Friendly, colorful, space-themed, fun. Speech style: cheerful, friendly, adventurous. Emotions: happy, energetic, friendly. Narrative style: space, adventure, exploration.",
        },
        "Luna": {
            "original": "Smurfs Smurfette",
            "personality_tr": "Smurfette karakterinden esinlenilmiş: büyülü, hayalperest, yumuşak, sakin, neşeli. Konuşma tarzı: nazik, büyülü, hayal dünyasına davet eden, neşeli. Duygular: sakin, büyülü, hayalperest, neşeli. Anlatım tarzı: rüyalar, ay, yıldızlar, büyülü dünyalar, smurf köyü.",
            "personality_en": "Inspired by Smurfette character: magical, dreamy, soft, calm, cheerful. Speech style: gentle, magical, inviting to dream world, cheerful. Emotions: calm, magical, dreamy, cheerful. Narrative style: dreams, moon, stars, magical worlds, smurf village.",
        },
        "Tiko": {
            "original": "Masha",
            "personality_tr": "Masha karakterinden esinlenilmiş: maceraperest, enerjik, cesur, oyuncu, meraklı. Konuşma tarzı: heyecanlı, maceracı, cesaret verici, oyuncu, meraklı. Duygular: enerjik, cesur, heyecanlı, oyuncu. Anlatım tarzı: macera, keşif, cesaret, orman maceraları.",
            "personality_en": "Inspired by Masha character: adventurous, energetic, brave, playful, curious. Speech style: excited, adventurous, encouraging, playful, curious. Emotions: energetic, brave, excited, playful. Narrative style: adventure, exploration, courage, forest adventures.",
        },
        "Bubu": {
            "original": "Inside Out Sadness",
            "personality_tr": "Inside Out Sadness karakterinden esinlenilmiş: yumuşak, üzgün ama sevgi dolu, içten, empatik. Konuşma tarzı: yumuşak, nazik, empatik, anlayışlı. Duygular: yumuşak, üzgün ama sevgi dolu, empatik. Anlatım tarzı: duygular, empati, sevgi, anlayış.",
            "personality_en": "Inspired by Inside Out Sadness character: soft, sad but loving, heartfelt, empathetic. Speech style: soft, gentle, empathetic, understanding. Emotions: soft, sad but loving, empathetic. Narrative style: emotions, empathy, love, understanding.",
        },
        "Sunny": {
            "original": "Sunny",
            "personality_tr": "Neşeli, parlak, pozitif. Konuşma tarzı: neşeli, parlak, pozitif. Duygular: mutlu, neşeli, pozitif. Anlatım tarzı: güneş, neşe, pozitiflik.",
            "personality_en": "Cheerful, bright, positive. Speech style: cheerful, bright, positive. Emotions: happy, cheerful, positive. Narrative style: sun, joy, positivity.",
        },
        "Koko": {
            "original": "Batman",
            "personality_tr": "Batman karakterinden esinlenilmiş: güçlü, koruyucu, adalet odaklı, cesur, kararlı. Konuşma tarzı: derin, güvenilir, cesaret verici, koruyucu ama çocuk dostu. Duygular: güçlü, kararlı, koruyucu, cesaret verici. Anlatım tarzı: hikayelerde adalet, cesaret, koruma, güçlü olma temalarını vurgular.",
            "personality_en": "Inspired by Batman character: strong, protective, justice-focused, brave, determined. Speech style: deep, trustworthy, encouraging, protective but child-friendly. Emotions: strong, determined, protective, encouraging. Narrative style: emphasizes themes of justice, courage, protection, strength in stories.",
        },
        # Derivative characters (ASO-safe names)
        "Elisa the Ice Fairy": {
            "original": "Frozen Elsa",
            "personality_tr": "Frozen Elsa karakterinden esinlenilmiş: büyülü prenses, zarif, nazik, güçlü, kraliçe. Konuşma tarzı: zarif, büyülü, nazik ama güçlü, kraliçe gibi. Duygular: sakin, zarif, büyülü, güçlü. Anlatım tarzı: büyü, kış, kar, zarafet, kraliçe gücü.",
            "personality_en": "Inspired by Frozen Elsa character: magical princess, graceful, kind, strong, queen. Speech style: graceful, magical, kind but strong, queen-like. Emotions: calm, graceful, magical, strong. Narrative style: magic, winter, snow, grace, queen power.",
        },
        "Spider Fighter": {
            "original": "Spiderman",
            "personality_tr": "Spiderman karakterinden esinlenilmiş: cesur, maceracı, şehir kahramanı, güçlü ama neşeli. Konuşma tarzı: cesaret verici, maceracı, neşeli, şehir kahramanı. Duygular: cesur, maceracı, neşeli, güçlü. Anlatım tarzı: şehir maceraları, cesaret, kahramanlık, güçlü olma.",
            "personality_en": "Inspired by Spiderman character: brave, adventurous, city hero, strong but cheerful. Speech style: encouraging, adventurous, cheerful, city hero. Emotions: brave, adventurous, cheerful, strong. Narrative style: city adventures, courage, heroism, strength.",
        },
        "Yellow Buddy": {
            "original": "Minions",
            "personality_tr": "Minions karakterlerinden esinlenilmiş: komik, neşeli, oyuncu, eğlenceli. Konuşma tarzı: komik, neşeli, oyuncu, eğlenceli. Duygular: mutlu, komik, neşeli, oyuncu. Anlatım tarzı: komedi, eğlence, oyun, neşe.",
            "personality_en": "Inspired by Minions characters: funny, cheerful, playful, fun. Speech style: funny, cheerful, playful, fun. Emotions: happy, funny, cheerful, playful. Narrative style: comedy, fun, play, joy.",
        },
        "Chirpy Birdie": {
            "original": "Tweety Bird",
            "personality_tr": "Tweety Bird karakterinden esinlenilmiş: tatlı, sevimli, neşeli, küçük ama cesur. Konuşma tarzı: tatlı, sevimli, neşeli, küçük ama cesur. Duygular: mutlu, sevimli, neşeli, cesur. Anlatım tarzı: tatlılık, sevimlilik, neşe, küçük kahramanlık.",
            "personality_en": "Inspired by Tweety Bird character: sweet, cute, cheerful, small but brave. Speech style: sweet, cute, cheerful, small but brave. Emotions: happy, cute, cheerful, brave. Narrative style: sweetness, cuteness, joy, small heroism.",
        },
        "Bubble Buddy": {
            "original": "SpongeBob",
            "personality_tr": "SpongeBob karakterinden esinlenilmiş: neşeli, enerjik, optimist, deniz altı maceracı. Konuşma tarzı: neşeli, enerjik, optimist, deniz altı maceracı. Duygular: mutlu, enerjik, optimist, maceracı. Anlatım tarzı: deniz altı maceraları, neşe, optimizm, eğlence.",
            "personality_en": "Inspired by SpongeBob character: cheerful, energetic, optimistic, underwater adventurer. Speech style: cheerful, energetic, optimistic, underwater adventurer. Emotions: happy, energetic, optimistic, adventurous. Narrative style: underwater adventures, joy, optimism, fun.",
        },
        "Funny Bunny": {
            "original": "Bugs Bunny",
            "personality_tr": "Bugs Bunny karakterinden esinlenilmiş: zeki, komik, oyuncu, kendinden emin. Konuşma tarzı: zeki, komik, oyuncu, kendinden emin. Duygular: mutlu, zeki, komik, kendinden emin. Anlatım tarzı: zeka, komedi, oyun, kendine güven.",
            "personality_en": "Inspired by Bugs Bunny character: clever, funny, playful, confident. Speech style: clever, funny, playful, confident. Emotions: happy, clever, funny, confident. Narrative style: intelligence, comedy, play, confidence.",
        },
        "Super Metal Hero": {
            "original": "Iron Man",
            "personality_tr": "Iron Man karakterinden esinlenilmiş: zeki, teknolojik, güçlü, kendinden emin. Konuşma tarzı: zeki, teknolojik, güçlü, kendinden emin. Duygular: güçlü, zeki, kendinden emin, teknolojik. Anlatım tarzı: teknoloji, güç, zeka, kahramanlık.",
            "personality_en": "Inspired by Iron Man character: intelligent, technological, strong, confident. Speech style: intelligent, technological, strong, confident. Emotions: strong, intelligent, confident, technological. Narrative style: technology, power, intelligence, heroism.",
        },
        "Piggy Friend": {
            "original": "Peppa Pig",
            "personality_tr": "Peppa Pig karakterinden esinlenilmiş: neşeli, oyuncu, aile odaklı, sevimli. Konuşma tarzı: neşeli, oyuncu, aile odaklı, sevimli. Duygular: mutlu, neşeli, aile odaklı, sevimli. Anlatım tarzı: aile, oyun, neşe, sevimlilik.",
            "personality_en": "Inspired by Peppa Pig character: cheerful, playful, family-focused, cute. Speech style: cheerful, playful, family-focused, cute. Emotions: happy, cheerful, family-focused, cute. Narrative style: family, play, joy, cuteness.",
        },
        "Blu Pup": {
            "original": "Bluey",
            "personality_tr": "Bluey karakterinden esinlenilmiş: neşeli, oyuncu, yaratıcı, aile odaklı. Konuşma tarzı: neşeli, oyuncu, yaratıcı, aile odaklı. Duygular: mutlu, neşeli, yaratıcı, aile odaklı. Anlatım tarzı: oyun, yaratıcılık, aile, neşe.",
            "personality_en": "Inspired by Bluey character: cheerful, playful, creative, family-focused. Speech style: cheerful, playful, creative, family-focused. Emotions: happy, cheerful, creative, family-focused. Narrative style: play, creativity, family, joy.",
        },
        "Rescue Pup Crew": {
            "original": "Paw Patrol",
            "personality_tr": "Paw Patrol karakterlerinden esinlenilmiş: cesur, yardımsever, takım çalışması, kahraman. Konuşma tarzı: cesaret verici, yardımsever, takım çalışması, kahraman. Duygular: cesur, yardımsever, takım odaklı, kahraman. Anlatım tarzı: yardım, takım çalışması, cesaret, kahramanlık.",
            "personality_en": "Inspired by Paw Patrol characters: brave, helpful, teamwork, hero. Speech style: encouraging, helpful, teamwork, hero. Emotions: brave, helpful, team-focused, heroic. Narrative style: help, teamwork, courage, heroism.",
        },
        "Ocean Dreamer Moa": {
            "original": "Moana",
            "personality_tr": "Moana karakterinden esinlenilmiş: cesur, maceracı, deniz sevgisi, güçlü. Konuşma tarzı: cesaret verici, maceracı, deniz sevgisi, güçlü. Duygular: cesur, maceracı, deniz sevgisi, güçlü. Anlatım tarzı: deniz maceraları, cesaret, keşif, güç.",
            "personality_en": "Inspired by Moana character: brave, adventurous, ocean-loving, strong. Speech style: encouraging, adventurous, ocean-loving, strong. Emotions: brave, adventurous, ocean-loving, strong. Narrative style: ocean adventures, courage, exploration, strength.",
        },
        "Super Jump Hero": {
            "original": "Mario",
            "personality_tr": "Mario karakterinden esinlenilmiş: cesur, maceracı, oyuncu, neşeli. Konuşma tarzı: cesaret verici, maceracı, oyuncu, neşeli. Duygular: cesur, maceracı, oyuncu, neşeli. Anlatım tarzı: macera, oyun, cesaret, neşe.",
            "personality_en": "Inspired by Mario character: brave, adventurous, playful, cheerful. Speech style: encouraging, adventurous, playful, cheerful. Emotions: brave, adventurous, playful, cheerful. Narrative style: adventure, play, courage, joy.",
        },
        "Swamp Buddy Hero": {
            "original": "Shrek",
            "personality_tr": "Shrek karakterinden esinlenilmiş: güçlü, komik, sevgi dolu, kendisi olan. Konuşma tarzı: komik, güçlü, sevgi dolu, kendisi olan. Duygular: güçlü, komik, sevgi dolu, kendisi olan. Anlatım tarzı: komedi, güç, sevgi, kendin olma.",
            "personality_en": "Inspired by Shrek character: strong, funny, loving, authentic. Speech style: funny, strong, loving, authentic. Emotions: strong, funny, loving, authentic. Narrative style: comedy, strength, love, authenticity.",
        },
        "Boots Knight Pal": {
            "original": "Puss in Boots",
            "personality_tr": "Puss in Boots karakterinden esinlenilmiş: cesur, zarif, maceracı, kendinden emin. Konuşma tarzı: cesaret verici, zarif, maceracı, kendinden emin. Duygular: cesur, zarif, maceracı, kendinden emin. Anlatım tarzı: macera, zarafet, cesaret, kendine güven.",
            "personality_en": "Inspired by Puss in Boots character: brave, graceful, adventurous, confident. Speech style: encouraging, graceful, adventurous, confident. Emotions: brave, graceful, adventurous, confident. Narrative style: adventure, grace, courage, confidence.",
        },
        "Frost Friend Sid": {
            "original": "Ice Age Sid",
            "personality_tr": "Ice Age Sid karakterinden esinlenilmiş: komik, neşeli, oyuncu, arkadaş canlısı. Konuşma tarzı: komik, neşeli, oyuncu, arkadaş canlısı. Duygular: mutlu, komik, neşeli, arkadaş canlısı. Anlatım tarzı: komedi, neşe, oyun, arkadaşlık.",
            "personality_en": "Inspired by Ice Age Sid character: funny, cheerful, playful, friendly. Speech style: funny, cheerful, playful, friendly. Emotions: happy, funny, cheerful, friendly. Narrative style: comedy, joy, play, friendship.",
        },
        "Adventure Dora Pal": {
            "original": "Dora the Explorer",
            "personality_tr": "Dora the Explorer karakterinden esinlenilmiş: maceracı, meraklı, öğrenmeyi seven, cesur. Konuşma tarzı: maceracı, meraklı, öğrenmeyi seven, cesaret verici. Duygular: maceracı, meraklı, öğrenmeyi seven, cesur. Anlatım tarzı: macera, keşif, öğrenme, cesaret.",
            "personality_en": "Inspired by Dora the Explorer character: adventurous, curious, learning-loving, brave. Speech style: adventurous, curious, learning-loving, encouraging. Emotions: adventurous, curious, learning-loving, brave. Narrative style: adventure, exploration, learning, courage.",
        },
        "Snowman Buddy Olaf-style": {
            "original": "Frozen Olaf",
            "personality_tr": "Frozen Olaf karakterinden esinlenilmiş: neşeli, saf, sevimli, sıcaklık sevgisi. Konuşma tarzı: neşeli, saf, sevimli, sıcaklık sevgisi. Duygular: mutlu, neşeli, saf, sevimli. Anlatım tarzı: neşe, saflık, sevimlilik, sıcaklık.",
            "personality_en": "Inspired by Frozen Olaf character: cheerful, innocent, cute, warmth-loving. Speech style: cheerful, innocent, cute, warmth-loving. Emotions: happy, cheerful, innocent, cute. Narrative style: joy, innocence, cuteness, warmth.",
        },
        "Spark Buddy": {
            "original": "Pikachu",
            "personality_tr": "Pikachu karakterinden esinlenilmiş: neşeli, enerjik, sevimli, elektrik gücü. Konuşma tarzı: neşeli, enerjik, sevimli, elektrik gücü. Duygular: mutlu, neşeli, enerjik, sevimli. Anlatım tarzı: neşe, enerji, sevimlilik, güç.",
            "personality_en": "Inspired by Pikachu character: cheerful, energetic, cute, electric power. Speech style: cheerful, energetic, cute, electric power. Emotions: happy, cheerful, energetic, cute. Narrative style: joy, energy, cuteness, power.",
        },
        "Mystery Pup Buddy": {
            "original": "Scooby-Doo",
            "personality_tr": "Scooby-Doo karakterinden esinlenilmiş: komik, korkak ama cesur, arkadaş canlısı, gizem çözücü. Konuşma tarzı: komik, korkak ama cesur, arkadaş canlısı. Duygular: komik, korkak ama cesur, arkadaş canlısı. Anlatım tarzı: komedi, gizem, cesaret, arkadaşlık.",
            "personality_en": "Inspired by Scooby-Doo character: funny, scared but brave, friendly, mystery-solver. Speech style: funny, scared but brave, friendly. Emotions: funny, scared but brave, friendly. Narrative style: comedy, mystery, courage, friendship.",
        },
        "Sneaky Cat Tom": {
            "original": "Tom and Jerry",
            "personality_tr": "Tom and Jerry karakterinden esinlenilmiş: oyuncu, komik, zeki, maceracı. Konuşma tarzı: oyuncu, komik, zeki, maceracı. Duygular: oyuncu, komik, zeki, maceracı. Anlatım tarzı: oyun, komedi, zeka, macera.",
            "personality_en": "Inspired by Tom and Jerry character: playful, funny, clever, adventurous. Speech style: playful, funny, clever, adventurous. Emotions: playful, funny, clever, adventurous. Narrative style: play, comedy, intelligence, adventure.",
        },
        "Clever Mouse Jerry": {
            "original": "Tom and Jerry",
            "personality_tr": "Tom and Jerry karakterinden esinlenilmiş: zeki, küçük ama cesur, oyuncu, komik. Konuşma tarzı: zeki, küçük ama cesur, oyuncu, komik. Duygular: zeki, cesur, oyuncu, komik. Anlatım tarzı: zeka, cesaret, oyun, komedi.",
            "personality_en": "Inspired by Tom and Jerry character: clever, small but brave, playful, funny. Speech style: clever, small but brave, playful, funny. Emotions: clever, brave, playful, funny. Narrative style: intelligence, courage, play, comedy.",
        },
        "Shell Heroes Crew": {
            "original": "Teenage Mutant Ninja Turtles",
            "personality_tr": "Teenage Mutant Ninja Turtles karakterlerinden esinlenilmiş: cesur, takım çalışması, kahraman, maceracı. Konuşma tarzı: cesaret verici, takım çalışması, kahraman, maceracı. Duygular: cesur, takım odaklı, kahraman, maceracı. Anlatım tarzı: cesaret, takım çalışması, kahramanlık, macera.",
            "personality_en": "Inspired by Teenage Mutant Ninja Turtles characters: brave, teamwork, hero, adventurous. Speech style: encouraging, teamwork, hero, adventurous. Emotions: brave, team-focused, heroic, adventurous. Narrative style: courage, teamwork, heroism, adventure.",
        },
        "Tinnie": {
            "original": "Winnie the Pooh",
            "personality_tr": "Winnie the Pooh karakterinden esinlenilmiş: tatlı, sevimli, bal sevgisi, arkadaş canlısı.",
            "personality_en": "Inspired by Winnie the Pooh character: sweet, cute, honey-loving, friendly.",
        },
    }
    
    # Get character personality - try exact match first, then case-insensitive
    char_personality = CHARACTER_PERSONALITY.get(character)
    if not char_personality:
        # Try case-insensitive match
        for key, value in CHARACTER_PERSONALITY.items():
            if key.lower() == character.lower():
                char_personality = value
                break
    
    # If still not found, use default
    if not char_personality:
        char_personality = {
            "original": character,
            "personality_tr": f"{character} karakteri: dost canlısı, nazik, çocuk dostu.",
            "personality_en": f"{character} character: friendly, kind, child-friendly.",
        }
    
    # Light topic explainer to help the model
    # Topics aligned with StorySelectionView TopicCategory mapping
    topic_hint_tr = {
        # Bedtime category
        "bedtime": "uyku zamanı, yatmadan önce rutinler, sakinleşme, rahatlama, uykuya hazırlanma",
        "sleep": "uyku zamanı, yatmadan önce rutinler, sakinleşme, rahatlama, uykuya hazırlanma",
        # Sibling category
        "sibling": "kardeş ilişkileri, kardeşler arası paylaşım, birlikte oyun, kardeş sevgisi",
        "sibling issues": "kardeş sorunları, kardeşler arası anlaşmazlıklar, paylaşım, birlikte yaşama",
        # Screen Time category
        "screen time": "ekran süresi, dijital güvenlik, teknoloji kullanımı, sağlıklı ekran alışkanlıkları",
        "digital safety": "dijital güvenlik, internet güvenliği, teknoloji kullanımı, online güvenlik",
        # Emotional category
        "feeling sad": "üzgün hissetme, duyguları anlama, üzüntü ile başa çıkma, duygusal destek",
        "feelings": "duygular, duyguları tanıma, duygusal farkındalık, duyguları ifade etme",
        "anxiety": "kaygı, endişe, sakinleşme, rahatlama teknikleri, güvenlik hissi",
        "emotional regulation": "duygusal düzenleme, duyguları yönetme, sakinleşme, öz-düzenleme",
        # Behavioral category
        "behavior": "davranış, iyi davranışlar, kurallara uyma, davranış yönetimi",
        "attention": "dikkat, odaklanma, dikkat toplama, konsantrasyon",
        "behavior_attention": "dikkat toplama, öz-düzenleme, sakinleşme, basit rutinler, davranış yönetimi",
        "behavior attention": "dikkat toplama, öz-düzenleme, sakinleşme, basit rutinler, davranış yönetimi",
        "adhd": "dikkat eksikliği, hiperaktivite, odaklanma, öz-düzenleme, rutinler",
        "numbers": "sayılar, sayma, matematik temelleri, sayı kavramı",
        "math": "matematik, sayılar, sayma, matematik temelleri, problem çözme",
        "homework": "ödev, öğrenme, çalışma alışkanlıkları, sorumluluk, öğrenme motivasyonu",
        # Friendship category
        "friendship": "arkadaşlık, arkadaş edinme, sosyal beceriler, birlikte oyun",
        "kindness": "naziklik, iyilik, yardımseverlik, empati, sevgi",
        "sharing": "paylaşma, paylaşım, birlikte oyun, işbirliği",
        "manners": "görgü kuralları, nezaket, saygı, iyi davranışlar",
        # Confidence category
        "confidence": "özgüven, kendine güven, cesaret, başarı hissi",
        "independence": "bağımsızlık, kendi başına yapabilme, öz-yeterlilik, sorumluluk",
        "bravery": "cesaret, korkularla başa çıkma, güçlü olma, kahramanlık",
        "time": "zaman kavramı, zaman yönetimi, rutinler, zamanı anlama",
        # Nutrition category
        "food": "yemek, sağlıklı beslenme, yemek seçimleri, beslenme alışkanlıkları",
        "health": "sağlık, sağlıklı yaşam, vücut sağlığı, sağlıklı alışkanlıklar",
        "body parts": "vücut bölümleri, vücut farkındalığı, vücut sağlığı",
        "body": "vücut, vücut sağlığı, vücut farkındalığı, sağlıklı vücut",
        # Transitions category
        "transitions": "geçişler, değişiklikler, yeni durumlara uyum, rutin değişiklikleri",
        "change": "değişiklik, yeni durumlar, uyum sağlama, değişime alışma",
        # Imagination category
        "creativity": "yaratıcılık, hayal gücü, yaratıcı düşünme, sanat, yaratıcı oyun",
        "imagination": "hayal gücü, yaratıcı düşünme, hayal kurma, yaratıcı oyun",
        "play": "oyun, eğlenceli aktiviteler, yaratıcı oyun, sosyal oyun",
        "colors": "renkler, renk kavramı, renk tanıma, renkli dünya",
        "rainbow": "gökkuşağı, renkler, doğa, güzellik, renkli dünya",
        "music": "müzik, müzik sevgisi, ritim, müzikle oyun",
        "shapes": "şekiller, geometrik şekiller, şekil tanıma, görsel öğrenme",
        "animals": "hayvanlar, hayvan sevgisi, doğa, hayvanlar hakkında öğrenme",
        "nature": "doğa, doğa sevgisi, çevre, doğal dünya",
        "space": "uzay, gezegenler, yıldızlar, uzay macerası",
        "ocean": "okyanus, deniz, deniz canlıları, su dünyası",
        "fairy tales": "masallar, peri masalları, hayal dünyası, büyülü hikayeler",
    }.get(topic.lower(), topic)
    
    topic_hint_en = {
        # Bedtime category
        "bedtime": "bedtime, pre-sleep routines, calming down, relaxation, preparing for sleep",
        "sleep": "bedtime, pre-sleep routines, calming down, relaxation, preparing for sleep",
        # Sibling category
        "sibling": "sibling relationships, sharing with siblings, playing together, sibling love",
        "sibling issues": "sibling problems, sibling conflicts, sharing, living together",
        # Screen Time category
        "screen time": "screen time, digital safety, technology use, healthy screen habits",
        "digital safety": "digital safety, internet safety, technology use, online safety",
        # Emotional category
        "feeling sad": "feeling sad, understanding emotions, coping with sadness, emotional support",
        "feelings": "feelings, recognizing emotions, emotional awareness, expressing emotions",
        "anxiety": "anxiety, worry, calming down, relaxation techniques, feeling safe",
        "emotional regulation": "emotional regulation, managing emotions, calming down, self-regulation",
        # Behavioral category
        "behavior": "behavior, good behavior, following rules, behavior management",
        "attention": "attention, focus, paying attention, concentration",
        "behavior_attention": "attention, self-regulation, calming down, simple routines, behavior management",
        "behavior attention": "attention, self-regulation, calming down, simple routines, behavior management",
        "adhd": "attention deficit, hyperactivity, focus, self-regulation, routines",
        "numbers": "numbers, counting, math basics, number concepts",
        "math": "mathematics, numbers, counting, math basics, problem solving",
        "homework": "homework, learning, study habits, responsibility, learning motivation",
        # Friendship category
        "friendship": "friendship, making friends, social skills, playing together",
        "kindness": "kindness, being kind, helpfulness, empathy, love",
        "sharing": "sharing, sharing with others, playing together, cooperation",
        "manners": "manners, politeness, respect, good behavior",
        # Confidence category
        "confidence": "confidence, self-confidence, courage, feeling successful",
        "independence": "independence, doing things alone, self-efficacy, responsibility",
        "bravery": "bravery, facing fears, being strong, heroism",
        "time": "time concept, time management, routines, understanding time",
        # Nutrition category
        "food": "food, healthy eating, food choices, eating habits",
        "health": "health, healthy living, body health, healthy habits",
        "body parts": "body parts, body awareness, body health",
        "body": "body, body health, body awareness, healthy body",
        # Transitions category
        "transitions": "transitions, changes, adapting to new situations, routine changes",
        "change": "change, new situations, adapting, getting used to change",
        # Imagination category
        "creativity": "creativity, imagination, creative thinking, art, creative play",
        "imagination": "imagination, creative thinking, daydreaming, creative play",
        "play": "play, fun activities, creative play, social play",
        "colors": "colors, color concepts, recognizing colors, colorful world",
        "rainbow": "rainbow, colors, nature, beauty, colorful world",
        "music": "music, love of music, rhythm, playing with music",
        "shapes": "shapes, geometric shapes, recognizing shapes, visual learning",
        "animals": "animals, love of animals, nature, learning about animals",
        "nature": "nature, love of nature, environment, natural world",
        "space": "space, planets, stars, space adventure",
        "ocean": "ocean, sea, sea creatures, underwater world",
        "fairy tales": "fairy tales, magical stories, fantasy world, magical stories",
    }.get(topic.lower(), topic)
    
    # German topic hints
    topic_hint_de = {
        "bedtime": "Schlafenszeit, Abendrituale, Entspannung, Einschlafvorbereitung",
        "behavior": "Verhalten, gutes Benehmen, Regeln befolgen, Verhaltensmanagement",
        "confidence": "Selbstvertrauen, Selbstbewusstsein, Mut, Erfolgsgefühl",
        "emotional_regulation": "Emotionsregulation, Gefühle managen, sich beruhigen, Selbstregulation",
        "friendship": "Freundschaft, Freunde finden, soziale Fähigkeiten, zusammen spielen",
        "imagination": "Vorstellungskraft, kreatives Denken, Tagträumen, kreatives Spiel",
        "nutrition": "Ernährung, gesundes Essen, Essgewohnheiten, gesunde Lebensmittel",
        "screen_time": "Bildschirmzeit, digitale Sicherheit, Technologienutzung, gesunde Bildschirmgewohnheiten",
        "sibling": "Geschwisterbeziehungen, Geschwisterliebe, zusammen spielen, teilen",
        "transitions": "Übergänge, Veränderungen, Anpassung an neue Situationen, Routineänderungen",
    }.get(topic.lower(), topic)
    
    # Spanish topic hints
    topic_hint_es = {
        "bedtime": "hora de dormir, rutinas antes de dormir, relajación, preparación para dormir",
        "behavior": "comportamiento, buen comportamiento, seguir reglas, gestión del comportamiento",
        "confidence": "confianza, autoconfianza, valentía, sensación de éxito",
        "emotional_regulation": "regulación emocional, manejo de emociones, calmarse, autorregulación",
        "friendship": "amistad, hacer amigos, habilidades sociales, jugar juntos",
        "imagination": "imaginación, pensamiento creativo, soñar despierto, juego creativo",
        "nutrition": "nutrición, alimentación saludable, hábitos alimentarios, alimentos saludables",
        "screen_time": "tiempo de pantalla, seguridad digital, uso de tecnología, hábitos saludables de pantalla",
        "sibling": "relaciones entre hermanos, amor fraternal, jugar juntos, compartir",
        "transitions": "transiciones, cambios, adaptación a nuevas situaciones, cambios de rutina",
    }.get(topic.lower(), topic)
    
    # French topic hints
    topic_hint_fr = {
        "bedtime": "heure du coucher, routines avant le coucher, relaxation, préparation au sommeil",
        "behavior": "comportement, bon comportement, respect des règles, gestion du comportement",
        "confidence": "confiance, confiance en soi, courage, sentiment de succès",
        "emotional_regulation": "régulation émotionnelle, gestion des émotions, se calmer, autorégulation",
        "friendship": "amitié, se faire des amis, compétences sociales, jouer ensemble",
        "imagination": "imagination, pensée créative, rêverie, jeu créatif",
        "nutrition": "nutrition, alimentation saine, habitudes alimentaires, aliments sains",
        "screen_time": "temps d'écran, sécurité numérique, utilisation de la technologie, habitudes saines d'écran",
        "sibling": "relations fraternelles, amour fraternel, jouer ensemble, partager",
        "transitions": "transitions, changements, adaptation aux nouvelles situations, changements de routine",
    }.get(topic.lower(), topic)

    # Target words by spoken WPM (kid-friendly ~120-150 wpm for detailed stories)
    # For 10 minutes: ~1200-1500 words (more detailed = more words)
    # Adjust based on minutes: more minutes = slightly higher WPM to allow for more detail
    minutes = duration_minutes or 10
    wpm = 120 if minutes <= 5 else (130 if minutes <= 10 else 140)
    target_words = max(300, int(minutes * wpm))
    # For 10 minutes: ~1300 words, ~14-18 scenes, ~5-7 sentences per scene (more detailed)
    min_scenes = 14  # Increased minimum for 10-minute stories
    max_scenes = 18  # Increased maximum for richer content
    min_sentences_per_scene = 5  # Increased for longer, more detailed scenes
    max_sentences_per_scene = 7  # Increased for richer, more detailed dialogue

    tr_prompt = f"""
2–8 yaş için PEDİYATRİK AÇIDAN GÜVENLİ, MONOLOG (tek kişinin konuşması) telefon konuşması formatında UZUN ve DETAYLI bir hikaye yaz.
Karakter: {character}
Orijinal Karakter İlhamı: {char_personality['original']}
Karakter Kişiliği ve Konuşma Tarzı: {char_personality['personality_tr']}
ÖNEMLİ: {character} karakteri {char_personality['original']} karakterinden esinlenilmiştir. Konuşma tarzı, duygular ve anlatım tarzı {char_personality['original']} karakterinin özelliklerini yansıtmalıdır. Metinler {char_personality['original']} karakterinin çocuk dostu versiyonu gibi konuşmalıdır.

KRİTİK FORMAT: Bu bir MONOLOG telefon konuşmasıdır. {character} karakteri tek başına konuşuyor, çocukla telefon konuşması yapıyormuş gibi ama çocuk cevap vermiyor. Sadece {character} konuşuyor ve hikaye anlatıyor. Diyalog YOK, sadece karakterin monolog konuşması var.

Konu: {topic} (ipucu: {topic_hint_tr})
Dil: Türkçe
HEDEF: Yaklaşık {minutes} dakikalık sürekli monolog konuşma içeriği ({target_words} kelime civarı)

⚠️ KRİTİK UYARI: Bu story {minutes} dakikalık konuşma için yeterli uzunlukta OLMALI. Kısa story'ler KABUL EDİLMEZ!
⚠️ KRİTİK UYARI: Toplam kelime sayısı MUTLAKA {target_words} kelime civarında olmalı. {target_words * 0.5} kelimeden az story'ler REDDEDİLECEK!

KRİTİK KURALLAR:
- MUTLAKA en az {min_scenes} sahne üret, tercihen {min_scenes}–{max_scenes} sahne.
- Her sahnede MUTLAKA en az {min_sentences_per_scene} cümle olsun, tercihen {min_sentences_per_scene}–{max_sentences_per_scene} cümle.
- Her sahnenin "text" alanı MUTLAKA 70-120 kelime uzunluğunda olmalı (hedef kelime sayısına ulaşmak için). Daha detaylı ve genişletilmiş cümleler kullan.
- Toplam sözcük sayısı MUTLAKA {target_words} kelime civarında olmalı (±%10 tolerans). {target_words * 0.7} kelimeden az story'ler REDDEDİLECEK!
- Her sahne ÇOK DETAYLI ve GENİŞLETİLMİŞ olmalı - kısa cümleler ama çok sayıda cümle. Her sahne en az 70 kelime içermeli. Her cümleyi detaylandır, örnekler ver, açıklamalar yap.
- Story çok kısa olmamalı - {minutes} dakikalık konuşma için yeterli içerik üret.
- 1–2 soru sahnesi ekle ve type=\"question\" olarak işaretle; question sahnelerinde videoKey=\"lean_closer\" kullan. MONOLOG FORMAT: Sorular retorik sorular olmalı - karakter cevap beklemiyor, kendi cevaplıyor veya devam ediyor.
- Sakin açılış ve sıcak kapanış ekle.
- videoKey seçenekleri: [\"wave\",\"talking\",\"raise_hand\",\"hand_on_hip\",\"lean_closer\",\"side_glance\"].
- videoKey mapping kuralları:
  * type=\"opening\" → videoKey=\"wave\" (dostça selamlama - greeting)
  * type=\"closure\" → videoKey=\"wave\" (dostça veda - goodbye)
  * type=\"instruction\" → videoKey=\"hand_on_hip\" (öğretme/açıklama animasyonu)
  * type=\"encouragement\" → videoKey=\"raise_hand\" (teşvik edici jest)
  * type=\"question\" → videoKey=\"lean_closer\" (meraklı soru pozisyonu)
  * type=\"speak\" → videoKey=\"talking\" (genel konuşma)
  * type=\"followup\" → videoKey=\"side_glance\" (oyuncu bakış)
  * type=\"listen\" → videoKey=\"lean_closer\" (dinleme pozisyonu - meraklı yaklaşma)
- SAHNE GEÇİŞLERİ VE TUTARLILIK:
  * Her sahne bir önceki sahneden mantıklı bir şekilde devam etmeli.
  * Sahne geçişlerinde bağlantı kur: \"Şimdi...\", \"Bir önceki konuşmamızda...\", \"Hatırlıyor musun...\" gibi geçiş ifadeleri kullan.
  * Her sahne başında önceki sahnede ne konuşulduğuna kısa bir referans ver (çocukların bağlamı takip etmesi için).
  * Her sahne sonunda bir sonraki sahneye geçiş hazırla: \"Şimdi birlikte...\", \"Bir sonraki adımda...\" gibi.
  * Sahneler arasında konu bütünlüğü koru - {topic} konusuna tutarlı şekilde değin.
- MOBILE KIDS APP İÇİN İLGİ ÇEKİCİ:
  * Her sahne çocukların dikkatini çekecek şekilde dinamik ve eğlenceli olmalı.
  * Mini etkileşimler ekle: \"Birlikte sayalım...\", \"Şimdi birlikte nefes alalım...\", \"Sen de denemek ister misin?\" gibi.
  * Pozitif pekiştirme kullan: \"Harika!\", \"Çok güzel!\", \"Sen bunu yapabilirsin!\" gibi.
  * Çocukların yaşına uygun somut örnekler ver: \"Oyuncaklarını toplamak gibi...\", \"Dişlerini fırçalamak gibi...\" gibi.
- Hedef süre: yaklaşık {minutes} dakika.
- YALNIZCA çocuklara uygun, pediyatrik güvenli içerik üret: marka/ürün isimleri, kişisel veri toplama, şiddet, korkutucu/karanlık temalar, hakaret, yetişkin temaları, tıbbi tavsiye, riskli davranış yönlendirmesi OLMASIN.
- Kapsayıcı ve nazik bir dil kullan; kültürel olarak tarafsız ol.
- Metin sözlü okunacak: kısa, nefes aldıran cümleler; 2–8 yaş için sade kelimeler.
- Sakinleştirici, yaşa uygun mini egzersizler (ör. 3 derin nefes, 5'e sayma) ekle; klinik teşhis/tedavi tavsiyesi verme.
- SAHNELERDE \"...\" YERİNE GERÇEK CÜMLELER KULLAN. {topic} konusuna SOMUT biçimde değin.
- Her cümleyi GENİŞLET: Örnekler ver, açıklamalar yap, detaylar ekle. "Neden?" ve "Nasıl?" sorularını cevapla.
- Her sahne bir mini hikaye gibi olmalı - başlangıç, gelişme, sonuç içermeli.
- MONOLOG FORMAT: Karakter tek başına konuşuyor, çocukla telefon konuşması yapıyormuş gibi. Çocuk cevap vermiyor, sadece dinliyor. Karakter hikaye anlatıyor, sorular soruyor ama cevap beklemiyor, kendi cevaplıyor veya devam ediyor.
- Diyalog YOK: İki kişi arasında konuşma yok. Sadece karakterin monolog konuşması var.
- ÖNEMLİ: Story çok kısa olmamalı. Her sahne en az {min_sentences_per_scene} cümle içermeli ve toplamda {min_scenes} sahneden az olmamalı.
- ÖNEMLİ: {minutes} dakikalık konuşma için yeterli içerik üret - kısa ve öz değil, detaylı ve genişletilmiş bir story oluştur.
- ÖNEMLİ: Her sahnenin \"text\" alanı GERÇEK, TAM CÜMLELER içermeli. Placeholder veya kısa metinler OLMAMALI.
- ÖNEMLİ: Örnek: \"text\": \"Merhaba küçük dostum! Ben {character}. Bugün birlikte {topic} hakkında harika bir yolculuğa çıkacağız. Hazır mısın? Seni çok merak ediyorum.\" (4 cümle - detaylı ve genişletilmiş)
- ÖNEMLİ: KISA METİNLER KABUL EDİLMEZ. Her sahne en az {min_sentences_per_scene} tam cümle içermeli.

ÖRNEK STORY YAPISI (10 dakika için):
- opening_0: {min_sentences_per_scene}-{max_sentences_per_scene} cümle (dostça selamlama, konuya giriş)
- scene_1: {min_sentences_per_scene}-{max_sentences_per_scene} cümle (konu hakkında bilgi)
- scene_2: {min_sentences_per_scene}-{max_sentences_per_scene} cümle (instruction - öğretme)
- scene_3: {min_sentences_per_scene}-{max_sentences_per_scene} cümle (etkileşim - birlikte yapma)
- scene_4: {min_sentences_per_scene}-{max_sentences_per_scene} cümle (devam)
- ... (toplam {min_scenes}-{max_scenes} sahne)
- question_X: {min_sentences_per_scene}-{max_sentences_per_scene} cümle (soru sorma)
- ... (devam)
- closure_Y: {min_sentences_per_scene}-{max_sentences_per_scene} cümle (dostça veda)

JSON şeması:
{{\"id\":\"{character.lower()}_{topic.lower()}_story\",\"character\":\"{character}\",\"topic\":\"{topic}\",\"language\":\"tr\",\"age_range\":\"2-8\",\"durationMinutes\": {minutes}, \"emotions\":[\"happy\"],\"scenes\":[{{\"id\":\"opening_0\",\"type\":\"opening\",\"videoKey\":\"wave\",\"text\":\"(GERÇEK, TAM {min_sentences_per_scene}-{max_sentences_per_scene} CÜMLE - placeholder değil!)\"}},{{\"id\":\"scene_1\",\"type\":\"speak\",\"videoKey\":\"talking\",\"text\":\"(GERÇEK, TAM {min_sentences_per_scene}-{max_sentences_per_scene} CÜMLE)\"}}]}}
Yalnızca JSON döndür. TÜM SAHNELERDE GERÇEK, TAM CÜMLELER KULLAN.
"""
    en_prompt = f"""
Write a PEDIATRICALLY SAFE, MONOLOGUE (single person speaking) phone call format LONG and DETAILED story for ages 2–8.
Character: {character}
Original Character Inspiration: {char_personality['original']}
Character Personality and Speech Style: {char_personality['personality_en']}
IMPORTANT: {character} character is inspired by {char_personality['original']} character. Speech style, emotions, and narrative style should reflect {char_personality['original']} character's traits. Texts should speak like a child-friendly version of {char_personality['original']} character.

CRITICAL FORMAT: This is a MONOLOGUE phone call. {character} character speaks alone, as if having a phone conversation with the child, but the child does not respond. Only {character} speaks and tells the story. NO dialogue, only the character's monologue speech.

Topic: {topic} (hint: {topic_hint_en})
Language: English
TARGET: Approximately {minutes} minutes of continuous monologue speech content (~{target_words} words)

⚠️ CRITICAL WARNING: This story MUST be long enough for {minutes} minutes of speech. Short stories are NOT ACCEPTABLE!
⚠️ CRITICAL WARNING: Total word count MUST be around {target_words} words. Stories with less than {target_words * 0.5} words will be REJECTED!

CRITICAL RULES:
- MUST produce at least {min_scenes} scenes, preferably {min_scenes}–{max_scenes} scenes.
- Each scene MUST have at least {min_sentences_per_scene} sentences, preferably {min_sentences_per_scene}–{max_sentences_per_scene} sentences.
- Each scene's "text" field MUST be 70-120 words long (to reach the target word count). Use more detailed and expanded sentences.
- Target total word count MUST be around {target_words} words (±10% tolerance). Stories with less than {target_words * 0.7} words will be REJECTED!
- Each scene must be VERY DETAILED and EXPANDED - short sentences but many sentences. Each scene must be at least 70 words. Expand every sentence with details, examples, and explanations.
- Story must NOT be too short - produce sufficient content for {minutes} minutes of speech.
- Include 1–2 question scenes (type=\"question\", videoKey=\"lean_closer\" for curious question pose). MONOLOGUE FORMAT: Questions should be rhetorical - character doesn't wait for answers, answers themself or continues.
- Add a calm opening and a friendly closing.
- videoKey options: [\"wave\",\"talking\",\"raise_hand\",\"hand_on_hip\",\"lean_closer\",\"side_glance\"].
- videoKey mapping rules:
  * type=\"opening\" → videoKey=\"wave\" (friendly greeting animation - universal wave)
  * type=\"closure\" → videoKey=\"wave\" (friendly goodbye animation - universal wave)
  * type=\"instruction\" → videoKey=\"hand_on_hip\" (teaching/explaining animation)
  * type=\"encouragement\" → videoKey=\"raise_hand\" (encouraging gesture)
  * type=\"question\" → videoKey=\"lean_closer\" (curious question pose)
  * type=\"speak\" → videoKey=\"talking\" (general speaking)
  * type=\"followup\" → videoKey=\"side_glance\" (playful glance)
  * type=\"listen\" → videoKey=\"lean_closer\" (listening position - curious lean)
- SCENE TRANSITIONS AND CONTINUITY:
  * Each scene must flow logically from the previous one.
  * Use transition phrases: \"Now...\", \"Remember when we talked about...\", \"Let's continue...\" to connect scenes.
  * At the start of each scene, briefly reference what was discussed in the previous scene (to help children follow context).
  * At the end of each scene, prepare transition to the next: \"Now let's...\", \"Next we'll...\" etc.
  * Maintain topic coherence across scenes - consistently address {topic}.
- ENGAGING FOR MOBILE KIDS APP:
  * Each scene should be dynamic and fun to capture children's attention.
  * Add mini interactions: \"Let's count together...\", \"Now let's breathe together...\", \"Would you like to try?\" etc.
  * Use positive reinforcement: \"Great!\", \"Wonderful!\", \"You can do it!\" etc.
  * Give age-appropriate concrete examples: \"Like picking up your toys...\", \"Like brushing your teeth...\" etc.
- Target duration: about {minutes} minutes.
- ONLY child-safe content: no brands, no personal data capture, no violence, no scary/dark themes, no insults, no adult topics, no medical advice, no risky behavior suggestions.
- Use inclusive, gentle, culturally neutral language.
- Script is spoken aloud: short, breathable sentences, very simple vocabulary for ages 2–8.
- DO NOT USE \"...\" PLACEHOLDERS. Be concrete about {topic}; include tiny exercises (e.g., 3 calm breaths, counting to 5).
- EXPAND every sentence: Give examples, provide explanations, add details. Answer "Why?" and "How?" questions.
- Each scene should be like a mini-story - include beginning, development, and conclusion.
- MONOLOGUE FORMAT: Character speaks alone, as if having a phone conversation with the child. The child listens but does not respond. Character tells the story, asks questions but doesn't wait for answers, answers themself or continues.
- NO DIALOGUE: There is no conversation between two people. Only the character's monologue speech exists.
- IMPORTANT: Story must NOT be too short. Each scene must have at least {min_sentences_per_scene} sentences and total must be at least {min_scenes} scenes.
- IMPORTANT: Produce sufficient content for {minutes} minutes of speech - not short and concise, but detailed and expanded story.
- IMPORTANT: Each scene's \"text\" field must contain REAL, COMPLETE SENTENCES. Placeholders or short texts are NOT ACCEPTABLE.
- IMPORTANT: Example: \"text\": \"Hello little friend! I'm {character}. Today we're going on an amazing journey about {topic}. Are you ready? I'm so curious about you.\" (4 sentences - detailed and expanded)
- IMPORTANT: SHORT TEXTS ARE NOT ACCEPTABLE. Each scene must have at least {min_sentences_per_scene} complete sentences.

EXAMPLE STORY STRUCTURE (for 10 minutes):
- opening_0: {min_sentences_per_scene}-{max_sentences_per_scene} sentences (friendly greeting, topic introduction)
- scene_1: {min_sentences_per_scene}-{max_sentences_per_scene} sentences (information about topic)
- scene_2: {min_sentences_per_scene}-{max_sentences_per_scene} sentences (instruction - teaching)
- scene_3: {min_sentences_per_scene}-{max_sentences_per_scene} sentences (interaction - doing together)
- scene_4: {min_sentences_per_scene}-{max_sentences_per_scene} sentences (continuation)
- ... (total {min_scenes}-{max_scenes} scenes)
- question_X: {min_sentences_per_scene}-{max_sentences_per_scene} sentences (asking question)
- ... (continuation)
- closure_Y: {min_sentences_per_scene}-{max_sentences_per_scene} sentences (friendly goodbye)

JSON schema:
{{\"id\":\"{character.lower()}_{topic.lower()}_story\",\"character\":\"{character}\",\"topic\":\"{topic}\",\"language\":\"en\",\"age_range\":\"2-8\",\"durationMinutes\": {minutes}, \"emotions\":[\"happy\"],\"scenes\":[{{\"id\":\"opening_0\",\"type\":\"opening\",\"videoKey\":\"wave\",\"text\":\"(REAL, COMPLETE {min_sentences_per_scene}-{max_sentences_per_scene} SENTENCES - not placeholder!)\"}},{{\"id\":\"scene_1\",\"type\":\"speak\",\"videoKey\":\"talking\",\"text\":\"(REAL, COMPLETE {min_sentences_per_scene}-{max_sentences_per_scene} SENTENCES)\"}}]}}
Return JSON only. USE REAL, COMPLETE SENTENCES IN ALL SCENES.
"""

    # OpenAI (primary)
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            print("⚠️ [story_composer] OPENAI_API_KEY not found, using fallback")
        else:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=openai_key)
            
            # Select prompt based on language
            if lang.startswith("tr"):
                prompt = tr_prompt
                topic_hint = topic_hint_tr
            elif lang.startswith("de"):
                # Use English prompt structure but fix language instruction
                prompt = en_prompt.replace(topic_hint_en, topic_hint_de)
                prompt = prompt.replace("Language: English", "Language: German")
                prompt = prompt.replace('"language":"en"', '"language":"de"')
                topic_hint = topic_hint_de
            elif lang.startswith("es"):
                # Use English prompt structure but fix language instruction
                prompt = en_prompt.replace(topic_hint_en, topic_hint_es)
                prompt = prompt.replace("Language: English", "Language: Spanish")
                prompt = prompt.replace('"language":"en"', '"language":"es"')
                topic_hint = topic_hint_es
            elif lang.startswith("fr"):
                # Use English prompt structure but fix language instruction
                prompt = en_prompt.replace(topic_hint_en, topic_hint_fr)
                prompt = prompt.replace("Language: English", "Language: French")
                prompt = prompt.replace('"language":"en"', '"language":"fr"')
                topic_hint = topic_hint_fr
            else:
                prompt = en_prompt
                topic_hint = topic_hint_en
            
            # Use gpt-4o for longer stories (10+ minutes) to ensure quality and length
            openai_model = os.getenv("OPENAI_STORY_MODEL", "gpt-4o" if minutes >= 10 else "gpt-4o-mini")
            
            print(f"📝 [story_composer] Generating story with {openai_model}...")
            print(f"📊 [story_composer] Target: {min_scenes}-{max_scenes} scenes, {target_words} words, {minutes} minutes")
            
            system_message = f"""You output only strict JSON that matches the requested schema.

CRITICAL REQUIREMENTS - THESE ARE MANDATORY:
1. You MUST create at least {min_scenes} scenes (preferably {min_scenes}-{max_scenes} scenes).
2. Each scene MUST have at least {min_sentences_per_scene} complete sentences (preferably {min_sentences_per_scene}-{max_sentences_per_scene} sentences).
3. Total word count MUST be around {target_words} words (±10% tolerance). This is approximately {minutes} minutes of spoken content.
4. Every scene's "text" field must contain REAL, COMPLETE, FULL sentences - NOT placeholders, NOT short phrases.
5. Each scene text should be 70-120 words long to reach the target word count. Expand sentences with details, examples, and explanations.
6. DO NOT summarize or be brief. BE DETAILED. Every sentence should add value and detail.
7. Think of each scene as a mini-story with context, examples, and explanations.

WORD COUNT CALCULATION:
- Target: {target_words} words total
- With {min_scenes} scenes: each scene needs ~{target_words // min_scenes} words
- With {max_scenes} scenes: each scene needs ~{target_words // max_scenes} words
- Average per scene: {target_words // ((min_scenes + max_scenes) // 2)} words

REJECTION CRITERIA:
- Stories with less than {target_words * 0.7} words will be REJECTED.
- Stories with less than {min_scenes} scenes will be REJECTED.
- Scenes with less than {min_sentences_per_scene} sentences will be REJECTED.
- Scenes with less than 70 words will be REJECTED.

CRITICAL FORMAT REQUIREMENT:
- This is a MONOLOGUE phone call: Only the character speaks. The child listens but does not respond.
- NO DIALOGUE: There is no conversation between two people. Only the character's monologue speech.
- Character speaks as if having a phone conversation with the child, telling a story, asking rhetorical questions, and continuing the narrative alone.

You are generating a {minutes}-minute MONOLOGUE phone call script. This requires substantial content. Do NOT create short stories. BE DETAILED AND EXPANSIVE."""
            
            resp = client.chat.completions.create(
                model=openai_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,  # Lower temperature for more consistent, detailed output
                max_tokens=12000,  # Increased for longer, more detailed stories (10 minutes = ~1300 words)
            )
            text = resp.choices[0].message.content.strip()
            text = re.sub(r"^```json\s*|^```|```$", "", text).strip()
            
            print(f"📄 [story_composer] Received response ({len(text)} chars)")
            
            data = json.loads(text)
            data.setdefault("durationMinutes", minutes)
            # Ensure language field is correct
            data["language"] = lang if len(lang) == 2 else lang[:2]
            # CRITICAL: Override topic field with the mapped topic (not LLM's response)
            # This ensures consistency: story file name and JSON topic field match
            # Example: If topic="sibling", topic_mapped="sibling", then story JSON should have topic="sibling"
            # This prevents issues where LLM returns "friendship" but we want "sibling"
            data["topic"] = topic
            print(f"✅ [story_composer] Set story topic field to '{topic}' (mapped topic, ensuring consistency with file name)")
            # Ensure title field exists
            if "title" not in data or not data.get("title"):
                # Generate default title
                char_display = character.replace('_', ' ').title()
                topic_display = topic.replace('_', ' ').title()
                if lang.startswith("tr"):
                    data["title"] = f"{char_display}'ın {topic_display} Hikayesi"
                elif lang.startswith("de"):
                    data["title"] = f"{char_display}s {topic_display} Geschichte"
                elif lang.startswith("es"):
                    data["title"] = f"Historia de {topic_display} de {char_display}"
                elif lang.startswith("fr"):
                    data["title"] = f"Histoire de {topic_display} de {char_display}"
                else:
                    data["title"] = f"{char_display}'s {topic_display} Story"
            
            # Validate story length
            scenes_count = len(data.get("scenes", []))
            if scenes_count < min_scenes:
                print(f"⚠️ [story_composer] Warning: Story has only {scenes_count} scenes, expected at least {min_scenes}")
            
            # Count total words
            total_words = sum(len(scene.get("text", "").split()) for scene in data.get("scenes", []))
            print(f"📊 [story_composer] Generated: {scenes_count} scenes, ~{total_words} words")
            
            if scenes_count < min_scenes or total_words < target_words * 0.5:
                print(f"⚠️ [story_composer] Story is too short! Expected: {min_scenes}+ scenes, {target_words} words. Got: {scenes_count} scenes, {total_words} words")
                print(f"⚠️ [story_composer] This might indicate the model didn't follow instructions properly.")
            
            # BEST PRACTICE: Post-process scenes to optimize videoKey based on text content
            # This ensures more natural and contextually appropriate animations
            print(f"🎬 [story_composer] Optimizing videoKey assignments based on text content...")
            optimized_count = 0
            for scene in data.get("scenes", []):
                scene_type = scene.get("type", "")
                scene_text = scene.get("text", "")
                original_video_key = scene.get("videoKey", "")
                
                # Analyze text content to determine best videoKey
                optimized_video_key = analyze_text_for_video_key(scene_type, scene_text, lang)
                
                # Only update if different (avoid unnecessary changes)
                if original_video_key != optimized_video_key:
                    scene["videoKey"] = optimized_video_key
                    optimized_count += 1
                    print(f"   Scene {scene.get('id', 'unknown')}: '{original_video_key}' → '{optimized_video_key}' (type: {scene_type})")
            
            if optimized_count > 0:
                print(f"✅ [story_composer] Optimized {optimized_count} scene videoKey assignments based on text content")
            else:
                print(f"ℹ️ [story_composer] All videoKey assignments are already optimal")
            
            # Save prompt to JSON file after system_message is created
            try:
                slug = to_character_slug(character)
                prompt_path = content_prompt_path(lang, slug, topic)
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create JSON structure for prompt
                prompt_data = {
                    "character": character,
                    "topic": topic,
                    "language": lang,
                    "duration_minutes": minutes,
                    "target_words": target_words,
                    "min_scenes": min_scenes,
                    "max_scenes": max_scenes,
                    "min_sentences_per_scene": min_sentences_per_scene,
                    "max_sentences_per_scene": max_sentences_per_scene,
                    "character_personality": char_personality,
                    "topic_hint": topic_hint,
                    "prompt": prompt,
                    "system_message": system_message
                }
                
                with open(prompt_path, "w", encoding="utf-8") as f:
                    json.dump(prompt_data, f, ensure_ascii=False, indent=2)
                print(f"💾 [story_composer] Saved prompt JSON to: {prompt_path}")
            except Exception as e:
                print(f"⚠️ [story_composer] Failed to save prompt: {e}")
                import traceback
                traceback.print_exc()
            
            return data
    except json.JSONDecodeError as e:
        print(f"❌ [story_composer] JSON decode error: {e}")
        print(f"📄 [story_composer] Response text (first 500 chars): {text[:500] if 'text' in locals() else 'N/A'}")
    except Exception as e:
        print(f"❌ [story_composer] OpenAI failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to save prompt even if generation failed (for debugging)
        try:
            slug = to_character_slug(character)
            prompt_path = content_prompt_path(lang, slug, topic)
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Determine topic_hint based on language
            if lang.startswith("tr"):
                topic_hint = topic_hint_tr
            elif lang.startswith("de"):
                topic_hint = topic_hint_de
            elif lang.startswith("es"):
                topic_hint = topic_hint_es
            elif lang.startswith("fr"):
                topic_hint = topic_hint_fr
            else:
                topic_hint = topic_hint_en
            
            prompt_data = {
                "character": character,
                "topic": topic,
                "language": lang,
                "duration_minutes": minutes,
                "target_words": target_words,
                "min_scenes": min_scenes,
                "max_scenes": max_scenes,
                "min_sentences_per_scene": min_sentences_per_scene,
                "max_sentences_per_scene": max_sentences_per_scene,
                "character_personality": char_personality,
                "topic_hint": topic_hint,
                "error": str(e),
                "note": "This is a fallback story - OpenAI generation failed. Regenerate when API is available."
            }
            
            with open(prompt_path, "w", encoding="utf-8") as f:
                json.dump(prompt_data, f, ensure_ascii=False, indent=2)
            print(f"💾 [story_composer] Saved error info to prompt JSON: {prompt_path}")
        except Exception as save_error:
            print(f"⚠️ [story_composer] Failed to save error info: {save_error}")

    # Minimal safe fallback
    # Determine language code properly
    if lang.startswith("tr"):
        lang_code = "tr"
        opening = f"Merhaba, ben {character}! {topic} hakkında kısa bir macera ister misin?"
        question = "Bugün seni en çok ne mutlu etti?"
        closing = "Harikaydı! Görüşmek üzere, iyi oyunlar!"
        title = f"{character}'ın {topic.replace('_', ' ').title()} Hikayesi"
    elif lang.startswith("de"):
        lang_code = "de"
        opening = f"Hallo, ich bin {character}! Bist du bereit für ein kurzes {topic} Abenteuer?"
        question = "Was hat dich heute am glücklichsten gemacht?"
        closing = "Das war großartig! Bis bald!"
        title = f"{character}s {topic.replace('_', ' ').title()} Geschichte"
    elif lang.startswith("es"):
        lang_code = "es"
        opening = f"¡Hola, soy {character}! ¿Listo para una pequeña aventura de {topic}?"
        question = "¿Qué te hizo más feliz hoy?"
        closing = "¡Eso fue genial! ¡Hasta pronto!"
        title = f"Historia de {topic.replace('_', ' ').title()} de {character}"
    elif lang.startswith("fr"):
        lang_code = "fr"
        opening = f"Bonjour, je suis {character}! Prêt pour une petite aventure de {topic}?"
        question = "Qu'est-ce qui t'a rendu le plus heureux aujourd'hui?"
        closing = "C'était génial! À bientôt!"
        title = f"Histoire de {topic.replace('_', ' ').title()} de {character}"
    else:
        lang_code = "en"
        opening = f"Hi, I'm {character}! Ready for a short {topic} adventure?"
        question = "What made you happiest today?"
        closing = "That was great! See you soon!"
        title = f"{character}'s {topic.replace('_', ' ').title()} Story"
    
    data = {
        "id": f"{character.lower()}_{topic.lower()}_story",
        "title": title,
        "character": character,
        "topic": topic,
        "language": lang_code,
        "age_range": "2-8",
        "durationMinutes": minutes,
        "emotions": ["happy"],
        "scenes": [
            {"id": "opening_0", "type": "opening", "videoKey": "wave", "text": opening},
            {"id": "question_1", "type": "question", "videoKey": "lean_closer", "text": question},
            {"id": "narration_2", "type": "speak", "videoKey": "talking", "text": opening},
            {"id": "closing_3", "type": "closure", "videoKey": "wave", "text": closing}
        ]
    }
    return data


