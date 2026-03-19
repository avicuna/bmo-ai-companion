"""
BMO Mood Detection System
Implements AI Council recommendations (2026-03-19):
- Primary: Claude function calling (98-99% reliability)
- Fallback: Local sentiment classifier (1-5% of cases)
- Ultimate fallback: Default to "neutral"

UPDATED: Applied AI Council code review fixes (2026-03-19)
"""

from __future__ import annotations
import re
import logging
import threading
from typing import Optional, Tuple
import anthropic

logger = logging.getLogger(__name__)

# BMO's 13 Emotional States (from show analysis)
BMO_MOODS = [
    "neutral",      # Default/calm state
    "excited",      # High energy, enthusiastic
    "happy",        # Cheerful, content
    "playful",      # Mischievous, fun
    "thoughtful",   # Pondering, curious
    "confused",     # Unsure, puzzled
    "sad",          # Down, melancholy
    "worried",      # Anxious, concerned
    "surprised",    # Shocked, amazed
    "sleepy",       # Tired, drowsy
    "singing",      # Musical, performing
    "loving",       # Affectionate, warm
    "determined"    # Focused, resolute
]

# Magic number constants
EXCITED_EXCLAMATION_THRESHOLD = 2
THOUGHTFUL_QUESTION_THRESHOLD = 1
WORRIED_SAD_RATIO = 0.5

# Claude function calling schema
MOOD_FUNCTION_SCHEMA = {
    "name": "respond_as_bmo",
    "description": "Respond to the user with BMO's personality and indicate BMO's emotional state",
    "input_schema": {
        "type": "object",
        "properties": {
            "mood": {
                "type": "string",
                "enum": BMO_MOODS,
                "description": f"BMO's emotional state while responding. Choose from: {', '.join(BMO_MOODS)}"
            },
            "response": {
                "type": "string",
                "description": "BMO's response text to the user"
            }
        },
        "required": ["mood", "response"]
    }
}


class MoodDetector:
    """Detects BMO's mood from responses using function calling + local fallback."""

    def __init__(self, claude_client: anthropic.Anthropic):
        if claude_client is None:
            raise ValueError("claude_client cannot be None")
        self.claude_client = claude_client
        self.fallback_count = 0
        self.total_count = 0
        self._lock = threading.Lock()

    def extract_mood_from_response(self, response: anthropic.types.Message) -> Tuple[Optional[str], str]:
        """
        Extract mood from Claude response.

        Returns:
            (mood, text) tuple where mood is one of BMO_MOODS or None
        """
        with self._lock:
            self.total_count += 1

        mood = None
        text = ""

        try:
            # Primary: Check for function call (tool use blocks are in response.content)
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    if hasattr(block, 'name') and block.name == 'respond_as_bmo':
                        mood = block.input.get('mood')
                        text = block.input.get('response', '')
                        # Validate mood is a string and valid
                        if isinstance(mood, str) and mood in BMO_MOODS:
                            return (mood, text)

            # Extract text from response (optimized with join)
            text = "".join(
                block.text for block in response.content
                if hasattr(block, 'text')
            )

        except (AttributeError, TypeError, KeyError) as e:
            logger.error(f"[MOOD ERROR] Error parsing Claude response: {e}")
            text = ""

        # Fallback: Local sentiment classifier
        mood = self._local_mood_classifier(text)
        if text.strip():  # Only count non-empty fallbacks
            with self._lock:
                self.fallback_count += 1
            logger.info(f"[MOOD FALLBACK] Used local classifier: {mood} "
                       f"({self.fallback_count}/{self.total_count} fallbacks)")

        return (mood, text)

    def _local_mood_classifier(self, text: str) -> str:
        """
        Lightweight local sentiment classifier.

        Per AI Council recommendations:
        - Simple keyword/punctuation analysis
        - Distinguish broad emotional categories
        - Don't try for perfection (just needs to be plausible)

        OPTIMIZED: Uses sets for O(1) lookups, word boundaries for accuracy
        """
        if not text or not text.strip():
            return "neutral"

        text_lower = text.lower()
        words_in_text = set(text_lower.split())
        exclamations = text.count('!')
        questions = text.count('?')

        # Keyword sets (converted to sets for faster lookups, overlaps removed)
        excited_words = {'yay', 'awesome', 'amazing', 'woohoo'}
        happy_words = {'happy', 'good', 'great', 'nice', 'fun', 'hehe'}
        sad_words = {'sad', 'sorry', 'unfortunately', 'ohno'}
        worried_words = {'worry', 'concerned', 'afraid'}
        confused_words = {'confused', 'unsure', 'hmm', 'hmmm'}
        playful_words = {'silly', 'funny', 'game'}
        surprised_words = {'wow', 'whoa', 'really', 'seriously'}
        sleepy_words = {'tired', 'sleepy', 'yawn', 'sleep'}
        loving_words = {'love', 'care', 'friend', 'best', 'treasure'}
        determined_words = {'will', 'must', 'need', 'going'}
        thoughtful_words = {'think', 'wonder', 'consider', 'maybe', 'perhaps'}

        # Excited indicators
        if exclamations >= EXCITED_EXCLAMATION_THRESHOLD or (excited_words & words_in_text):
            return "excited"

        # Happy indicators
        if happy_words & words_in_text:
            return "happy"

        # Sad/worried indicators (weighted approach)
        sad_count = sum(1 for word in sad_words if word in text_lower)
        worried_count = sum(1 for word in worried_words if word in text_lower)

        if sad_count > 0:
            # Worry needs to be significant relative to sadness
            if worried_count > sad_count * WORRIED_SAD_RATIO:
                return "worried"
            return "sad"

        # Check for specific phrases with "oh no" (substring match needed here)
        if 'oh no' in text_lower:
            return "worried"

        # Confused indicators
        if confused_words & words_in_text:
            return "confused"

        # Check for "not sure" or "don't know" (substring patterns)
        if 'not sure' in text_lower or "dont know" in text_lower or "don't know" in text_lower:
            return "confused"

        # Questioning/thoughtful
        if questions >= THOUGHTFUL_QUESTION_THRESHOLD:
            if thoughtful_words & words_in_text:
                return "thoughtful"

        # Playful indicators
        if playful_words & words_in_text:
            return "playful"

        # Check for playful sounds
        if 'tee hee' in text_lower or 'hehehe' in text_lower:
            return "playful"

        # Surprised indicators (single exclamation + surprise word)
        if exclamations == 1 and (surprised_words & words_in_text):
            return "surprised"

        # Sleepy indicators
        if sleepy_words & words_in_text:
            return "sleepy"

        # Singing indicators
        if '♪' in text or '♫' in text or 'la la' in text_lower:
            return "singing"

        # Loving indicators
        if loving_words & words_in_text:
            return "loving"

        # Determined indicators
        if determined_words & words_in_text:
            # Check for phrases like "have to" or "need to"
            if 'have to' in text_lower or 'need to' in text_lower:
                return "determined"
            # Single keywords also count
            if words_in_text & {'must', 'will'}:
                return "determined"

        # Default
        return "neutral"

    def get_fallback_rate(self) -> float:
        """Return percentage of responses using fallback classifier."""
        with self._lock:
            if self.total_count == 0:
                return 0.0
            return (self.fallback_count / self.total_count) * 100


# Convenience function for quick mood detection
def detect_mood(
    response: anthropic.types.Message,
    detector: MoodDetector
) -> Tuple[str, str]:
    """
    Quick mood detection wrapper.

    Args:
        response: Claude API response
        detector: Existing MoodDetector instance (for tracking statistics)

    Returns:
        (mood, text) tuple - mood is always a valid BMO_MOOD (never None)
    """
    mood, text = detector.extract_mood_from_response(response)
    if mood is None or mood not in BMO_MOODS:
        logger.warning(f"[MOOD] Invalid mood '{mood}', defaulting to neutral")
        mood = "neutral"
    return (mood, text)
