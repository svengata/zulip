# Documented in https://zulip.readthedocs.io/en/latest/subsystems/queuing.html
import logging
from collections.abc import Mapping
from typing import Any

from django.db import transaction
from typing_extensions import override

from zerver.lib.topic_title_llm import check_and_suggest_topic_title
from zerver.models import Message, Stream
from zerver.tornado.django_api import send_event_on_commit
from zerver.worker.base import QueueProcessingWorker, assign_queue

logger = logging.getLogger(__name__)


@assign_queue("topic_title_improver")
class TopicTitleImproverWorker(QueueProcessingWorker):
    """
    Worker that processes topic drift detection and LLM-based title suggestions.
    
    This worker runs asynchronously after messages are sent, checking if topics
    have drifted and suggesting better titles when appropriate. The LLM call
    only happens if drift is detected, keeping costs low.
    """

    @override
    def consume(self, event: Mapping[str, Any]) -> None:
        """
        Process a topic title improvement event.
        
        Args:
            event: Dictionary containing:
                - message_id: ID of the message that was just sent
                - stream_id: ID of the stream
                - realm_id: ID of the realm
                - topic_name: Current topic name
                - message_content: Content of the new message
        """
        message_id = event.get("message_id")
        stream_id = event.get("stream_id")
        realm_id = event.get("realm_id")
        topic_name = event.get("topic_name")
        
        if not all([message_id, stream_id, realm_id, topic_name]):
            logger.warning(
                "Invalid topic_title_improver event: missing required fields",
                extra={"event": event},
            )
            return
        
        with transaction.atomic(savepoint=False):
            try:
                # Fetch the message and stream
                message = Message.objects.select_related("recipient", "sender", "realm").get(
                    id=message_id
                )
                stream = Stream.objects.get(id=stream_id, realm_id=realm_id)
            except (Message.DoesNotExist, Stream.DoesNotExist) as e:
                # Message or stream may have been deleted
                logger.debug(
                    "Message or stream not found for topic title improvement",
                    extra={"message_id": message_id, "stream_id": stream_id, "error": str(e)},
                )
                return
            
            # Verify the message content matches (message may have been edited)
            if message.content != event.get("message_content"):
                logger.debug(
                    "Message content changed, skipping topic title improvement",
                    extra={"message_id": message_id},
                )
                return
            
            # Check for drift and get suggestion
            suggested_title = check_and_suggest_topic_title(
                message=message,
                stream=stream,
                recent_message_count=8,
            )
            
            if suggested_title:
                logger.info(
                    "Topic title suggestion generated",
                    extra={
                        "message_id": message_id,
                        "stream_id": stream_id,
                        "current_topic": topic_name,
                        "suggested_topic": suggested_title,
                    },
                )
                # Send event to notify the sender about the suggestion
                event = {
                    "type": "topic_title_suggestion",
                    "message_id": message_id,
                    "stream_id": stream_id,
                    "current_topic": topic_name,
                    "suggested_topic": suggested_title,
                }
                # Only notify the message sender
                send_event_on_commit(message.realm, event, [message.sender_id])
            else:
                logger.debug(
                    "No topic drift detected or suggestion failed",
                    extra={"message_id": message_id, "topic_name": topic_name},
                )
