"""
Centralized topic mapping utility for backend.
Maps UI topic names to backend file names (same as iOS TopicMappingManager.swift).

This ensures consistency across iOS app and backend.
"""
from typing import Dict, List


# Topic mapping dictionary: Maps UI topic names to backend file names
# This matches the iOS TopicMappingManager.swift and TopicCatalog.json
# NOTE: Backend file names are: nutrition_0.wav, sibling_0.wav (not nutrition_health_body, sibling_issues)
# Expanded with keyword-based aliases for better free-form description matching
TOPIC_MAPPING: Dict[str, str] = {
    # Bedtime
    "sleep": "bedtime",
    "bedtime": "bedtime",
    "uyku": "bedtime",
    "uyku vakti": "bedtime",
    "zor uykuya dalıyor": "bedtime",
    "zor uykuya daliyor": "bedtime",
    "uykuya dalamıyor": "bedtime",
    "uykuya dalamiyor": "bedtime",
    
    # Sibling
    "sibling": "sibling",
    "sibling issues": "sibling",
    "sibling_issues": "sibling",
    "siblingissues": "sibling",
    "kardeş": "sibling",
    "kardes": "sibling",
    "kardeşiyle kavga": "sibling",
    "kardesiyle kavga": "sibling",
    "kardeşiyle anlaşamıyor": "sibling",
    "kardesiyle anlasamiyor": "sibling",
    "kardeşiyle paylaşmıyor": "sibling",
    "kardesiyle paylasmiyor": "sibling",
    "kardeşiyle paylaşmak": "sibling",
    "kardesiyle paylasmak": "sibling",
    "kardeşiyle paylaşmak için ikna": "sibling",
    "kardesiyle paylasmak icin ikna": "sibling",
    "kardeşiyle paylaşmak için ikna et": "sibling",
    "kardesiyle paylasmak icin ikna et": "sibling",
    "convince sibling to share": "sibling",
    "persuade sibling to share": "sibling",
    "convince to share with sibling": "sibling",
    "persuade to share with sibling": "sibling",
    "convencer para compartir con hermano": "sibling",
    "convencer para compartir con hermana": "sibling",
    "convencer de compartir con hermano": "sibling",
    "convencer de compartir con hermana": "sibling",
    "persuadir para compartir con hermano": "sibling",
    "persuadir para compartir con hermana": "sibling",
    "überzeugen mit geschwister zu teilen": "sibling",
    "überzeugen mit bruder zu teilen": "sibling",
    "überzeugen mit schwester zu teilen": "sibling",
    "überreden mit geschwister zu teilen": "sibling",
    "überreden mit bruder zu teilen": "sibling",
    "überreden mit schwester zu teilen": "sibling",
    "convaincre de partager avec son frère": "sibling",
    "convaincre de partager avec sa soeur": "sibling",
    "persuader de partager avec son frère": "sibling",
    "persuader de partager avec sa soeur": "sibling",
    
    # Screen Time
    "screen time": "screen_time",
    "screen_time": "screen_time",
    "digital safety": "screen_time",
    "ekran süresi": "screen_time",
    "ekran suresi": "screen_time",
    "çok ekran izliyor": "screen_time",
    "cok ekran izliyor": "screen_time",
    "tabletten ayrılamıyor": "screen_time",
    "tabletten ayrılamiyor": "screen_time",
    
    # Emotional Regulation
    "emotional regulation": "emotional_regulation",
    "emotional_regulation": "emotional_regulation",
    "feeling sad": "emotional_regulation",
    "anxiety": "emotional_regulation",
    "feelings": "emotional_regulation",
    "okul": "emotional_regulation",
    "okula gitmek": "emotional_regulation",
    "okula gitmek istemiyor": "emotional_regulation",
    "okula gitmek istemiyor korkuyor": "emotional_regulation",
    "okula gitmekten korkuyor": "emotional_regulation",
    "okula mutlu gitmek": "emotional_regulation",
    "okula mutlu gitmekle ilgili ikna": "emotional_regulation",
    "okula gitmek için ikna": "emotional_regulation",
    "okula gitmek icin ikna": "emotional_regulation",
    "okula gitmek için ikna et": "emotional_regulation",
    "okula gitmek icin ikna et": "emotional_regulation",
    "okula gitmesi için ikna": "emotional_regulation",
    "okula gitmesi icin ikna": "emotional_regulation",
    "okula gitmesi için ikna et": "emotional_regulation",
    "okula gitmesi icin ikna et": "emotional_regulation",
    "school": "emotional_regulation",
    "school anxiety": "emotional_regulation",
    "afraid of school": "emotional_regulation",
    "convince to go to school": "emotional_regulation",
    "persuade to go to school": "emotional_regulation",
    "no quiere ir a la escuela": "emotional_regulation",
    "convencer para ir al cole": "emotional_regulation",
    "convencer para ir a la escuela": "emotional_regulation",
    "convencer de ir al cole": "emotional_regulation",
    "convencer de ir a la escuela": "emotional_regulation",
    "persuadir para ir al cole": "emotional_regulation",
    "persuadir para ir a la escuela": "emotional_regulation",
    "will nicht zur schule gehen": "emotional_regulation",
    "überzeugen zur schule zu gehen": "emotional_regulation",
    "überzeugen in die schule zu gehen": "emotional_regulation",
    "überreden zur schule zu gehen": "emotional_regulation",
    "überreden in die schule zu gehen": "emotional_regulation",
    "peur d aller à l école": "emotional_regulation",
    "veut pas aller à l école": "emotional_regulation",
    "ne veut pas aller à l école": "emotional_regulation",
    "convaincre d aller à l école": "emotional_regulation",
    "persuader d aller à l école": "emotional_regulation",
    
    # Behavior
    "behavior": "behavior",
    "behavior attention": "behavior",
    "behavior_attention": "behavior",
    "attention": "behavior",
    "adhd": "behavior",
    "inatçı": "behavior",
    "inatci": "behavior",
    "inatlaşıyor": "behavior",
    "inatlasiyor": "behavior",
    "doesn't listen": "behavior",
    "won't listen": "behavior",
    "convince to listen": "behavior",
    "persuade to listen": "behavior",
    # Turkish (TR) - Listen
    "dinlemesi için ikna": "behavior",
    "dinlemesi icin ikna": "behavior",
    "dinlemesi için ikna et": "behavior",
    "dinlemesi icin ikna et": "behavior",
    "dinlemiyor": "behavior",
    # Spanish (ES) - Listen
    "no quiere escuchar": "behavior",
    "convencer para escuchar": "behavior",
    "convencer de escuchar": "behavior",
    "persuadir para escuchar": "behavior",
    # German (DE) - Listen
    "will nicht zuhören": "behavior",
    "hört nicht zu": "behavior",
    "überzeugen zuzuhören": "behavior",
    "überreden zuzuhören": "behavior",
    # French (FR) - Listen
    "ne veut pas écouter": "behavior",
    "n'écoute pas": "behavior",
    "convaincre d écouter": "behavior",
    "persuader d écouter": "behavior",
    "tantrum": "behavior",
    "tantrums": "behavior",
    
    # Friendship
    "friendship": "friendship",
    "sharing": "friendship",
    
    # Kindness
    "kindness": "kindness",
    "kind": "kindness",
    "being kind": "kindness",
    "be kind": "kindness",
    "being kind to siblings": "kindness",
    "be kind to siblings": "kindness",
    "kind to siblings": "kindness",
    "nazik": "kindness",
    "nazik olmak": "kindness",
    "nazik ol": "kindness",
    "kibar": "kindness",
    "kibar olmak": "kindness",
    "kibar ol": "kindness",
    "kardeşine nazik ol": "kindness",
    "kardesine nazik ol": "kindness",
    "kardeşine kibar ol": "kindness",
    "kardesine kibar ol": "kindness",
    # Spanish (ES) - Kindness
    "ser amable": "kindness",
    "ser amable con hermanos": "kindness",
    "ser amable con hermano": "kindness",
    "ser amable con hermana": "kindness",
    "ser bueno": "kindness",
    "ser bueno con hermanos": "kindness",
    "amabilidad": "kindness",
    # German (DE) - Kindness
    "freundlich sein": "kindness",
    "freundlich zu geschwistern": "kindness",
    "freundlich zu bruder": "kindness",
    "freundlich zu schwester": "kindness",
    "freundlichkeit": "kindness",
    "nett sein": "kindness",
    "nettigkeit": "kindness",
    # French (FR) - Kindness
    "être gentil": "kindness",
    "être gentil avec son frère": "kindness",
    "être gentil avec sa soeur": "kindness",
    "être gentil avec ses frères": "kindness",
    "être gentil avec ses soeurs": "kindness",
    "gentillesse": "kindness",
    "compassion": "kindness",
    "empathy": "kindness",
    "manners": "friendship",
    "paylaşmak": "friendship",
    "paylasmak": "friendship",
    "paylaş": "friendship",
    "paylas": "friendship",
    "arkadaşlık": "friendship",
    "arkadaslik": "friendship",
    "arkadaş": "friendship",
    "arkadas": "friendship",
    "oyuncak paylaşmıyor": "friendship",
    "oyuncak paylasmiyor": "friendship",
    "oyuncaklarını paylaşmak istemiyor": "friendship",
    "oyuncaklarini paylasmak istemiyor": "friendship",
    "oyuncakları paylaşmak": "friendship",
    "oyuncaklarini paylasmak": "friendship",
    "oyuncakları paylaşmak için ikna": "friendship",
    "oyuncaklarini paylasmak icin ikna": "friendship",
    "oyuncakları paylaşmak için ikna et": "friendship",
    "oyuncaklarini paylasmak icin ikna et": "friendship",
    "paylaşmak için ikna": "friendship",
    "paylasmak icin ikna": "friendship",
    "paylaşmak için ikna et": "friendship",
    "paylasmak icin ikna et": "friendship",
    "ikna et": "friendship",
    "ikna": "friendship",
    "doesn't share toys": "friendship",
    "share toys": "friendship",
    "sharing toys": "friendship",
    "convince to share toys": "friendship",
    "convince to share": "friendship",
    "persuade to share": "friendship",
    "persuade to share toys": "friendship",
    "convencer para compartir": "friendship",
    "convencer para compartir juguetes": "friendship",
    "convencer de compartir": "friendship",
    "convencer de compartir juguetes": "friendship",
    "persuadir para compartir": "friendship",
    "persuadir para compartir juguetes": "friendship",
    "überzeugen zu teilen": "friendship",
    "überzeugen spielzeuge zu teilen": "friendship",
    "überreden zu teilen": "friendship",
    "überreden spielzeuge zu teilen": "friendship",
    "convaincre de partager": "friendship",
    "convaincre de partager ses jouets": "friendship",
    "persuader de partager": "friendship",
    "persuader de partager ses jouets": "friendship",
    "has no friends": "friendship",
    "making friends": "friendship",
    
    # Confidence
    "confidence": "confidence",
    "independence": "confidence",
    "bravery": "confidence",
    "time": "confidence",
    "cesaret": "confidence",
    "özgüven": "confidence",
    "ozguven": "confidence",
    "kendine güven": "confidence",
    "doktor korkusu": "confidence",
    "dis korkusu": "confidence",
    "diş korkusu": "confidence",
    "afraid of doctor": "confidence",
    "afraid of dentist": "confidence",
    
    # Transitions
    "transitions": "transitions",
    "change": "transitions",
    "transitions_change": "transitions",
    "transitions_attention": "transitions",
    "okula başlama": "transitions",
    "okula baslama": "transitions",
    "okula başlama korkusu": "transitions",
    "okula baslama korkusu": "transitions",
    "okula başlıyor": "transitions",
    "okula basliyor": "transitions",
    "starting school": "transitions",
    "school start": "transitions",
    "first day of school": "transitions",
    "new school": "transitions",
    
    # Imagination
    "imagination": "imagination",
    "creativity": "imagination",
    "play": "imagination",
    "colors": "imagination",
    "rainbow": "imagination",
    "music": "imagination",
    "shapes": "imagination",
    "animals": "imagination",
    "nature": "imagination",
    "space": "imagination",
    "ocean": "imagination",
    "fairy tales": "imagination",
    "fairy_tales": "imagination",
    "oyun": "imagination",
    "hayal gücü": "imagination",
    "hayal": "imagination",
    "can sıkılıyor": "imagination",
    "can sikiliyor": "imagination",
    "sıkılıyor": "imagination",
    "sikiliyor": "imagination",
    "bored": "imagination",
    "bored at home": "imagination",
    
    # Nutrition
    "nutrition": "nutrition",
    "food": "nutrition",
    "health": "nutrition",
    "body": "nutrition",
    "body parts": "nutrition",
    "body_parts": "nutrition",
    "vegetable": "nutrition",
    "vegetables": "nutrition",
    "broccoli": "nutrition",
    "brokoli": "nutrition",
    "sebze": "nutrition",
    "sebzeler": "nutrition",
    "yemek": "nutrition",
    "yemekler": "nutrition",
    "yemek yemiyor": "nutrition",
    "yemek yemesi için ikna et": "nutrition",
    "yemek yemesi icin ikna et": "nutrition",
    "yemek reddediyor": "nutrition",
    "sebze yemiyor": "nutrition",
    "sebze sevmiyor": "nutrition",
    "sebze yemesi için ikna et": "nutrition",
    "sebze yemesi icin ikna et": "nutrition",
    "brokoli sevmiyor": "nutrition",
    "brokoli yemesi için ikna et": "nutrition",
    "brokoli yemesi icin ikna et": "nutrition",
    "won't eat": "nutrition",
    "doesn't eat": "nutrition",
    "refuses to eat": "nutrition",
    "convince to eat": "nutrition",
    "convince to eat vegetables": "nutrition",
    "persuade to eat": "nutrition",
    "persuade to eat vegetables": "nutrition",
    "no quiere comer": "nutrition",
    "no come": "nutrition",
    "convencer para comer": "nutrition",
    "convencer para comer verduras": "nutrition",
    "convencer de comer": "nutrition",
    "convencer de comer verduras": "nutrition",
    "persuadir para comer": "nutrition",
    "persuadir para comer verduras": "nutrition",
    "isst nicht": "nutrition",
    "will nicht essen": "nutrition",
    "überzeugen zu essen": "nutrition",
    "überzeugen gemüse zu essen": "nutrition",
    "überreden zu essen": "nutrition",
    "überreden gemüse zu essen": "nutrition",
    "ne mange pas": "nutrition",
    "refuse de manger": "nutrition",
    "ne veut pas manger": "nutrition",
    "convaincre de manger": "nutrition",
    "convaincre de manger des légumes": "nutrition",
    "persuader de manger": "nutrition",
    "persuader de manger des légumes": "nutrition",
    "iştah": "nutrition",
    "appetite": "nutrition",
    "new food": "nutrition",
    "new foods": "nutrition",
    "pickyeater": "nutrition",
    "picky eater": "nutrition",
    
    # Transitions / Clothing / Getting Dressed
    "transitions": "transitions",
    "clothing": "transitions",
    "getting dressed": "transitions",
    "wearing clothes": "transitions",
    "winter clothing": "transitions",
    "mont": "transitions",
    "mont giymemek": "transitions",
    "mont giymek": "transitions",
    "mont giymesi için ikna": "transitions",
    "mont giymesi icin ikna": "transitions",
    "mont giymesi için ikna et": "transitions",
    "mont giymesi icin ikna et": "transitions",
    "kışın mont giymemek": "transitions",
    "kışın mont giymek": "transitions",
    "kışın mont giymesi için ikna": "transitions",
    "kışın mont giymesi icin ikna": "transitions",
    "kışın mont giymesi için ikna et": "transitions",
    "kışın mont giymesi icin ikna et": "transitions",
    "giymemek": "transitions",
    "giymek": "transitions",
    "giyinmek": "transitions",
    "giyinmemek": "transitions",
    "giyinmesi için ikna": "transitions",
    "giyinmesi icin ikna": "transitions",
    "giyinmesi için ikna et": "transitions",
    "giyinmesi icin ikna et": "transitions",
    "convince to wear": "transitions",
    "convince to get dressed": "transitions",
    "won't wear": "transitions",
    "doesn't want to wear": "transitions",
    "refuses to wear": "transitions",
    "no quiere ponerse": "transitions",
    "no quiere vestirse": "transitions",
    "convencer para vestirse": "transitions",
    "convencer para ponerse": "transitions",
    "will nicht anziehen": "transitions",
    "will sich nicht anziehen": "transitions",
    "überzeugen sich anzuziehen": "transitions",
    "ne veut pas s'habiller": "transitions",
    "ne veut pas mettre": "transitions",
    "convaincre de s'habiller": "transitions",
    "convaincre de mettre": "transitions",
}


def map_topic(topic: str) -> str:
    """Map a topic name to its backend file name.
    
    Supports both exact matching and keyword-based matching for free-form descriptions.
    
    Args:
        topic: Topic name (e.g., "food", "sleep", or free-form description like "Oyuncakları Eda ile paylaşmak için ikna et")
        
    Returns:
        Mapped topic name for backend file lookup (e.g., "nutrition", "bedtime", "friendship")
    """
    import re
    
    topic_lower = topic.lower().strip()
    
    # Step 1: Try exact alias mapping first
    if topic_lower in TOPIC_MAPPING:
        return TOPIC_MAPPING[topic_lower]
    
    # Step 2: Try keyword-based matching (for free-form descriptions)
    # Split description into words and check each word against aliases
    words = re.findall(r'\b\w+\b', topic_lower)  # Extract words (alphanumeric only)
    
    # Check each word against aliases (prioritize longer matches first)
    best_match = None
    best_score = 0
    
    for word in words:
        if len(word) < 3:  # Skip very short words
            continue
        
        # Try exact word match
        if word in TOPIC_MAPPING:
            score = len(word)
            if best_match is None or score > best_score:
                best_match = TOPIC_MAPPING[word]
                best_score = score
                continue
        
        # Try substring matching: check if any alias key is contained in the word or vice versa
        for alias_key, mapped_value in TOPIC_MAPPING.items():
            if len(alias_key) < 3:  # Skip very short aliases
                continue
            
            # Check if alias key is contained in the word (e.g., "paylaş" in "paylaşmak")
            if alias_key in word or word in alias_key:
                score = min(len(word), len(alias_key))
                if best_match is None or score > best_score:
                    best_match = mapped_value
                    best_score = score
    
    # If we found a keyword match, return it
    if best_match:
        return best_match
    
    # Step 3: Try full description substring matching (for phrases like "oyuncak paylaşmak")
    # Check if any alias key is contained in the full description
    for alias_key, mapped_value in TOPIC_MAPPING.items():
        if len(alias_key) >= 4 and alias_key in topic_lower:  # Only check longer aliases
            return mapped_value
    
    # Step 4: Fallback - return original (will be used as-is by backend)
    return topic_lower


def get_topic_candidates(topic: str) -> List[str]:
    """Get topic candidates for file lookup (mapped version first, then original, then reverse mappings).
    
    Args:
        topic: Topic name (e.g., "food")
        
    Returns:
        List of topic candidates to try (e.g., ["nutrition", "food"])
        
    Note: Also includes reverse mappings (e.g., "sibling" → ["sibling", "sibling_issues"])
    """
    topic_lower = topic.lower()
    mapped = map_topic(topic)
    
    candidates = []
    
    # Add mapped version first (if different)
    if mapped != topic_lower:
        candidates.append(mapped)
    
    # Add original
    candidates.append(topic_lower)
    
    # Add reverse mappings: find all keys that map to the mapped value
    # Example: "sibling" → find all keys that map to "sibling" (e.g., "sibling_issues", "sibling issues")
    if mapped in TOPIC_MAPPING.values():
        for key, value in TOPIC_MAPPING.items():
            if value == mapped and key != topic_lower and key not in candidates:
                # Only add underscore variants (not space variants) to avoid confusion
                if '_' in key:
                    candidates.append(key)
    
    return candidates


def has_mapping(topic: str) -> bool:
    """Check if a topic has a mapping.
    
    Args:
        topic: Topic name
        
    Returns:
        True if topic has a mapping, false otherwise
    """
    topic_lower = topic.lower()
    if topic_lower in TOPIC_MAPPING:
        return TOPIC_MAPPING[topic_lower] != topic_lower
    return False

