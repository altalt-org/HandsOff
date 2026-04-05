"""
Droidrun - A framework for controlling Android devices through LLM agents.
"""

import logging
from importlib.metadata import version

__version__ = version("droidrun")

# Attach a default CLILogHandler so that every consumer (CLI, TUI, SDK,
# tools-only) gets visible output without explicit setup.  CLI and TUI
# replace this with their own handler via ``configure_logging()``.
from droidrun.log_handlers import CLILogHandler

_logger = logging.getLogger("droidrun")
_logger.addHandler(CLILogHandler())
_logger.setLevel(logging.INFO)
_logger.propagate = False

# Heavy imports commented out — require llama-index and other large deps.
# Uncomment when using the full droidrun agent stack.
# from droidrun.agent import ResultEvent
# from droidrun.agent.droid import DroidAgent
# from droidrun.agent.utils.llm_picker import load_llm
# from droidrun.config_manager import (
#     AgentConfig, AppCardConfig, FastAgentConfig, CredentialsConfig,
#     DeviceConfig, DroidConfig, ExecutorConfig, LLMProfile,
#     LoggingConfig, ManagerConfig, TelemetryConfig, ToolsConfig, TracingConfig,
# )
# from droidrun.macro import MacroPlayer, replay_macro_file, replay_macro_folder
from droidrun.tools import AndroidDriver, DeviceDriver, RecordingDriver

__all__ = [
    "DeviceDriver",
    "AndroidDriver",
    "RecordingDriver",
]
