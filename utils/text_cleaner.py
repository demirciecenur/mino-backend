"""Text cleaning utilities for TTS."""

import re
from typing import Optional


def clean_text_for_tts(text: str, character: Optional[str] = None) -> str:
    """Clean text for TTS by removing character name prefixes and extra whitespace.
    
    Examples:
        "Mino: Hello!" -> "Hello!"
        "Luna: Hey there!" -> "Hey there!"
        "Mino: Hey there!\n\nMino: You know..." -> "Hey there!\n\nYou know..."
    """
    if not text:
        return text
    
    # List of character names to remove (case-insensitive)
    character_names = [
        "Mino", "Luna", "Tiko", "Bubu", "Sunny", "Koko", "Tom",
        "Bunny", "Elsa", "Jerry", "Ninja Turtles", "Tweety", "Spiderman", "Winnie"
    ]
    
    # If character is specified, prioritize that character name
    if character:
        character_names = [character] + [c for c in character_names if c.lower() != character.lower()]
    
    # Remove character name prefixes (with colon, em dash, or hyphen)
    cleaned_text = text
    for char_name in character_names:
        # Pattern: "CharacterName: " or "CharacterName: " or "CharacterName — " or "CharacterName - "
        patterns = [
            rf"^{re.escape(char_name)}\s*:\s*",  # "Mino: "
            rf"^{re.escape(char_name)}\s*—\s*",  # "Mino — "
            rf"^{re.escape(char_name)}\s*-\s*",  # "Mino - "
        ]
        for pattern in patterns:
            # Remove from start of string and after newlines
            cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE | re.MULTILINE)
    
    # Clean up extra whitespace (multiple spaces, multiple newlines)
    cleaned_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_text)  # Max 2 consecutive newlines
    cleaned_text = re.sub(r" +", " ", cleaned_text)  # Multiple spaces to single space
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text
