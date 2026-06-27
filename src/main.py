import sys

from src.handler.handler_fsm import HandlerFSM
from src.utils.configuration import Configuration
from src.utils.logger_utils import logger

def safe_stop(handler: HandlerFSM):
    """
    Safely stops the HandlerFSM instance by transitioning to the final state and waiting for the thread to finish.
    Args:
        handler (HandlerFSM): The HandlerFSM instance to be stopped.
    """
    logger.info("Stopping HandlerFSM...")
    handler.stop_machine()
    handler.join()

def main(argv=None):
    argv = argv or sys.argv
    if len(argv) < 2:
        logger.warning("Configuration file path not provided, using default: config.json")
        conf:str = "config.json"
    else:
        conf:str = argv[1]
    configuration:Configuration = Configuration.load_from_file(conf)
    logger.info(f"Configuration loaded from {conf}: {configuration}")

    try:
        handler:HandlerFSM = HandlerFSM(configuration)
        #handler.start()
        #handler.join()
    except KeyboardInterrupt:
        logger.info("Ctrl+C received, stopping handler")
        safe_stop(handler)

if __name__ == "__main__":
    main()
