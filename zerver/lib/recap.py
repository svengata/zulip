from django.conf import settings
from zerver.models import UserProfile
from zerver.lib.message import get_raw_unread_data, messages_for_ids
from groq import Groq

def get_unread_summary(user_profile: UserProfile) -> str:
    # 1. Fetch unread IDs specifically for channels (streams)
    unread_data = get_raw_unread_data(user_profile)
    unread_ids = list(unread_data["stream_dict"].keys())
    
    if not unread_ids:
        return "You're all caught up! No unread messages to recap."

    # We use empty flags as we only need the text and subject for the summary
    # 2. Get the actual content and metadata
    message_dicts = messages_for_ids(
        message_ids=unread_ids,
        user_message_flags={id: [] for id in unread_ids},
        search_fields={},
        apply_markdown=False,
        client_gravatar=False,
        allow_empty_topic_name=True,
        # Corrected the attribute name below
        message_edit_history_visibility_policy=user_profile.realm.message_edit_history_visibility_policy,
        user_profile=user_profile,
        realm=user_profile.realm,
    )

    # 3. Build the prompt for Groq
    prompt = (
        "Summarize these unread Zulip messages concisely. "
        "For every summary point, you MUST include a clickable reference "
        "using exactly this syntax: #**stream_name>topic_name@message_id**\n\n"
    )
    
    for m in message_dicts:
        prompt += (f"ID: {m['id']} | Sender: {m['sender_full_name']} | "
                   f"Stream: {m['display_recipient']} | Topic: {m['subject']}\n"
                   f"Content: {m['content']}\n\n")

    # 4. Request the completion from Groq
    # We will replace this with a secure secret later!
    client = Groq(api_key=settings.GROQ_API_KEY)
    completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
    )
    
    return completion.choices[0].message.content