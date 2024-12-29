from flask import Flask, jsonify, request

app = Flask(__name__)

# Bot status and hardcoded data
bot_data = {
    "running": False,
    "starting_price": 1000.0,
    "current_price": 1050.0,
    "current_total_profits": 500.0,
    "weekly_total_profits": 120.0,
    "total_trades": 25,
    "successful_trades": 20,
    "failed_trades": 5,
}


@app.route("/")
def home():
    return jsonify({"message": "Trend Following Bot is ready!"})


@app.route("/start", methods=["POST"])
def start_bot():
    if bot_data["running"]:
        return jsonify({"message": "Bot is already running!", "status": "On"}), 400
    bot_data["running"] = True
    print("Bot started!")  # Log for debugging
    return jsonify({"message": "Bot started successfully!", "status": "On"})


@app.route("/stop", methods=["POST"])
def stop_bot():
    if not bot_data["running"]:
        return jsonify({"message": "Bot is not running!", "status": "Off"}), 400
    bot_data["running"] = False
    print("Bot stopped!")  # Log for debugging
    return jsonify({"message": "Bot stopped successfully!", "status": "Off"})


@app.route("/status", methods=["GET"])
def status_bot():
    status = "On" if bot_data["running"] else "Off"
    print(f"Bot status requested: {status}")  # Log for debugging
    return jsonify(
        {
            "status": status,
            "starting_price": bot_data["starting_price"],
            "current_price": bot_data["current_price"],
            "current_total_profits": bot_data["current_total_profits"],
            "weekly_total_profits": bot_data["weekly_total_profits"],
            "total_trades": bot_data["total_trades"],
            "successful_trades": bot_data["successful_trades"],
            "failed_trades": bot_data["failed_trades"],
        }
    )


if __name__ == "__main__":
    # Run the Flask app on localhost
    app.run(host="127.0.0.1", port=5001)