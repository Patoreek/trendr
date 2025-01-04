import asyncio
import websockets
import json
import threading

# Global registry for loggers
loggers = {}
logger_ready_events = {}  # Registry for thread synchronization events

class ThreadSafeLogger:
    def __init__(self, bot_id, loop):
        self.bot_id = bot_id
        self.queue = asyncio.Queue()
        self.websocket = None
        self.loop = loop
        self.connection_successful = False

    async def connect(self):
        if self.websocket is None or not self.connection_successful:
            print("Attempting to connect to WebSocket...")
            try:
                self.websocket = await websockets.connect('ws://localhost:8080')
                self.connection_successful = True
                print("WebSocket connection established.")
            except Exception as e:
                print(f"Failed to connect to WebSocket: {e}")
                self.connection_successful = False

    async def log_worker(self):
        while True:
            message = await self.queue.get()
            try:
                await self.connect()
                if self.connection_successful:
                    await self.websocket.send(json.dumps({"bot_id": self.bot_id, "log": message}))
            except Exception as e:
                print(f"Failed to send log: {e}")
            finally:
                self.queue.task_done()

    def log(self, message):
        asyncio.run_coroutine_threadsafe(self.queue.put(message), self.loop)

    async def close(self):
        await self.queue.join()
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
    
    
    
def lprint(logger, message, action="both"):
    """
    Logs a message using the logger and prints it to the console based on the specified action.

    Args:
        logger (ThreadSafeLogger): The logger instance.
        message (str): The message to log and print.
        action (str): Determines the action to take. 
                      Options are "both" (default), "log", or "print".
    """
    if action not in {"both", "log", "print"}:
        raise ValueError(f"Invalid action: {action}. Use 'both', 'log', or 'print'.")
    
    if action in {"both", "log"} and logger:
        logger.log(message)
    if action in {"both", "print"}:
        print(message)
