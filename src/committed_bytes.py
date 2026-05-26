from src.influx import Line
from src.logger_utils import logger

max_gigabytes_before_stop: float = 10

file_name: str = "committed_bytes.log"
bytes_to_commit: int = 0
lines: int = 0
limit: int = 5_000

def add_line(line: Line):
    bytes_in_line: int = line.get_size_in_bytes()
    add_bytes(bytes_in_line)

def add_bytes(bytes: int) -> None|str:
    global bytes_to_commit, lines, limit
    bytes_to_commit += bytes
    lines += 1
    if lines >= limit:
        commit()
        return get_pretty_committed_bytes()
    else:
        return None
    
def is_max_bytes_reached() -> bool:
    total_committed_bytes = get_committed_bytes()
    if total_committed_bytes >= max_gigabytes_before_stop * 1_000_000_000:
        logger.info(f"Committer: Total committed bytes ({pretty_print_committed_bytes(total_committed_bytes)}) has reached the limit of {max_gigabytes_before_stop} GB.")
        return True
    return False

def commit() -> None:
    global bytes_to_commit, lines
    if bytes_to_commit == 0:
        return
    try:
        with open(file_name, "a") as f:
            f.write(f"{bytes_to_commit}\n")
    except Exception as e:
        logger.error(f"Committer: Failed to write committed bytes to file: {e}")
    bytes_to_commit = 0
    lines = 0
    
def get_committed_bytes() -> int:
    try:
        tot: int = 0
        with open(file_name, "r") as f:
            lines = f.readlines()
            tot = sum(int(line.strip()) for line in lines)
        with open(file_name, "w") as f:
            f.write(f"{tot}\n")
        return tot
    except FileNotFoundError:
        logger.error(f"Committed bytes file '{file_name}' not found. Returning 0.")
        return 0
    
def pretty_print_committed_bytes(bytes: int) -> str:
    if bytes < 1_000:
        return f"{bytes} B"
    elif bytes < 1_000_000:
        return f"{bytes / 1_000:.3f} KB"
    elif bytes < 1_000_000_000:
        return f"{bytes / 1_000_000:.3f} MB"
    elif bytes < 1_000_000_000_000:
        return f"{bytes / 1_000_000_000:.3f} GB"
    else:
        return f"{bytes / 1_000_000_000_000:.3f} TB"

def get_pretty_committed_bytes() -> str:
    bytes = get_committed_bytes()
    logger.info(f"Committer: Total committed bytes: {pretty_print_committed_bytes(bytes)}")
    return pretty_print_committed_bytes(bytes)
