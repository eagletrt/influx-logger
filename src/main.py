import sys
from xml.sax import handler

from src.handler.handler_fsm import HandlerFSM
from src.utils.configuration import Configuration
from src.utils.logger_utils import logger


def main(argv=None):
    argv = argv or sys.argv
    if len(argv) < 2:
        logger.warning("Configuration file path not provided, using default: config.json")
        conf:str = "config.json"
    else:
        conf:str = argv[1]
    configuration:Configuration = Configuration.load_from_file(conf)
    logger.info(f"Configuration loaded from {conf}: {configuration}")

    handler:HandlerFSM = HandlerFSM(configuration)
    handler.start()

if __name__ == "__main__":
    main()
