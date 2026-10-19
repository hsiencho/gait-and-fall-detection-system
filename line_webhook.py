"""
LINE Webhook receiver and handler service built with Flask.
"""

import sys
from argparse import ArgumentParser
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import config

app = Flask(__name__)

# Validate credentials
if not config.LINE_CHANNEL_SECRET or not config.LINE_CHANNEL_ACCESS_TOKEN:
    print("[Error] LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN must be specified in .env.")
    sys.exit(1)

line_bot_api = LineBotApi(config.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(config.LINE_CHANNEL_SECRET)

led_status = "OFF"


@app.route("/", methods=["GET"])
def get_status():
    """Device or health check endpoint."""
    return f"LED Status: {led_status}"


@app.route("/callback", methods=["POST"])
def callback():
    """LINE webhook event handler."""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """Echo incoming user messages."""
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    print(f"[LINE Webhook] Event from {user_id}: {user_text}")

    reply_text = f"Received: {user_text}"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )


if __name__ == "__main__":
    parser = ArgumentParser(description="LINE Bot Webhook Server")
    parser.add_argument("-p", "--port", type=int, default=1800, help="Port to listen on")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug mode")
    options = parser.parse_args()

    app.run(host="0.0.0.0", port=options.port, debug=options.debug)