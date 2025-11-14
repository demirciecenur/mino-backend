#!/usr/bin/env python3
"""
Generic script to generate character videos using FAL.ai.
Bütçe dostu: wan-2.1-text-to-video model ($0.2 per video at 480p)

Usage:
    # Generate legacy actions (default)
    python scripts/generate_character_videos.py --character koko
    python scripts/generate_character_videos.py --character elsa --actions all_legacy
    
    # Generate new scene actions
    python scripts/generate_character_videos.py --character koko --actions all_new
    python scripts/generate_character_videos.py --character mino --actions wave_greeting,talking,storytelling
    
    # Generate all actions (legacy + new scenes)
    python scripts/generate_character_videos.py --character koko --actions all
    
    # Generate specific actions
    python scripts/generate_character_videos.py --character koko --actions idle,speak,wave_greeting,talking
    
    # With custom background
    python scripts/generate_character_videos.py --character mino --actions all_new --background-style "space adventure theme"
"""

import asyncio
import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.video_generator import generate_character_video, generate_all_character_videos

# Load environment variables
load_dotenv()


async def main():
    parser = argparse.ArgumentParser(description='Generate character videos using FAL.ai')
    parser.add_argument('--character', required=True, help='Character name (e.g., koko, elsa)')
    parser.add_argument('--actions', help='Comma-separated list of actions. Special values: "all" (all actions), "all_new" (new scenes only), "all_legacy" (legacy only). Default: all_legacy', 
                       default='all_new')
    parser.add_argument('--profile-image', help='Path to character profile image (optional)')
    parser.add_argument('--reference-image-2', help='Path to second reference image for better character consistency (optional)')
    parser.add_argument('--output-dir', help='Output directory (default: mino/Assets/characters/{character})')
    parser.add_argument('--background-style', help='Background style description (e.g., "ice castle with soft pastel colors", "forest playground", "space adventure theme"). If not provided, uses character-specific default.')
    
    args = parser.parse_args()
    
    character_name = args.character.lower()
    
    # Get project root (backend/scripts/ -> backend/ -> project root)
    project_root = Path(__file__).parent.parent.parent
    
    # Helper function to resolve paths relative to project root
    def resolve_path(path_str: str) -> Path:
        """Resolve path: if relative, assume it's relative to project root"""
        path = Path(path_str)
        if path.is_absolute():
            return path
        # Relative path: resolve from project root
        resolved = project_root / path_str
        if resolved.exists():
            return resolved
        # Try as-is (might be relative to current working directory)
        return path
    
    # Determine profile image path
    if args.profile_image:
        profile_image_path = str(resolve_path(args.profile_image))
        if not Path(profile_image_path).exists():
            print(f"❌ Profile image not found: {args.profile_image}")
            print(f"   Resolved to: {profile_image_path}")
            sys.exit(1)
    else:
        # Default: mino/Assets/characters/{character}/{character}_profile.{ext}
        char_dir = project_root / "mino" / "Assets" / "characters" / character_name
        
        # Try different extensions
        profile_image_path = None
        for ext in ["png", "jpg", "jpeg"]:
            potential_path = char_dir / f"{character_name}_profile.{ext}"
            if potential_path.exists():
                profile_image_path = str(potential_path)
                break
        
        if not profile_image_path:
            print(f"❌ Profile image not found for {character_name}")
            print(f"   Expected: {char_dir}/{character_name}_profile.png/jpg/jpeg")
            print(f"   Or use --profile-image to specify path")
            sys.exit(1)
    
    # Determine reference image 2 path
    reference_image_2_path = None
    if args.reference_image_2:
        reference_image_2_path = str(resolve_path(args.reference_image_2))
        if not Path(reference_image_2_path).exists():
            print(f"❌ Second reference image not found: {args.reference_image_2}")
            print(f"   Resolved to: {reference_image_2_path}")
            sys.exit(1)
    
    # Determine output directory
    if args.output_dir:
        output_dir = resolve_path(args.output_dir)
    else:
        # Default: mino/Assets/characters/{character}
        output_dir = project_root / "mino" / "Assets" / "characters" / character_name
    
    print(f"\n🎬 Character Video Generator (3D Animation from Profile Image)")
    print(f"{'='*60}")
    print(f"Character: {character_name}")
    print(f"Profile Image: {profile_image_path}")
    print(f"Output Directory: {output_dir}")
    print(f"{'='*60}\n")
    
    # Parse actions
    # Available actions:
    # - Legacy: idle, speak, listen, wave
    # - New scenes: wave_greeting, talking, storytelling, raise_hand, hand_on_hip, 
    #               lean_closer, foot_tap, side_glance, wave_goodbye
    # - All new scenes: wave_greeting,talking,storytelling,raise_hand,hand_on_hip,lean_closer,listen,foot_tap,side_glance,wave_goodbye
    # - All legacy: idle,speak,listen,wave
    # - All (both): all
    
    if args.actions.lower() == 'all':
        # Generate all actions (simplified set - only essential actions)
        actions = [
            "wave", "talking", "raise_hand", "hand_on_hip",
            "lean_closer", "side_glance"
        ]
    elif args.actions.lower() == 'all_new':
        # Generate only essential scene actions (simplified set)
        actions = [
            "wave", "talking", "raise_hand", "hand_on_hip",
            "lean_closer", "side_glance"
        ]
    elif args.actions.lower() == 'all_legacy':
        # Generate only legacy actions
        actions = ["idle", "speak", "listen", "wave"]
    else:
        # Parse comma-separated list
        actions = [a.strip() for a in args.actions.split(',')]
    
    # Validate actions (simplified set - only essential actions)
    valid_actions = {
        # Essential scene actions
        "wave", "talking", "raise_hand", "hand_on_hip",
        "lean_closer", "side_glance"
    }
    
    invalid_actions = [a for a in actions if a not in valid_actions]
    if invalid_actions:
        print(f"❌ Invalid actions: {', '.join(invalid_actions)}")
        print(f"   Valid actions: {', '.join(sorted(valid_actions))}")
        print(f"   Special values: 'all' (all actions), 'all_new' (new scenes only), 'all_legacy' (legacy only)")
        sys.exit(1)
    
    print(f"📋 Actions to generate: {', '.join(actions)}")
    print(f"   Total: {len(actions)} videos\n")
    
    # Check if FAL_API_KEY is set
    import os
    if not os.getenv('FAL_API_KEY'):
        print("❌ FAL_API_KEY not found in environment variables")
        print("   Please set FAL_API_KEY in .env file or environment")
        sys.exit(1)
    
    # Generate videos for specified actions
    # For smooth transitions, determine previous and next actions
    # This creates a continuous animated story, not separate disconnected scenes
    results = {}
    for i, action in enumerate(actions):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(actions)}] Generating {character_name}_{action}.mp4...")
        print(f"{'='*60}")
        
        # Determine previous and next actions for smooth transitions
        # Her sahne, bir önceki sahneden devam etmeli ve sonraki sahneye geçiş yapmalı
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
            output_dir=output_dir,
            background_style=args.background_style,
            previous_action=previous_action,
            next_action=next_action
        )
        
        results[action] = video_path
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Generation Summary")
    print(f"{'='*60}")
    
    successful = [action for action, path in results.items() if path]
    failed = [action for action, path in results.items() if not path]
    
    print(f"✅ Successful: {len(successful)}/{len(results)}")
    for action in successful:
        print(f"   - {character_name}_{action}.mp4")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}/{len(results)}")
        for action in failed:
            print(f"   - {character_name}_{action}.mp4")
    
    print(f"\n💡 Videos saved to: {output_dir}")
    # Maliyet tahmini (en ucuz model: Minimax)
    min_cost_per_video = 0.085  # Minimax: ~$0.017/saniye * 5 saniye
    max_cost_per_video = 0.20   # Wan-2.1/Ovi: $0.20
    print(f"💡 Estimated cost: ${len(successful) * min_cost_per_video:.2f}-${len(successful) * max_cost_per_video:.2f}")
    print(f"   (Minimax: ~$0.085/video, Wan-2.1/Ovi: $0.20/video)")
    print(f"💡 Model priority: Minimax (cheapest) → Wan-2.1 → Ovi → SVD")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())

