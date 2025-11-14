"""Notification message templates for parent push notifications.

COPPA-compliant: Messages are sent to parents only, not children.
Messages are topic-based and include activity suggestions.
"""

from typing import Dict, Optional


# Topic mapping: UI topic names to notification topic keys
TOPIC_MAPPING = {
    "sleep": "bedtime",
    "bedtime": "bedtime",
    "sibling issues": "sibling_issues",
    "sibling_issues": "sibling_issues",
    "screen time": "screen_time",
    "screen_time": "screen_time",
    "digital safety": "digital_safety",
    "digital_safety": "digital_safety",
    "feeling sad": "feeling_sad",
    "feeling_sad": "feeling_sad",
    "emotional regulation": "emotional_regulation",
    "emotional_regulation": "emotional_regulation",
    "behavior attention": "behavior_attention",
    "behavior_attention": "behavior_attention",
    "body parts": "body_parts",
    "body_parts": "body_parts",
    "fairy tales": "fairy_tales",
    "fairy_tales": "fairy_tales",
    "sharing": "sharing",
    "patience": "patience",
    "emotions": "emotions",
    "friendship": "friendship",
    "kindness": "kindness",
    "honesty": "honesty",
    "respect": "respect",
    "colors": "colors",
}


def get_badge_unlocked_message(
    badge_name: str,
    badge_icon: str,
    language: str = "en",
    child_name: Optional[str] = None
) -> Dict[str, str]:
    """Get notification message for badge unlock.
    
    Args:
        badge_name: Badge display name
        badge_icon: Badge icon emoji
        language: Language code
        child_name: Optional child name
        
    Returns:
        Dict with 'title' and 'body' keys
    """
    templates = NOTIFICATION_TEMPLATES.get(language, NOTIFICATION_TEMPLATES["en"])
    badge_template = templates.get("badge_unlocked", {})
    
    name = child_name or "your child"
    
    title = badge_template.get("title", "").format(
        badge_icon=badge_icon,
        badge_name=badge_name
    )
    body = badge_template.get("body", "").format(
        badge_icon=badge_icon,
        badge_name=badge_name,
        name=name
    )
    
    return {"title": title, "body": body}


def get_streak_milestone_message(
    streak_days: int,
    language: str = "en",
    child_name: Optional[str] = None
) -> Dict[str, str]:
    """Get notification message for streak milestone.
    
    Args:
        streak_days: Current streak days
        language: Language code
        child_name: Optional child name
        
    Returns:
        Dict with 'title' and 'body' keys
    """
    templates = NOTIFICATION_TEMPLATES.get(language, NOTIFICATION_TEMPLATES["en"])
    streak_template = templates.get("streak_milestone", {})
    
    name = child_name or "your child"
    
    title = streak_template.get("title", "").format(streak_days=streak_days)
    body = streak_template.get("body", "").format(
        streak_days=streak_days,
        name=name
    )
    
    return {"title": title, "body": body}


def get_notification_message(
    character: str,
    topic: str,
    language: str = "en",
    child_name: Optional[str] = None
) -> Dict[str, str]:
    """Get notification message and activity tip for a story completion.
    
    Args:
        character: Character name (e.g., "Luna", "Mino")
        topic: Story topic (e.g., "sharing", "bedtime")
        language: Language code (en, tr, fr, de, es)
        child_name: Optional child name for personalization
        
    Returns:
        Dict with 'title', 'body', and 'activity_tip' keys
    """
    # Normalize topic
    topic_key = TOPIC_MAPPING.get(topic.lower(), topic.lower().replace(" ", "_"))
    
    # Get templates for language
    templates = NOTIFICATION_TEMPLATES.get(language, NOTIFICATION_TEMPLATES["en"])
    
    # Get topic-specific template or use default
    topic_template = templates.get(topic_key, templates.get("default", {}))
    
    # Use child name if provided, otherwise use generic
    name = child_name or "your child"
    
    # Format message
    title = topic_template.get("title", "").format(character=character, name=name)
    body = topic_template.get("body", "").format(character=character, name=name, topic=topic)
    activity_tip = topic_template.get("activity_tip", "")
    
    return {
        "title": title,
        "body": body,
        "activity_tip": activity_tip
    }


# Notification templates by language
NOTIFICATION_TEMPLATES = {
    "en": {
        "sharing": {
            "title": "{character} shared a story about sharing",
            "body": "{name} listened to {character}'s story about sharing today. Try playing 'whose turn is it?' together tonight!",
            "activity_tip": "Play a sharing game: take turns choosing activities or toys"
        },
        "patience": {
            "title": "{character} taught about patience",
            "body": "{name} learned about patience from {character} today. Practice waiting together with a simple patience game!",
            "activity_tip": "Practice patience: count to 10 together before doing something fun"
        },
        "emotions": {
            "title": "{character} explored emotions",
            "body": "{name} explored different emotions with {character} today. Talk about feelings together this evening!",
            "activity_tip": "Emotion check-in: ask how they're feeling and share your own feelings"
        },
        "bedtime": {
            "title": "{character} told a bedtime story",
            "body": "{name} listened to {character}'s bedtime story. Try a calming breathing exercise together before sleep!",
            "activity_tip": "Calm breathing: take 3 deep breaths together, counting slowly"
        },
        "sibling_issues": {
            "title": "{character} shared about siblings",
            "body": "{name} heard {character}'s story about getting along with siblings. Try a cooperative activity together!",
            "activity_tip": "Sibling bonding: do a puzzle or craft project together"
        },
        "screen_time": {
            "title": "{character} talked about screen time",
            "body": "{name} learned about healthy screen time from {character}. Plan a screen-free activity together!",
            "activity_tip": "Screen-free time: go for a walk, read a book, or play a board game"
        },
        "digital_safety": {
            "title": "{character} taught digital safety",
            "body": "{name} learned about staying safe online with {character}. Discuss internet safety together!",
            "activity_tip": "Safety chat: talk about what to do if they see something strange online"
        },
        "feeling_sad": {
            "title": "{character} helped with sadness",
            "body": "{name} listened to {character}'s story about feeling sad. Offer comfort and talk about emotions together.",
            "activity_tip": "Emotional support: ask what made them sad and offer a hug"
        },
        "emotional_regulation": {
            "title": "{character} taught emotional control",
            "body": "{name} learned about managing emotions with {character} today. Practice calming techniques together!",
            "activity_tip": "Calm down technique: try the 'turtle technique' - stop, breathe, think"
        },
        "behavior_attention": {
            "title": "{character} discussed attention",
            "body": "{name} heard {character}'s story about paying attention. Practice focus together with a fun activity!",
            "activity_tip": "Focus practice: play 'I spy' or do a short puzzle together"
        },
        "friendship": {
            "title": "{character} shared about friendship",
            "body": "{name} learned about being a good friend from {character}. Talk about friendship together!",
            "activity_tip": "Friendship chat: ask about their friends and what makes a good friend"
        },
        "kindness": {
            "title": "{character} taught kindness",
            "body": "{name} heard {character}'s story about kindness today. Do a kind act together!",
            "activity_tip": "Kindness act: help someone together or write a kind note"
        },
        "default": {
            "title": "{character} shared a story",
            "body": "{name} listened to {character}'s story about {topic} today. Talk about it together this evening!",
            "activity_tip": "Discussion time: ask what they learned from the story"
        },
        "badge_unlocked": {
            "title": "New Badge Unlocked! {badge_icon}",
            "body": "Congratulations! {name} earned the {badge_name} badge {badge_icon} Keep up the great work!"
        },
        "streak_milestone": {
            "title": "Amazing Streak! 🌟",
            "body": "Wow! {name} has been active for {streak_days} days in a row! Keep the momentum going! 🎉"
        }
    },
    "tr": {
        "sharing": {
            "title": "{character} paylaşma hikayesi anlattı",
            "body": "{name} bugün {character}'in paylaşma hikayesini dinledi. Bu akşam birlikte 'sıra kimde?' oyunu oynayabilirsiniz!",
            "activity_tip": "Paylaşma oyunu: sırayla aktivite veya oyuncak seçin"
        },
        "patience": {
            "title": "{character} sabır hakkında öğretti",
            "body": "{name} bugün {character}'den sabır hakkında öğrendi. Birlikte basit bir sabır oyunu oynayın!",
            "activity_tip": "Sabır pratiği: eğlenceli bir şey yapmadan önce birlikte 10'a kadar sayın"
        },
        "emotions": {
            "title": "{character} duyguları keşfetti",
            "body": "{name} bugün {character} ile farklı duyguları keşfetti. Bu akşam birlikte duygular hakkında konuşun!",
            "activity_tip": "Duygu kontrolü: nasıl hissettiklerini sorun ve kendi duygularınızı paylaşın"
        },
        "bedtime": {
            "title": "{character} uyku hikayesi anlattı",
            "body": "{name} {character}'in uyku hikayesini dinledi. Uyumadan önce birlikte sakin bir nefes egzersizi deneyin!",
            "activity_tip": "Sakin nefes: birlikte yavaşça sayarak 3 derin nefes alın"
        },
        "sibling_issues": {
            "title": "{character} kardeşler hakkında anlattı",
            "body": "{name} {character}'in kardeşlerle geçinme hikayesini dinledi. Birlikte işbirlikçi bir aktivite deneyin!",
            "activity_tip": "Kardeş bağı: birlikte bir puzzle veya el işi yapın"
        },
        "screen_time": {
            "title": "{character} ekran süresi hakkında konuştu",
            "body": "{name} {character}'den sağlıklı ekran süresi hakkında öğrendi. Birlikte ekransız bir aktivite planlayın!",
            "activity_tip": "Ekransız zaman: yürüyüşe çıkın, kitap okuyun veya masa oyunu oynayın"
        },
        "digital_safety": {
            "title": "{character} dijital güvenlik öğretti",
            "body": "{name} {character} ile internette güvende kalma hakkında öğrendi. Birlikte internet güvenliği hakkında konuşun!",
            "activity_tip": "Güvenlik sohbeti: online'da garip bir şey görürlerse ne yapmaları gerektiğini konuşun"
        },
        "feeling_sad": {
            "title": "{character} üzüntüyle yardımcı oldu",
            "body": "{name} {character}'in üzüntü hakkındaki hikayesini dinledi. Birlikte rahatlık sunun ve duygular hakkında konuşun.",
            "activity_tip": "Duygusal destek: neyin onları üzdüğünü sorun ve sarılın"
        },
        "emotional_regulation": {
            "title": "{character} duygusal kontrol öğretti",
            "body": "{name} bugün {character} ile duyguları yönetmeyi öğrendi. Birlikte sakinleştirici teknikler deneyin!",
            "activity_tip": "Sakinleşme tekniği: 'kaplumbağa tekniği'ni deneyin - dur, nefes al, düşün"
        },
        "behavior_attention": {
            "title": "{character} dikkat hakkında konuştu",
            "body": "{name} {character}'in dikkat verme hikayesini dinledi. Birlikte eğlenceli bir aktivite ile odaklanma pratiği yapın!",
            "activity_tip": "Odak pratiği: 'gör bakalım' oynayın veya kısa bir puzzle yapın"
        },
        "friendship": {
            "title": "{character} arkadaşlık hakkında anlattı",
            "body": "{name} {character}'den iyi bir arkadaş olmayı öğrendi. Birlikte arkadaşlık hakkında konuşun!",
            "activity_tip": "Arkadaşlık sohbeti: arkadaşları hakkında sorun ve iyi bir arkadaşın ne olduğunu konuşun"
        },
        "kindness": {
            "title": "{character} nezaket öğretti",
            "body": "{name} bugün {character}'in nezaket hikayesini dinledi. Birlikte nazik bir davranış yapın!",
            "activity_tip": "Nezaket eylemi: birlikte birine yardım edin veya nazik bir not yazın"
        },
        "default": {
            "title": "{character} bir hikaye anlattı",
            "body": "{name} bugün {character}'in {topic} hakkındaki hikayesini dinledi. Bu akşam birlikte konuşun!",
            "activity_tip": "Konuşma zamanı: hikayeden ne öğrendiklerini sorun"
        }
    },
    "fr": {
        "sharing": {
            "title": "{character} a raconté une histoire sur le partage",
            "body": "{name} a écouté l'histoire de {character} sur le partage aujourd'hui. Essayez de jouer 'à qui le tour?' ce soir!",
            "activity_tip": "Jeu de partage: à tour de rôle, choisissez des activités ou des jouets"
        },
        "patience": {
            "title": "{character} a enseigné la patience",
            "body": "{name} a appris la patience avec {character} aujourd'hui. Pratiquez l'attente ensemble avec un jeu simple!",
            "activity_tip": "Pratique de la patience: comptez jusqu'à 10 ensemble avant de faire quelque chose d'amusant"
        },
        "emotions": {
            "title": "{character} a exploré les émotions",
            "body": "{name} a exploré différentes émotions avec {character} aujourd'hui. Parlez des sentiments ensemble ce soir!",
            "activity_tip": "Vérification émotionnelle: demandez comment ils se sentent et partagez vos propres sentiments"
        },
        "bedtime": {
            "title": "{character} a raconté une histoire du soir",
            "body": "{name} a écouté l'histoire du soir de {character}. Essayez un exercice de respiration apaisant ensemble avant de dormir!",
            "activity_tip": "Respiration calme: prenez 3 respirations profondes ensemble, en comptant lentement"
        },
        "default": {
            "title": "{character} a raconté une histoire",
            "body": "{name} a écouté l'histoire de {character} sur {topic} aujourd'hui. Parlez-en ensemble ce soir!",
            "activity_tip": "Temps de discussion: demandez ce qu'ils ont appris de l'histoire"
        },
        "badge_unlocked": {
            "title": "Nouveau Badge Débloqué! {badge_icon}",
            "body": "Félicitations! {name} a gagné le badge {badge_name} {badge_icon} Continuez comme ça!"
        },
        "streak_milestone": {
            "title": "Série Impressionnante! 🌟",
            "body": "Wow! {name} est actif depuis {streak_days} jours consécutifs! Continuez comme ça! 🎉"
        }
    },
    "de": {
        "sharing": {
            "title": "{character} hat eine Geschichte über das Teilen erzählt",
            "body": "{name} hat heute {character}s Geschichte über das Teilen gehört. Versuchen Sie heute Abend zusammen 'wer ist dran?' zu spielen!",
            "activity_tip": "Teilspiel: abwechselnd Aktivitäten oder Spielzeug auswählen"
        },
        "patience": {
            "title": "{character} hat Geduld gelehrt",
            "body": "{name} hat heute von {character} Geduld gelernt. Üben Sie das Warten zusammen mit einem einfachen Spiel!",
            "activity_tip": "Geduld üben: zählen Sie zusammen bis 10, bevor Sie etwas Lustiges tun"
        },
        "emotions": {
            "title": "{character} hat Emotionen erkundet",
            "body": "{name} hat heute mit {character} verschiedene Emotionen erkundet. Sprechen Sie heute Abend zusammen über Gefühle!",
            "activity_tip": "Emotionscheck: fragen Sie, wie sie sich fühlen, und teilen Sie Ihre eigenen Gefühle"
        },
        "bedtime": {
            "title": "{character} hat eine Gutenachtgeschichte erzählt",
            "body": "{name} hat {character}s Gutenachtgeschichte gehört. Versuchen Sie zusammen eine beruhigende Atemübung vor dem Schlaf!",
            "activity_tip": "Ruhige Atmung: nehmen Sie zusammen 3 tiefe Atemzüge, langsam zählend"
        },
        "default": {
            "title": "{character} hat eine Geschichte erzählt",
            "body": "{name} hat heute {character}s Geschichte über {topic} gehört. Sprechen Sie heute Abend zusammen darüber!",
            "activity_tip": "Gesprächszeit: fragen Sie, was sie aus der Geschichte gelernt haben"
        },
        "badge_unlocked": {
            "title": "Neues Abzeichen Freigeschaltet! {badge_icon}",
            "body": "Herzlichen Glückwunsch! {name} hat das {badge_name} Abzeichen {badge_icon} verdient. Weiter so!"
        },
        "streak_milestone": {
            "title": "Unglaubliche Serie! 🌟",
            "body": "Wow! {name} ist seit {streak_days} Tagen in Folge aktiv! Behalten Sie den Schwung bei! 🎉"
        }
    },
    "es": {
        "sharing": {
            "title": "{character} contó una historia sobre compartir",
            "body": "{name} escuchó la historia de {character} sobre compartir hoy. ¡Intenten jugar '¿de quién es el turno?' juntos esta noche!",
            "activity_tip": "Juego de compartir: turnen para elegir actividades o juguetes"
        },
        "patience": {
            "title": "{character} enseñó sobre la paciencia",
            "body": "{name} aprendió sobre la paciencia de {character} hoy. ¡Practiquen esperar juntos con un juego simple!",
            "activity_tip": "Práctica de paciencia: cuenten hasta 10 juntos antes de hacer algo divertido"
        },
        "emotions": {
            "title": "{character} exploró emociones",
            "body": "{name} exploró diferentes emociones con {character} hoy. ¡Hablen sobre sentimientos juntos esta noche!",
            "activity_tip": "Revisión emocional: pregunten cómo se sienten y compartan sus propios sentimientos"
        },
        "bedtime": {
            "title": "{character} contó una historia para dormir",
            "body": "{name} escuchó la historia para dormir de {character}. ¡Intenten un ejercicio de respiración calmante juntos antes de dormir!",
            "activity_tip": "Respiración calmante: tomen 3 respiraciones profundas juntos, contando lentamente"
        },
        "default": {
            "title": "{character} contó una historia",
            "body": "{name} escuchó la historia de {character} sobre {topic} hoy. ¡Hablen sobre ello juntos esta noche!",
            "activity_tip": "Tiempo de discusión: pregunten qué aprendieron de la historia"
        },
        "badge_unlocked": {
            "title": "¡Nueva Insignia Desbloqueada! {badge_icon}",
            "body": "¡Felicitaciones! {name} ganó la insignia {badge_name} {badge_icon} ¡Sigan así!"
        },
        "streak_milestone": {
            "title": "¡Serie Increíble! 🌟",
            "body": "¡Wow! {name} ha estado activo durante {streak_days} días seguidos! ¡Mantengan el impulso! 🎉"
        }
    }
}

