import asyncio
import websockets
import json
from datetime import datetime, timedelta
from decimal import Decimal
import threading

# Global registry for loggers
loggers = {}
logger_ready_events = {}  # Registry for thread synchronization events

class ThreadSafeLogger:
    def __init__(self, bot_id, loop, reconnect_interval=5):
        self.bot_id = bot_id
        self.queue = asyncio.Queue()
        self.websocket = None
        self.loop = loop
        self.connection_successful = False
        self.reconnect_interval = reconnect_interval  # Interval to wait before reconnecting

    async def connect(self):
        """
        Attempt to connect to the WebSocket server. Reconnect if necessary.
        """
        while not self.connection_successful:
            try:
                print("Attempting to connect to WebSocket...")
                self.websocket = await websockets.connect('ws://localhost:8080')
                self.connection_successful = True
                print("WebSocket connection established.")
            except Exception as e:
                print(f"Failed to connect to WebSocket: {e}. Retrying in {self.reconnect_interval} seconds...")
                await asyncio.sleep(self.reconnect_interval)

    async def log_worker(self):
        """
        Continuously process log messages and attempt to reconnect if necessary.
        """
        while True:
            message = await self.queue.get()
            while True:  # Retry loop for sending the message
                try:
                    await self.connect()  # Ensure a connection exists
                    if self.connection_successful:
                        await self.websocket.send(json.dumps({"bot_id": self.bot_id, "log": message}))
                        break  # Exit the retry loop after a successful send
                except websockets.ConnectionClosedError:
                    print("WebSocket connection closed. Attempting to reconnect...")
                    self.connection_successful = False
                    await asyncio.sleep(self.reconnect_interval)  # Wait before retrying
                except Exception as e:
                    print(f"Failed to send log: {e}. Retrying...")
                    await asyncio.sleep(self.reconnect_interval)  # Wait before retrying
                # No `finally` block here; the message stays in the retry loop until sent
            self.queue.task_done()

    def log(self, message):
        """
        Add a message to the log queue to be processed by the worker.
        """
        asyncio.run_coroutine_threadsafe(self.queue.put(message), self.loop)

    async def close(self):
        """
        Close the logger gracefully.
        """
        await self.queue.join()  # Wait until all messages are processed
        if self.websocket:
            await self.websocket.close()
def logger_thread(bot_name, ready_event):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger = ThreadSafeLogger(bot_name, loop)
    loggers[bot_name] = logger  # Store the logger in the global registry
    ready_event.set()  # Signal that the logger is ready
    try:
        loop.run_until_complete(logger.log_worker())
    finally:
        loop.run_until_complete(logger.close())
        loop.close()
        del loggers[bot_name]  # Remove the logger from the registry on shutdown

def start_logger(bot_name):
    """
    Starts the logger in a dedicated thread and ensures it's ready before returning it.
    """
    if bot_name in loggers:
        return loggers[bot_name]  # Return existing logger if already started

    ready_event = threading.Event()
    logger_ready_events[bot_name] = ready_event

    thread = threading.Thread(target=logger_thread, args=(bot_name, ready_event))
    thread.daemon = True
    thread.start()

    # Wait for the logger to be ready
    ready_event.wait()
    return loggers[bot_name]

def stop_logger(bot_name):
    """
    Stops the logger thread and closes the logger gracefully.
    """
    logger = loggers.get(bot_name)
    if logger:
        asyncio.run(logger.close())  # Close the logger
        loggers.pop(bot_name, None)  # Remove the logger from the registry
    logger_ready_events.pop(bot_name, None)  # Remove the ready event if present
    

def create_message_data(message, status="log", data=None):
    """
    Creates a consistent messageData object.

    Args:
        message (str): The main message content.
        status (str): The status of the message (default: "log"). Options: "log", "notify", "warn", "error", "success".
        data (list): Additional data related to the message (default: None).

    Returns:
        dict: A dictionary containing the message data.
    """
    return {
        "message": message,
        "status": status,
        "data": data or []  # Default to an empty list if no data is provided
    } 


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()  # Convert datetime to ISO 8601 string
        return super().default(obj)

    
def wsprint(logger, message, action="both"):
    """
    Logs a message using the logger and prints it to the console based on the specified action.

    Args:
        logger (ThreadSafeLogger): The logger instance.
        message (str or dict): The message to log and print. Can be a string or a dictionary.
        action (str): Determines the action to take. 
                      Options are "both" (default), "log", or "print".
    """
    if action not in {"both", "log", "print"}:
        raise ValueError(f"Invalid action: {action}. Use 'both', 'log', or 'print'.")
    
    # If the message is a dictionary or object, serialize it to JSON
    if isinstance(message, (dict, list)):
        serialized_message = json.dumps(message, cls=CustomJSONEncoder)
    else:
        serialized_message = message  # Assume it's already a string

    if action in {"both", "log"} and logger:
        logger.log(serialized_message)
    # if action in {"both", "print"}:
    #     print(message)  # Print the original message, not the serialized one
