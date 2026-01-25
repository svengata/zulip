"""
Lightweight topic drift detection without LLM.

This module provides fast, local-only heuristics to detect when a topic
has drifted from its original title, using only string operations and
simple similarity metrics.
"""

import re
from typing import Sequence


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, remove punctuation, split words."""
    # Convert to lowercase and remove extra whitespace
    text = text.lower().strip()
    # Remove common punctuation but keep word boundaries
    text = re.sub(r"[^\w\s]", " ", text)
    # Split into words and filter out empty strings
    words = [w for w in text.split() if w]
    return " ".join(words)


def calculate_word_overlap(text1: str, text2: str) -> float:
    """
    Calculate word overlap similarity between two texts.
    
    Returns a value between 0.0 (no overlap) and 1.0 (perfect overlap).
    Uses Jaccard similarity on word sets.
    """
    words1 = set(normalize_text(text1).split())
    words2 = set(normalize_text(text2).split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def detect_topic_drift(
    topic_name: str,
    recent_messages: Sequence[str],
    new_message: str,
    *,
    min_similarity_threshold: float = 0.15,
    min_off_topic_messages: int = 2,
) -> bool:
    """
    Detect if a topic has drifted from its title.
    
    Args:
        topic_name: The current topic title
        recent_messages: List of recent message contents in the topic (last N messages)
        new_message: The content of the newly posted message
        min_similarity_threshold: Minimum similarity score to consider a message "on-topic"
        min_off_topic_messages: Minimum number of off-topic messages needed to flag drift
    
    Returns:
        True if drift is detected, False otherwise
    """
    # Skip empty topics
    if not topic_name or not topic_name.strip():
        return False
    
    # Need at least some messages to compare
    if not recent_messages and not new_message:
        return False
    
    # Calculate similarity of new message to topic
    new_message_similarity = calculate_word_overlap(topic_name, new_message)
    
    # If new message is clearly on-topic, no drift
    if new_message_similarity >= min_similarity_threshold:
        return False
    
    # Count how many recent messages are also off-topic
    off_topic_count = 0
    
    # Check recent messages
    for msg in recent_messages:
        if not msg or not msg.strip():
            continue
        similarity = calculate_word_overlap(topic_name, msg)
        if similarity < min_similarity_threshold:
            off_topic_count += 1
    
    # Check new message
    if new_message_similarity < min_similarity_threshold:
        off_topic_count += 1
    
    # Flag drift if we have enough off-topic messages
    return off_topic_count >= min_off_topic_messages
