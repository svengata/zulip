# Feature Implementation Documentation


Feature 1: AI-Powered Unread Recap
Technical Description
The "Recap" feature provides users with an AI-generated summary of their unread messages, complete with clickable navigation links. This was implemented by creating a full-stack pipeline from a new Python API endpoint to a custom UI element in the Zulip sidebar.

Key Implementation Files:
Backend Logic (zerver/lib/recap.py): Contains the core logic to query the database for UserMessage rows where the flag is not 'read'. It extracts message content and sends it to the Groq API.

API Routing (zproject/urls.py): Defines the /json/messages/recap endpoint which maps to the view function.

Sidebar Template (web/templates/left_sidebar.hbs): The manual injection of the "Recap" list item into the "VIEWS" section of the navigation area.

Frontend Controller (web/src/left_sidebar_navigation_area.ts): Handles the click event, manages the asynchronous API call, and renders the result.

Link Creation & Navigation
To create functional links to relevant messages, the backend formats the LLM output using Zulip’s internal navigation syntax: #**stream_name>topic_name@message_id**.

On the frontend, the raw string is processed via markdown.parse_non_message(data.recap).

This specific function "hydrates" the syntax into HTML anchor tags that Zulip's global click handler recognizes, allowing the user to jump directly to the specific message in the chat feed when clicked.

Frontend Integration
The feature was integrated into the UI by adding a new row to the left sidebar. I utilized the existing dialog_widget.launch system to maintain Zulip's native look and feel. By using white-space: pre-wrap in the CSS, I ensured the AI’s bulleted formatting remained readable within the popup.

Latency, Cost, and Scalability (Basic Considerations)
Latency: To keep the UI responsive, the recap is fetched asynchronously. A "Generating..." log is sent to the console immediately so the user knows the request is in progress.

Cost: Costs are minimized by only sending the text of unread messages to the LLM, rather than the entire message history.

Scalability: By using a specialized endpoint (/recap) rather than bundling this with the main inbox load, the feature only consumes resources when explicitly requested by the user.



Feature 2: Topic Title Improver

Overview
The Topic Title Improver feature automatically detects when a Zulip topic conversation has drifted from its original title and suggests a better title using an LLM. The implementation uses a two-phase approach: fast local drift detection gates expensive LLM calls, ensuring low latency and cost efficiency.

Architecture

Backend Components:**

1. **Drift Detection (Phase 1)** - `zerver/lib/topic_drift.py`
   - Fast, local-only heuristic using Jaccard similarity on word sets
   - Compares topic name to recent messages (last 8 messages)
   - Returns boolean `possible_drift` if similarity threshold is breached
   - No external API calls, sub-millisecond execution

2. **LLM Suggestion (Phase 2)** - `zerver/lib/topic_title_llm.py`
   - Only called when Phase 1 detects drift
   - Uses Groq API with `llama-3.1-8b-instant` model (fast, cost-effective)
   - Fetches recent messages from database, builds prompt, calls LLM
   - Returns suggested title or `None` on failure
   - Main entry point: `check_and_suggest_topic_title()` (lines 108-178)

3. **Message Send Integration** - `zerver/actions/message_send.py` (lines 1094-1105)
   - Hooks into `do_send_messages()` after message is saved
   - Queues async event via `queue_event_on_commit()` - non-blocking
   - Only processes stream messages with non-empty topics

4. **Queue Worker** - `zerver/worker/topic_title_improver.py`
   - Processes events asynchronously via RabbitMQ queue
   - Fetches message and stream, validates content hasn't changed
   - Calls `check_and_suggest_topic_title()` which runs both phases
   - Sends server event to frontend if suggestion generated (lines 92-101)

**Frontend Components:**

1. **Event Handler** - `web/src/topic_title_suggestion.ts`
   - `handle_topic_title_suggestion_event()` receives server events
   - `show_topic_title_suggestion_banner()` displays banner above compose box
   - Handles "Rename topic" button click using `message_edit.do_save_inline_topic_edit()`

2. **Event Dispatcher** - `web/src/server_events_dispatch.js` (line 1233-1236)
   - Added case for `topic_title_suggestion` event type
   - Routes events to topic title suggestion handler

3. **Banner Template** - `web/templates/compose_banner/topic_title_suggestion_banner.hbs`
   - Displays suggestion with "Rename topic" and "Dismiss" buttons
   - Uses existing compose banner infrastructure

### Latency, Cost, and Scalability Considerations

**Latency:**
- Message sending is non-blocking: drift check is queued asynchronously (line 1105 in `message_send.py`)
- Phase 1 detection is <1ms (local string operations)
- Phase 2 LLM call is async (2-5 seconds), doesn't block message delivery
- Frontend banner appears when event arrives, typically within 5 seconds

**Cost:**
- LLM only called when drift detected (Phase 1 gate prevents unnecessary calls)
- Uses `llama-3.1-8b-instant` model: fast and cost-effective (~$0.05 per 1M tokens)
- Limits to last 10 messages in prompt to minimize token usage
- 5-second timeout prevents hanging requests

**Scalability:**
- Queue-based architecture: workers can be scaled horizontally
- Non-blocking message send path: doesn't impact core message delivery
- Worker auto-discovers via `@assign_queue` decorator (line 17 in `topic_title_improver.py`)
- Event system handles high message volume efficiently

### Frontend Integration

The frontend receives suggestions via Zulip's event system. When the worker generates a suggestion, it sends a `topic_title_suggestion` event (line 93-101 in `topic_title_improver.py`) to the message sender. The event dispatcher routes it to `handle_topic_title_suggestion_event()` which shows a banner above the compose box. The banner includes the suggested title and action buttons. Clicking "Rename topic" uses the existing `message_edit.do_save_inline_topic_edit()` function to rename the topic, maintaining consistency with Zulip's existing UI patterns.
