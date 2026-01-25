import $ from "jquery";

import render_topic_title_suggestion_banner from "../templates/compose_banner/topic_title_suggestion_banner.hbs";

import * as compose_banner from "./compose_banner.ts";
import * as message_edit from "./message_edit.ts";
import * as message_lists from "./message_lists.ts";
import * as message_store from "./message_store.ts";
import * as message_view from "./message_view.ts";
import * as narrow_state from "./narrow_state.ts";

export function show_topic_title_suggestion_banner(
    message_id: number,
    stream_id: number,
    current_topic: string,
    suggested_topic: string,
): void {
    // Remove any existing suggestion banner
    $(`#compose_banners .${CSS.escape(compose_banner.CLASSNAMES.topic_title_suggestion)}`).remove();

    const $banner = $(
        render_topic_title_suggestion_banner({
            message_id,
            suggested_topic,
            banner_type: compose_banner.INFO,
            classname: compose_banner.CLASSNAMES.topic_title_suggestion,
        }),
    );

    // Handle rename button click
    $banner.find(".topic-title-suggestion-rename-button").on("click", function () {
        const $button = $(this);
        const msg_id = Number.parseInt($button.attr("data-message-id")!, 10);
        const new_topic = $button.attr("data-suggested-topic")!;

        // Find the message row
        const message = message_store.get(msg_id);
        if (!message) {
            // Message not found - we can't rename without the message object
            // The user will need to navigate to the message first
            return;
        }

        // Find the row in the current message list
        if (!message_lists.current) {
            // No message list available, navigate to the message
            message_view.narrow_to_message_near(message, "topic_title_suggestion");
            return;
        }

        const $row = message_lists.current.get_row(msg_id);
        if ($row.length === 0) {
            // Row not found in current view, navigate to the message
            message_view.narrow_to_message_near(message, "topic_title_suggestion");
            return;
        }

        // Rename the topic using the existing message_edit function
        message_edit.do_save_inline_topic_edit($row, message, new_topic);

        // Remove the banner after renaming
        $banner.remove();
    });

    // Handle dismiss button click
    $banner.find(".topic-title-suggestion-dismiss-button").on("click", function () {
        $banner.remove();
    });

    // Handle close button (if present)
    $banner.find(".main-view-banner-close-button").on("click", function () {
        $banner.remove();
    });

    compose_banner.append_compose_banner_to_banner_list($banner, $("#compose_banners"));
}

export function handle_topic_title_suggestion_event(event: {
    type: string;
    message_id: number;
    stream_id: number;
    current_topic: string;
    suggested_topic: string;
}): void {
    // Only show banner if we're currently viewing this stream/topic or if it's our recent message
    const current_stream_id = narrow_state.stream_id();
    const current_topic = narrow_state.topic();

    // Show if we're in the same stream/topic, or if we just sent this message
    const should_show =
        (current_stream_id === event.stream_id &&
            current_topic?.toLowerCase() === event.current_topic.toLowerCase()) ||
        message_store.get(event.message_id) !== undefined;

    if (should_show) {
        show_topic_title_suggestion_banner(
            event.message_id,
            event.stream_id,
            event.current_topic,
            event.suggested_topic,
        );
    }
}
