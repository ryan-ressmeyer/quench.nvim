"""
Configuration management utilities for the Quench plugin.

This module contains functions for retrieving and managing plugin configuration
from Neovim global variables with appropriate defaults and error handling.
"""
import logging
from typing import Any


def get_cell_delimiter(nvim: Any, logger: logging.Logger) -> str:
    """
    Get the cell delimiter pattern from Neovim global variable.

    Args:
        nvim: The pynvim.Nvim instance for interacting with Neovim
        logger: Logger instance for error reporting

    Returns:
        str: The regex pattern for cell delimiters, defaults to '^#+\\s*%%' if not set.
             This matches one or more '#' characters followed by optional spaces and '%%'.
    """
    try:
        delimiter = nvim.vars.get('quench_nvim_cell_delimiter', r'^#+\s*%%')
        return delimiter
    except Exception:
        logger.warning("Failed to get custom cell delimiter, using default '^#+\\s*%%'")
        return r'^#+\s*%%'


def get_web_server_host(nvim: Any, logger: logging.Logger) -> str:
    """
    Get the web server host from Neovim global variable.

    Args:
        nvim: The pynvim.Nvim instance for interacting with Neovim
        logger: Logger instance for error reporting

    Returns:
        str: The host address for the web server, defaults to '127.0.0.1' if not set.
    """
    try:
        return nvim.vars.get('quench_nvim_web_server_host', '127.0.0.1')
    except Exception as e:
        logger.warning(f"Error getting web server host from Neovim variable: {e}")
        return '127.0.0.1'


def get_web_server_port(nvim: Any, logger: logging.Logger) -> int:
    """
    Get the web server port from Neovim global variable.

    Args:
        nvim: The pynvim.Nvim instance for interacting with Neovim
        logger: Logger instance for error reporting

    Returns:
        int: The port number for the web server, defaults to 8765 if not set.
    """
    try:
        return nvim.vars.get('quench_nvim_web_server_port', 8765)
    except Exception as e:
        logger.warning(f"Error getting web server port from Neovim variable: {e}")
        return 8765


def get_web_server_auto_select_port(nvim: Any, logger: logging.Logger) -> bool:
    """
    Get the auto_select_port setting from Neovim global variable.

    When enabled, the web server will automatically try subsequent ports if the
    configured port is already in use. This is disabled by default for security
    reasons, ensuring users don't accidentally expose the server on an unexpected port.

    Args:
        nvim: The pynvim.Nvim instance for interacting with Neovim
        logger: Logger instance for error reporting

    Returns:
        bool: Whether to automatically select an available port, defaults to False.
    """
    try:
        return nvim.vars.get('quench_nvim_web_server_auto_select_port', False)
    except Exception as e:
        logger.warning(f"Error getting auto_select_port from Neovim variable: {e}")
        return False