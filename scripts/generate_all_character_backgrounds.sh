#!/bin/bash
# Generate videos for all characters with their specific background styles and actions
# Her karakter için özel arka plan stilleri ile tüm action sahnelerini üretir

set -e

cd "$(dirname "$0")/../.." || exit 1
source backend/venv/bin/activate

# Character names and their specific background styles
# Using array of arrays to handle spaces in character names
CHARACTERS=(
    "mino|space adventure theme with twinkling stars, colorful planets in soft pastel hues, cozy space station interior with friendly alien decorations, gentle nebula clouds in purple and blue, warm space lighting, preschool-friendly bright and cheerful cosmic atmosphere"
    "luna|magical dreamy forest with soft moonlit glades, twinkling stars visible through tree branches, cozy mushroom houses with warm glowing windows, pastel purple and blue tones, gentle fairy lights dancing, soft fireflies, preschool-friendly enchanting nighttime wonderland"
    "tiko|playful forest playground with colorful trees, soft green grass, gentle sunlight filtering through leaves creating dappled shadows, friendly woodland creatures visible in background, bright green and yellow tones, natural wooden play elements, preschool-friendly adventurous forest atmosphere"
    "bubu|calm and soothing indoor space with soft pastel walls in lavender and light blue, cozy reading nook with plush cushions and soft blankets, gentle warm lighting from a reading lamp, peaceful atmosphere with soft blue and lavender tones, preschool-friendly comforting and safe environment"
    "sunny|bright and cheerful sunny meadow with colorful wildflowers in yellow, pink, and blue, clear blue sky with fluffy white clouds, warm golden sunlight creating soft shadows, playful butterflies fluttering, vibrant yellow and orange tones, preschool-friendly joyful and energetic atmosphere"
    "koko|forest playground with natural wooden elements, soft earth tones of brown and green, gentle tree canopy overhead providing dappled shade, adventure-themed but safe and cozy, natural rocks and logs, preschool-friendly brave explorer atmosphere with nature elements"
    "elsa|ice castle with soft pastel colors in blue and white, gentle snowflakes falling softly, crystal-like structures with warm glowing lights, magical winter wonderland with blue and white tones, soft ice formations, preschool-friendly enchanting frozen palace atmosphere"
    "elisa the ice fairy|ice castle with soft pastel colors in blue and white, gentle snowflakes falling softly, crystal-like structures with warm glowing lights, magical winter wonderland with blue and white tones, soft ice formations, preschool-friendly enchanting frozen palace atmosphere"
    "spider fighter|city playground with friendly urban elements, soft city skyline in background with colorful buildings, bright and safe urban environment, red and blue tones, friendly street elements, preschool-friendly heroic city adventure atmosphere"
    "yellow buddy|playful laboratory with colorful gadgets in bright yellow and blue, soft bright yellow and blue tones, friendly scientific elements like test tubes and beakers, cheerful and energetic atmosphere, fun science decorations, preschool-friendly fun and educational environment"
    "chirpy birdie|sunny garden with colorful flowers in red, yellow, and pink, soft birdhouse visible in background, gentle breeze moving leaves, warm yellow and green tones, friendly garden elements, preschool-friendly cheerful and nature-filled atmosphere"
    "bubble buddy|underwater playground with soft coral reefs in pink, orange, and purple, friendly sea creatures like fish and starfish in background, gentle ocean currents creating soft movement, bright blue and yellow tones, preschool-friendly aquatic adventure with ocean life"
    "funny bunny|playful meadow with soft grass, colorful flowers in various hues, gentle hills in background, warm earth tones of green and brown, natural outdoor elements, preschool-friendly comedic and playful natural atmosphere"
    "super metal hero|futuristic tech playground with soft glowing elements in blue and orange, friendly robotic decorations, bright metallic colors with warm tones, high-tech but safe environment, preschool-friendly technological adventure with friendly robots"
    "piggy friend|cozy family home interior with soft pastel walls in pink and yellow, friendly family decorations like photos and toys, warm and inviting atmosphere, pink and yellow tones, comfortable furniture, preschool-friendly family environment with homey feel"
    "blu pup|playful home setting with creative toys scattered around, colorful art supplies like crayons and paper, soft family-friendly interior, bright and cheerful tones, creative workspace elements, preschool-friendly creative and imaginative atmosphere"
    "rescue pup crew|adventure base with friendly rescue elements like safety equipment, soft hero-themed decorations, safe and encouraging environment, red and blue tones, rescue-themed props, preschool-friendly heroic and helpful atmosphere"
    "ocean dreamer moa|ocean adventure setting with soft waves in blue and turquoise, friendly sea elements like shells and seaweed, gentle beach scene with sand and water, blue and turquoise tones, ocean-themed decorations, preschool-friendly oceanic and adventurous atmosphere"
    "super jump hero|playful game world with colorful platforms in red, green, and yellow, friendly game elements like coins and power-ups, bright and energetic atmosphere, red and green tones, game-themed decorations, preschool-friendly gaming adventure with fun elements"
    "swamp buddy hero|friendly swamp setting with soft natural elements like water and plants, cozy and warm atmosphere despite swamp theme, green and brown tones, natural swamp decorations made friendly, preschool-friendly natural environment with adventure feel"
    "boots knight pal|medieval adventure setting with soft castle elements in brown and gray, friendly knight decorations like shields and banners, warm and brave atmosphere, brown and gold tones, chivalrous-themed props, preschool-friendly chivalrous and brave environment"
    "frost friend sid|ice age playground with soft snow elements in white and blue, friendly prehistoric decorations like ice formations, cool but warm atmosphere, blue and white tones, prehistoric-themed but friendly elements, preschool-friendly prehistoric adventure with ice age feel"
    "adventure dora pal|exploration setting with soft map elements visible, friendly adventure decorations like compass and backpack, warm and curious atmosphere, orange and purple tones, exploration-themed props, preschool-friendly exploration and discovery theme"
    "snowman buddy olaf-style|winter wonderland with soft snow in white and light blue, friendly winter elements like snowflakes and icicles, warm and cozy atmosphere despite cold theme, white and blue tones, winter-themed decorations, preschool-friendly winter adventure with warm feeling"
    "spark buddy|electric playground with soft energy elements in yellow and orange, friendly electric decorations like lightning bolts, bright and energetic atmosphere, yellow and orange tones, electric-themed props, preschool-friendly electric adventure with sparkly elements"
    "mystery pup buddy|mystery setting with soft detective elements like magnifying glass, friendly mystery decorations, warm and curious atmosphere, purple and brown tones, detective-themed props, preschool-friendly mystery adventure with puzzle-solving feel"
    "sneaky cat tom|playful home setting with soft furniture in gray and brown, friendly home decorations, warm and mischievous atmosphere, gray and brown tones, home-themed props, preschool-friendly home adventure with playful mischief"
    "clever mouse jerry|cozy small space with soft miniature elements, friendly small decorations, warm and clever atmosphere, brown and beige tones, miniature-themed props, preschool-friendly miniature adventure with clever solutions"
    "shell heroes crew|urban adventure setting with soft city elements, friendly urban decorations, bright and team-oriented atmosphere, green and orange tones, team-themed props, preschool-friendly team adventure with cooperation feel"
)

# Parse arguments
ACTIONS="all_new"  # Default: generate all new scene actions
SPECIFIC_CHARACTER=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --actions)
            ACTIONS="$2"
            shift 2
            ;;
        --character)
            SPECIFIC_CHARACTER="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--actions ACTIONS] [--character CHARACTER] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --actions ACTIONS     Actions to generate (default: all_new)"
            echo "                       Options: all_new, all_legacy, all, or comma-separated list"
            echo "                       Example: wave_greeting,talking,storytelling"
            echo "  --character CHARACTER Generate videos for specific character only"
            echo "  --dry-run             Show commands without executing"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Generate all_new actions for all characters"
            echo "  $0 --character luna                  # Generate all_new actions for Luna only"
            echo "  $0 --actions all --character mino    # Generate all actions for Mino"
            echo "  $0 --actions wave_greeting,talking --character luna  # Generate specific actions"
            echo "  $0 --dry-run                          # Show commands without executing"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "🎬 Character Video Generation with Custom Backgrounds"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Actions: $ACTIONS"
if [ -n "$SPECIFIC_CHARACTER" ]; then
    echo "Character: $SPECIFIC_CHARACTER (only)"
else
    echo "Characters: All (${#CHARACTERS[@]} characters)"
fi
if [ "$DRY_RUN" = true ]; then
    echo "Mode: DRY RUN (commands will be shown but not executed)"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if FAL_API_KEY is set
if [ -z "$FAL_API_KEY" ]; then
    echo "⚠️  FAL_API_KEY not found in environment"
    echo "   Make sure to set it in .env file or export it"
    if [ "$DRY_RUN" = false ]; then
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

TOTAL=0
SUCCESS=0
FAILED=0

# Generate videos for each character
for char_entry in "${CHARACTERS[@]}"; do
    # Split character name and background using pipe separator
    IFS='|' read -r character background <<< "$char_entry"
    
    # Skip if specific character is requested and doesn't match
    if [ -n "$SPECIFIC_CHARACTER" ] && [ "$character" != "$SPECIFIC_CHARACTER" ]; then
        continue
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎬 Generating videos for: $character"
    echo "📋 Actions: $ACTIONS"
    echo "🎨 Background: ${background:0:100}..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Build command with proper quoting
    CMD="python backend/scripts/generate_character_videos.py --character \"$character\" --actions \"$ACTIONS\" --background-style \"$background\""
    
    if [ "$DRY_RUN" = true ]; then
        echo "Command: $CMD"
        echo ""
    else
        TOTAL=$((TOTAL + 1))
        if eval "$CMD" 2>&1 | tee "/tmp/video_gen_${character// /_}.log" | tail -20 | grep -q "✅.*Success\|📊 Generation Summary"; then
            SUCCESS=$((SUCCESS + 1))
            echo "✅ Successfully generated videos for $character"
        else
            FAILED=$((FAILED + 1))
            echo "❌ Failed to generate videos for $character"
            echo "   Check log: /tmp/video_gen_${character// /_}.log"
        fi
        
        # Small delay to avoid rate limiting
        sleep 3
    fi
    echo ""
done

if [ "$DRY_RUN" = false ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Summary:"
    echo "   ✅ Success: $SUCCESS"
    echo "   ❌ Failed: $FAILED"
    echo "   📝 Total: $TOTAL"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi
