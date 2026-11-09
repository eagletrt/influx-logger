"""
Main entry point for the Influx Logger service.
"""
import sys
from pathlib import Path

from src.handler.handler_fsm import HandlerFSM
from src.parser.parserfsm import ParserFSM
from src.utils.configuration import Configuration
from src.utils.logger_utils import logger
from src.utils.tlm_fsm import TelemetryFSM


def safe_stop(handler: HandlerFSM):
    """
    Safely stops the HandlerFSM instance by transitioning to the final state and 
    waiting for the thread to finish.
    Args:
        handler (HandlerFSM): The HandlerFSM instance to be stopped.
    """
    logger.info("Stopping HandlerFSM...")
    handler.stop_machine()
    handler.join()


def main(argv=None):
    '''
    Main function to start the Influx Logger service.
    It can take an optional command line argument for the configuration file path.
    If not provided, it defaults to "config.json".
    Args:
        argv (list, optional): Command line arguments. Defaults to None.
    Returns:
        None
    '''
    argv = argv or sys.argv
    if len(argv) < 2:
        logger.warning(
            "Configuration file path not provided, using default: config.json")
        conf: str = "config.json"
    else:
        conf: str = argv[1]
    try:
        configuration: Configuration = Configuration.load_from_file(conf)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to load configuration from %s: %s", conf, e)
        sys.exit(1)
    logger.info("Configuration loaded from %s: %s", conf, configuration)
    stop: bool = False
    while not stop:
        stop = True
        try:
            handler: HandlerFSM = HandlerFSM(configuration)
            handler.start()
            handler.join()
        except KeyboardInterrupt:
            logger.info("Ctrl+C received, stopping handler")
            safe_stop(handler)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("HandlerFSM encountered an error: %s", str(e))
            try:
                handler.stop_machine()
                handler.join()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            stop = False


def print_fsm() -> None:
    """
    Prints the FSM structure of the HandlerFSM instance.
    """
    fsm_dir: Path = Path("images/fsm")
    '''
    Path to the directory where FSM diagrams will be saved. 
    '''
    fsm_dir.mkdir(parents=True, exist_ok=True)
    HandlerFSM.draw(fsm_dir / 'handler_fsm.png')
    ParserFSM.draw(fsm_dir / 'parser_fsm.png')
    TelemetryFSM.draw(fsm_dir / 'telemetry_fsm.png')


if __name__ == "__main__":
    #print_fsm()
    main()
