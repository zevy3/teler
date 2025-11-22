"""
Logging Module
--------------
This module provides asynchronous logging functionality with support for log levels,
file rotation, and custom logging policies for the TELERAG-MONOLITH project.

Key Components:
1. Exceptions:
   - LoggingCreationException: Raised when there is an error during logger creation.
   - LoggingCancellation: Raised to signal cancellation of logging operations.

2. Logger Infrastructure:
   - BaseLogger: Abstract base class defining the logger interface.
   - Logger: Implements asynchronous logging, maintains a message queue, and writes logs to files.
   - LoggerComposer: Manages and registers logger instances, ensuring a singleton pattern for global access.
   - ComposerMeta: A metaclass that automates logger registration to the LoggerComposer.

3. Log Levels and Rotation:
   - LogLevel: Enumerates available log levels (DEBUG, INFO, WARNING, ERROR, etc.).
   - RotType: Defines the rotation type for log files (NONE, TIME, SIZE, TIME_SIZE).
   - LogPolicy: Specifies policies to handle failed flush attempts (PRINT, LOOSE, KEEP).
   - FileGateway: Handles file operations, message buffering, and log file rotation based on configured policies.

4. Utility Functions:
   - aprint and aprint_err: Asynchronous print functions to stdout and stderr respectively.
   - stop_logging: Shuts down all loggers and file gateways gracefully.

Usage:
- Instantiate a Logger (or a subclass) to start logging. The creation process automatically registers
  it via ComposerMeta.
- Configure logging levels and file rotation settings as needed.
- Use async methods like info, debug, error, etc., for logging messages.
- Call stop_logging() after the application completes its logging tasks to ensure proper shutdown.
"""

import asyncio, enum, sys, os, aiofiles
from datetime import datetime
from types import MappingProxyType
from typing import Optional
class LoggingCreationException(Exception):
    pass
class LoggingCancellation(Exception):
    pass

size_type_dict = MappingProxyType({
            "b": 1,
            "bytes": 1,
            "byte": 1,
            "kb": 1024,
            "kilobytes": 1024,
            "kilobyte": 1024,
            "mb": 1024 * 1024,
            "megabytes": 1024 * 1024,
            "megabyte": 1024 * 1024,
            "gb": 1024 * 1024 * 1024,
            "gigabytes": 1024 * 1024 * 1024,
            "gigabyte": 1024 * 1024 * 1024
        })

time_type_dict = MappingProxyType({
            "s": 1,
            "seconds": 1,
            "second": 1,
            "m": 60,
            "minutes": 60,
            "minute": 60,
            "h": 60 * 60,
            "hours": 60 * 60,
            "hour": 60 * 60,
            "d": 60 * 60 * 24,
            "days": 60 * 60 * 24,
            "day": 60 * 60 * 24
        })

class LogLevel(enum.Enum):
    SIGSTOP = -1
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    FATAL = 4
    EXCEPTION = 5
    QUIET = 6
    NOTSET = 7

loglevel_dict = MappingProxyType({
    "DEBUG": LogLevel.DEBUG,
    "INFO": LogLevel.INFO,
    "WARNING": LogLevel.WARNING,
    "ERROR": LogLevel.ERROR,
    "FATAL": LogLevel.FATAL,
    "EXCEPTION": LogLevel.EXCEPTION,
    "QUIET": LogLevel.QUIET,
    "NOTSET": LogLevel.NOTSET,
})
reversed_loglevel_dict = MappingProxyType({
    LogLevel.DEBUG.value: "DEBUG",
    LogLevel.INFO.value: "INFO",
    LogLevel.WARNING.value: "WARNING",
    LogLevel.ERROR.value: "ERROR",
    LogLevel.FATAL.value: "FATAL",
    LogLevel.EXCEPTION.value: "EXCEPTION",
    LogLevel.QUIET.value: "QUIET",
    LogLevel.NOTSET.value: "NOTSET",
})

class BaseLogger:
    async def exception(self, message):
        raise NotImplementedError(
            "Up to subclasses to implement this method."
        )

class LoggerComposer:
    """
    A class that helps create, manage and use loggers.
    """
    _instance: Optional["LoggerComposer"] = None

    @classmethod
    def set_instance(cls, instance: "LoggerComposer"):
        """
        Set the instance of the composer.
        """
        if cls._instance is not None:
            raise RuntimeError(
                "LoggerComposer instance already set. Use get_instance() to access it."
            )
        cls._instance = instance

    @classmethod
    def get_instance(cls) -> "LoggerComposer":
        """
        Get the instance of the composer.
        """
        if cls._instance is None:
            raise RuntimeError(
                "LoggerComposer instance not set. To create it, create instance of Logger class. It will create composer instance for automatically."
            )
        return cls._instance

    def __init__(self, loglevel: str):
        self._loggers = {}
        self.level = loglevel_dict.get(loglevel, LogLevel.NOTSET)

    def __contains__(self, item):
        return item in self._loggers

    def get_logger(self, name: str) -> BaseLogger:
        """
        Get a logger by name.
        """
        if name not in self._loggers:
            raise ValueError(f"Logger {name} not found.")
        return self._loggers[name][0]

    def add_logger(self, name: str, logger: "Logger", file_location: str, gateway: "FileGateway"):
        """
        Add a logger to the composer.
        """
        if name in self._loggers:
            raise ValueError(f"Logger {name} already exists.")
        logger._level = self.level
        gateway.start()
        self._loggers[name] = (logger, file_location, gateway)

    def remove_logger(self, name: str):
        """
        Remove a logger from the composer. Proceed with caution. It may break essential deps in your app.
        """
        if name not in self._loggers:
            raise ValueError(f"Logger {name} not found.")
        del self._loggers[name]

    def get_all(self):
        """
        Get all loggers.
        """
        return self._loggers

    def get_gateway_if_exists(self, file: str) -> Optional['FileGateway']:
        """
        Returns file gateway if exists. Otherwise, returns None.
        """
        for logger in self._loggers.values():
            if logger[1] == file:
                return logger[2]
        return None

    def stop_everything(self):
        """
        Stop all loggers. Use this after the app is done.
        """
        for logger in self._loggers.values():
            logger[0].stop()
            logger[2].stop()
        self._loggers = {}

    def set_level_if_not_set(self):
        """
        Set the level of all loggers if not set.
        """
        for logger in self._loggers.values():
            logger[0].set_level(self.level)


class ComposerMeta(type):
    """
    A metaclass that helps to register Logger classes to a compositor counterpart automatically, and to ensure that composer remains singleton.
    """
    _instance: Optional[LoggerComposer] = None
    @classmethod
    def _get_composer(cls) -> LoggerComposer:
        """get composer instance"""
        if cls._instance is None:
            try:
                composer = LoggerComposer.get_instance()
                return composer
            except RuntimeError:
                composer = LoggerComposer(loglevel="DEBUG")
                LoggerComposer.set_instance(composer)
                cls._instance = composer
        return cls._instance

    @classmethod
    def _stop_all_sig(cls):
        """
        Stop all loggers.
        """
        composer = cls._get_composer()
        composer.stop_everything()

    def __call__(cls, *args, **kwargs):
        """
        This method is called when the class is instantiated.
        It registers the logger to the composer.
        with all the checks
        """
        composer = cls._get_composer()
        logger_name = kwargs.get("name", "default")
        logfile_location = kwargs.get("file", "log.txt")

        logfile_location = "./logs/" + logfile_location

        if logger_name in composer:
            return composer.get_logger(logger_name)

        gateway = composer.get_gateway_if_exists(logfile_location)
        if gateway is None:
            gateway = FileGateway(logfile_location)

        logger = super().__call__(*args, **kwargs)
        logger._file_gateway = gateway
        try:
            composer.add_logger(logger_name, logger, logfile_location, gateway)
            return logger
        except Exception as e:
            raise ValueError("Failed to add logger to composer.") from e

class RotType(enum.Enum):
    NONE = 0
    TIME = 1
    SIZE = 2
    TIME_SIZE = 3

class Logger(BaseLogger, metaclass=ComposerMeta):
    """
    This is a logger class. It logs messages to the log file. Pretty much nothing to explain. Logger is logger, not a rocket.
    """
    def __init__(self, name: str = "default", file: str = "log.txt"):
        """
        Initialize the logger.
        """
        print("Initialized logger " + name + " at " + file)
        self.name = name
        self._level = LogLevel.NOTSET
        self._buffer = []
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._queue_processing_task: Optional[asyncio.Task] = None
        self._logging = True
        self._file_gateway: Optional[FileGateway] = None
        self._file_location = file

    def set_level(self, level: LogLevel):
        """
        Set the level of the logger. It will not be changed later.
        """
        if self._level != LogLevel.NOTSET:
            return
        self._level = level

    def _create(self):
        """
        Create the logger. It creates the log file and starts the logging loop.
        """
        if self._queue_processing_task is not None or self._logging is False:
            return
        self._queue_processing_task = asyncio.create_task(self._process_queue())
        self._logging = True

    async def log(self, loglevel: LogLevel, message: str):
        """
        Log a message to the log file.
        """
        int_level = loglevel.value
        int_self_level = self._level.value
        if self._level == LogLevel.QUIET:
            return
        if loglevel == LogLevel.SIGSTOP:
            await self._message_queue.put(None)
            return
        if int_level >= int_self_level:
            await self._message_queue.put((loglevel, message))

        if self._queue_processing_task is None:
            self._create()

    async def info(self, message):
        await self.log(LogLevel.INFO, message)

    async def debug(self, message):
        await self.log(LogLevel.DEBUG, message)

    async def warning(self, message):
        await self.log(LogLevel.WARNING, message)

    async def error(self, message):
        await self.log(LogLevel.ERROR, message)

    async def fatal(self, message):
        await self.log(LogLevel.FATAL, message)

    async def exception(self, message):
        await self.log(LogLevel.EXCEPTION, message)

    def _apply_decorations(self, level: LogLevel,  message: str) -> str:
        """
        Apply decorations to the message.
        """
        level_string = reversed_loglevel_dict.get(level.value, "UNKNOWN")
        timestamp = datetime.now().strftime("%m-%d_%H:%M:%S")
        return f"[{timestamp} - {self.name}/{level_string}] -> {message}"

    async def _process_queue(self):
        while self._logging:
            try:
                item = await self._message_queue.get()
                if item is None:
                    if self._file_gateway:
                        await self._file_gateway.enqueue(None)
                    break
                level, msg = item
                message = self._apply_decorations(level, msg)
                await aprint(message)
                if self._file_gateway:
                    await self._file_gateway.enqueue(message)
            except (asyncio.CancelledError, LoggingCancellation):
                break
            except Exception as e:
                await aprint_err(f"Logger {self.name} failed to log message: {e}")

    async def stop(self):
        self._logging = False
        await self._message_queue.join()
        if self._queue_processing_task is not None:
            self._queue_processing_task.cancel()
            try:
                await self._queue_processing_task
            except asyncio.CancelledError:
                pass
        self._queue_processing_task = None

class FileGateway:
    """
    Class made to isolate file interactions from logger or multiple loggers.
    """
    def __init__(self, file_loc: str):
        print("Started Logging at " + file_loc)
        self.file_loc = file_loc
        self._start_stamp = int(datetime.now().timestamp())
        self._message_stream: asyncio.Queue[str] = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._logging = True
        self._rot_type = RotType.NONE
        self._rot_amt = None

    def start(self):
        """
        Start the file gateway.
        """
        if self._processing_task is not None:
            return
        self._processing_task = asyncio.create_task(self._stream_process())

    async def enqueue(self, message: str):
        await self._message_stream.put(message)

    def set_file_rotation(self, rot_type: RotType, amt: str):
        if self._rot_type != RotType.NONE:
            return

        self._rot_type = rot_type

        if rot_type == RotType.SIZE:
            self._rot_amt = self.convert_str_to_size(amt)
        elif rot_type == RotType.TIME:
            self._rot_amt = self.convert_str_to_timestamp(amt)
        elif rot_type == RotType.TIME_SIZE:
            time_str, size_str = amt.split("|")
            self._rot_amt = (self.convert_str_to_timestamp(time_str), self.convert_str_to_size(size_str))

    def rotate_if_needed(self, time_amt: Optional[int] = None, size_amt: Optional[int] = None):
        if self._rot_type == RotType.NONE:
            return False

        if self._rot_type == RotType.SIZE:
            if size_amt is not None and size_amt >= self._rot_amt:
                return True
        if self._rot_type == RotType.TIME:
            if time_amt is not None and time_amt - self._start_stamp > self._rot_amt:
                return True
        if self._rot_type == RotType.TIME_SIZE:
            if time_amt is not None and size_amt is not None:
                if time_amt - self._start_stamp > self._rot_amt[0] or size_amt >= self._rot_amt[1]:
                    return True
        return False

    async def _rotate_file(self):
        self._processing_task.cancel()
        try:
            await self._processing_task
        except asyncio.CancelledError:
            pass

        self._start_stamp = int(datetime.now().timestamp())
        try:
            self._processing_task = asyncio.create_task(self._stream_process())
        except Exception:
            await asyncio.sleep(1)

        self._processing_task = asyncio.create_task(self._stream_process())

    @staticmethod
    def convert_str_to_size(amt: str):
        """
        Convert string to size in bytes.
        """
        size_amt, size_type = amt.split()
        size_amt = int(size_amt)

        coefficient = size_type_dict.get(size_type.lower(), 1)
        return size_amt * coefficient

    @staticmethod
    def convert_str_to_timestamp(amt: str):
        """
        Convert string to timestamp.
        """
        time_amt, time_type = amt.split()
        time_amt = int(time_amt)
        coefficient = time_type_dict.get(time_type.lower(), 1)
        return time_amt * coefficient

    @staticmethod
    def boilerplate_message():
        """
        Returns boilerplate message for the logger.
        """
        timestamp = int(datetime.now().timestamp())
        return (
            f"--- Logging Session Start ---\n"
            f"Timestamp: {timestamp}\n"
            f"Project: TELERAG-MONOLITH\n"
            f"Version: 1.0\n"
        )

    async def _stream_process(self):
        """
        Process message stream.
        """
        should_rotate = False
        log_file_path = f"{os.path.splitext(self.file_loc)[0]}_{self._start_stamp}.log"
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

        async with aiofiles.open(log_file_path, mode="a") as IOstream:
            await IOstream.write(self.boilerplate_message() + "\n" + "-" * 20 + "\n")
            await IOstream.flush()
            while self._logging:
                try:
                    msg = await self._message_stream.get()
                    if msg is None:
                        break
                    await IOstream.write(msg + "\n")
                    await IOstream.flush()
                    # Corrected the file path for size checking
                    if self.rotate_if_needed(int(datetime.now().timestamp()), os.path.getsize(log_file_path)):
                        should_rotate = True
                        break

                except (asyncio.CancelledError, LoggingCancellation):
                    break
                except Exception as e:
                    await aprint_err(f"FileGateway failed to write message to file: {e}")

        if should_rotate:
            await self._rotate_file()

    async def stop(self):
        """
        Stop the file gateway.
        """
        self._logging = False
        if self._message_stream:
             await self._message_stream.put(None) # Sentinel to unblock queue
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

async def aprint(message: str, sep: str = " ",end: str = "\n", *args):
    """
    async print function
    """
    try:
        loop = asyncio.get_running_loop()
        full_message = message
        if args:
            for arg in args:
                full_message += sep + str(arg)
        full_message += end
        await loop.run_in_executor(None, sys.stdout.write, full_message)
    except Exception:
        print(message, *args, sep=sep, end=end) # Fallback

async def aprint_err(message: str, sep: str = " ", end: str ="\n", *args):
    try:
        loop = asyncio.get_running_loop()
        full_message = message
        if args:
            for arg in args:
                full_message += sep + str(arg)
        full_message += end
        await loop.run_in_executor(None, sys.stderr.write, full_message)
    except Exception:
        print(message, *args, sep=sep, end=end, file=sys.stderr) # Fallback

def stop_logging():
    """
    Stop all loggers.
    """
    ComposerMeta._stop_all_sig()