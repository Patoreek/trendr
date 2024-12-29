from flask import Flask, jsonify, request

app = Flask(__name__)

# Bot status (can be updated based on actual functionality later)
bot_status = {"running": False}


@app.route("/")
def home():
    return jsonify({"message": "Trend Following Bot is ready!"})


@app.route("/start", methods=["POST"])
def start_bot():
    if bot_status["running"]:
        return jsonify({"message": "Bot is already running!"}), 400
    bot_status["running"] = True
    print("Bot started!")  # Log for debugging
    return jsonify({"message": "Bot started successfully!"})


@app.route("/stop", methods=["POST"])
def stop_bot():
    if not bot_status["running"]:
        return jsonify({"message": "Bot is not running!"}), 400
    bot_status["running"] = False
    print("Bot stopped!")  # Log for debugging
    return jsonify({"message": "Bot stopped successfully!"})


@app.route("/status", methods=["GET"])
def status_bot():
    status = "running" if bot_status["running"] else "stopped"
    print(f"Bot status requested: {status}")  # Log for debugging
    return jsonify({"message": f"Bot is currently {status}."})


if __name__ == "__main__":
    # Run the Flask app on localhost
    app.run(host="127.0.0.1", port=5001)