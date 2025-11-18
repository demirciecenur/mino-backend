"""
Centralized topic mapping utility for backend.
Maps UI topic names to backend file names (same as iOS TopicMappingManager.swift).

This ensures consistency across iOS app and backend.
"""
from typing import Dict, List


# Topic mapping dictionary: Maps UI topic names to backend file names
# This matches the iOS TopicMappingManager.swift
TOPIC_MAPPING: Dict[str, str] = {
    "sleep": "bedtime",                    # sleep → bedtime.json
    "sibling issues": "sibling_issues",    # sibling issues → sibling_issues.json
    "sibling": "sibling_issues",           # sibling → sibling_issues.json (fallback)
    "screen time": "screen_time",          # screen time → screen_time.json
    "digital safety": "digital_safety",    # digital safety → digital_safety.json
    "feeling sad": "feeling_sad",         # feeling sad → feeling_sad.json
    "emotional regulation": "emotional_regulation",  # emotional regulation → emotional_regulation.json
    "behavior attention": "behavior_attention",      # behavior attention → behavior_attention.json
    "body parts": "body_parts",            # body parts → body_parts.json
    "fairy tales": "fairy_tales",         # fairy tales → fairy_tales.json
    "food": "nutrition",                   # food → nutrition.json (backend file name)
    "health": "nutrition",                 # health → nutrition.json (Beslenme Sağlık & Beden farkındalığı)
    "body": "nutrition",                   # body → nutrition.json (Beslenme Sağlık & Beden farkındalığı)
    "nutrition": "nutrition",              # nutrition → nutrition.json (direct match)
    "transitions_change": "transitions",   # transitions_change → transitions (story ID variant)
    "transitions_attention": "transitions", # transitions_attention → transitions (story ID variant)
}


def map_topic(topic: str) -> str:
    """Map a topic name to its backend file name.
    
    Args:
        topic: Topic name (e.g., "food", "sleep")
        
    Returns:
        Mapped topic name for backend file lookup (e.g., "nutrition", "bedtime")
    """
    topic_lower = topic.lower()
    return TOPIC_MAPPING.get(topic_lower, topic_lower)


def get_topic_candidates(topic: str) -> List[str]:
    """Get topic candidates for file lookup (mapped version first, then original).
    
    Args:
        topic: Topic name (e.g., "food")
        
    Returns:
        List of topic candidates to try (e.g., ["nutrition", "food"])
    """
    topic_lower = topic.lower()
    mapped = map_topic(topic)
    
    if mapped != topic_lower:
        return [mapped, topic_lower]
    return [topic_lower]


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

