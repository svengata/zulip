"""
LLM-based topic title suggestion.

This module provides functionality to suggest better topic titles using
an LLM when topic drift is detected. Only called when drift detection
returns True to minimize cost and latency.
"""

import logging
import re
from typing import TYPE_CHECKING, Any

from django.conf import settings
from groq import Groq

if TYPE_CHECKING:
    from zerver.models import Message, Stream

logger = logging.getLogger(__name__)

# Timeout for LLM requests (in seconds)
LLM_TIMEOUT = 5.0


def suggest_topic_title(topic_name: str, messages: list[dict[str, Any]]) -> str | None:
    """
    Suggest a better topic title using an LLM based on recent messages.
    
    Args:
        topic_name: The current topic title
        messages: List of message dicts with at least 'content' field.
                  Should contain the last 5-10 messages in the topic.
    
    Returns:
        A suggested topic title string, or None if the request fails or times out.
    """
    if not messages:
        return None
    
    # Limit to last 10 messages to keep prompt size reasonable
    recent_messages = messages[-10:]
    
    # Build the prompt
    prompt = (
        "You are analyzing a Zulip topic conversation. The current topic title is: "
        f'"{topic_name}"\n\n'
        "Recent messages in this topic:\n"
    )
    
    for i, msg in enumerate(recent_messages, 1):
        content = msg.get("content", "").strip()
        if content:
            # Truncate very long messages to keep prompt manageable
            if len(content) > 500:
                content = content[:500] + "..."
            prompt += f"{i}. {content}\n\n"
    
    prompt += (
        "Based on the conversation above, propose ONE concise topic title "
        "that better reflects what the discussion is actually about.\n\n"
        "Requirements:\n"
        "- Return ONLY the title text, nothing else\n"
        "- No markdown formatting\n"
        "- No explanations or commentary\n"
        "- Keep it concise (ideally 3-8 words)\n"
        "- Make it descriptive of the actual conversation\n\n"
        "Topic title:"
    )
    
    try:
        # Initialize Groq client
        if not hasattr(settings, "GROQ_API_KEY") or not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not configured, cannot suggest topic title")
            return None
        
        client = Groq(api_key=settings.GROQ_API_KEY)
        
        # Make the API call with timeout
        # Using llama-3.1-8b-instant as it's a current, fast, and cost-effective model
        # Alternative: llama-3.3-70b-versatile (used in recap.py) for better quality but slower
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            timeout=LLM_TIMEOUT,
            max_tokens=50,  # Limit response length
        )
        
        suggested_title = completion.choices[0].message.content.strip()
        
        # Clean up the response - remove any markdown, quotes, or extra formatting
        suggested_title = suggested_title.strip('"\'`')
        # Remove markdown headers if present
        suggested_title = re.sub(r"^#+\s*", "", suggested_title)
        # Remove any trailing punctuation that might have been added
        suggested_title = suggested_title.rstrip(".,;:!?")
        
        # Validate the suggestion is reasonable
        if not suggested_title or len(suggested_title) > 200:
            logger.warning(f"LLM returned invalid topic title: {suggested_title}")
            return None
        
        return suggested_title
        
    except Exception as e:
        # Log the error but don't fail the message send
        logger.warning(f"Failed to get LLM topic title suggestion: {e}", exc_info=True)
        return None


def check_and_suggest_topic_title(
    message: "Message",  # noqa: F821
    stream: "Stream",  # noqa: F821
    recent_message_count: int = 8,
) -> str | None:
    """
    Check for topic drift and suggest a new title if drift is detected.
    
    This is the main entry point that combines drift detection (Phase 1)
    with LLM-based title suggestion (Phase 2). Only calls the LLM if
    drift is detected, keeping costs and latency low.
    
    Args:
        message: The Message object that was just sent
        stream: The Stream object for the message
        recent_message_count: Number of recent messages to fetch for analysis
    
    Returns:
        A suggested topic title string if drift is detected, None otherwise.
        The caller should NOT automatically rename the topic - this is just
        a suggestion that can be presented to users.
    """
    from zerver.lib.topic import messages_for_topic
    from zerver.lib.topic_drift import detect_topic_drift
    
    topic_name = message.topic_name()
    
    # Skip empty topics
    if not topic_name or not topic_name.strip():
        return None
    
    # Fetch recent messages in this topic (excluding the current one)
    recent_messages_qs = (
        messages_for_topic(
            realm_id=stream.realm_id,
            stream_recipient_id=message.recipient_id,
            topic_name=topic_name,
        )
        .exclude(id=message.id)  # Exclude the message we just sent
        .order_by("-id")  # Most recent first
        .values_list("content", flat=True)[:recent_message_count]
    )
    
    recent_messages = list(recent_messages_qs)
    
    # Phase 1: Lightweight drift detection
    possible_drift = detect_topic_drift(
        topic_name=topic_name,
        recent_messages=recent_messages,
        new_message=message.content,
    )
    
    if not possible_drift:
        return None
    
    # Phase 2: LLM-based suggestion (only called if drift detected)
    # Build message dicts for the LLM
    message_dicts = []
    
    # Add recent messages
    for msg_content in reversed(recent_messages):  # Reverse to get chronological order
        if msg_content:
            message_dicts.append({"content": msg_content})
    
    # Add the new message
    message_dicts.append({"content": message.content})
    
    suggested_title = suggest_topic_title(topic_name, message_dicts)
    
    return suggested_title
