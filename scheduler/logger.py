import os
import sys
import inspect
import datetime
from pathlib import Path
from typing import TypedDict, Literal

LoggerSeverity = Literal["debug", "info", "warn", "error"]


class FunctionCallInfo(TypedDict):
    function: str
    file: str
    line: str


LOG_FILE_PATH = Path(__file__).resolve().parents[2] / "logs" / "logs.log"
LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

COLORS = {
    "debug": "\033[94m",
    "warn": "\033[33m",
    "error": "\033[31m",
    "reset": "\033[0m",
}


def get_timestamp() -> str:
    # ISO-like format with milliseconds (3 digits)
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%d-%H:%M:%S.%f")[:-3]


def get_call_info() -> FunctionCallInfo:
    # Stack:
    # 0 = get_call_info
    # 1 = log
    # 2 = public logger method (info/warn/etc)
    # 3 = actual caller
    stack = inspect.stack()
    if len(stack) <= 3:
        return {
            "function": "<unknown>",
            "file": "<unknown>",
            "line": "<unknown>",
        }

    frame = stack[3]
    file_path = frame.filename or "<unknown>"
    file_name = os.path.basename(file_path)
    function_name = frame.function or "<anonymous>"
    line_number = str(frame.lineno) if frame.lineno else "<unknown>"

    return {
        "file": file_name,
        "function": function_name,
        "line": line_number,
    }


def should_log(level: LoggerSeverity) -> bool:
    log_level = os.getenv("LOG_LEVEL", "debug")
    levels = {
        "debug": 0,
        "info": 1,
        "warn": 2,
        "error": 3,
    }

    return levels.get(level, 0) >= levels.get(log_level, 0)


def _log(level: LoggerSeverity, message: str) -> None:
    timestamp = get_timestamp()
    info = get_call_info()

    verbosity = os.getenv("LOG_VERBOSITY", "detailed").lower()

    if verbosity == "detailed":
        log_message = (
            f"[{timestamp}] {level.upper()} "
            f"[{info['function']}@{info['file']}:{info['line']}]: {message}"
        )
    else:  # simple
        log_message = f"[{timestamp}] {level.upper()}: {message}"

    env = os.getenv("ENV", "development").lower()

    if env in "development":
        if should_log(level):
            if level in COLORS:
                print(COLORS[level] + log_message + COLORS["reset"])
            else:
                print(log_message)
    elif env in "test":
        pass
    else:
        try:
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
        except Exception as err:
            # Fallback to console
            print(f"Failed to write log to file: {err}", file=sys.stderr)
            print(log_message)


class Logger:
    @staticmethod
    def info(message: str) -> None:
        _log("info", message)

    @staticmethod
    def warn(message: str) -> None:
        _log("warn", message)

    @staticmethod
    def error(message: str) -> None:
        _log("error", message)

    @staticmethod
    def debug(message: str) -> None:
        _log("debug", message)


logger = Logger()
