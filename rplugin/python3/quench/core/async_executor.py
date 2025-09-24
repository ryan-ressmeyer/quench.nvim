"""
AsyncExecutor - Standardized async execution patterns for Quench plugin.

This module provides centralized async execution handling to eliminate the
repetitive boilerplate found in 8+ commands throughout the main plugin file.
"""

import asyncio
import logging
from typing import Callable, Any, Awaitable, Optional
import functools


class AsyncExecutor:
    """
    Centralized async execution management for the Quench plugin.

    Handles event loop detection, proper task scheduling, and error handling
    for async operations within the synchronous pynvim command context.
    """

    def __init__(self, nvim, logger: Optional[logging.Logger] = None):
        """
        Initialize the AsyncExecutor.

        Args:
            nvim: The pynvim.Nvim instance for interacting with Neovim
            logger: Optional logger instance. If None, will create one.
        """
        self.nvim = nvim
        self._logger = logger or logging.getLogger("quench.async_executor")

    async def execute_async(self, coro: Awaitable[Any], error_context: str = "operation") -> Any:
        """
        Execute an async coroutine with proper error handling.

        Args:
            coro: The coroutine to execute
            error_context: Context string for error messages

        Returns:
            The result of the coroutine execution
        """
        try:
            return await coro
        except Exception as e:
            self._logger.error(f"{error_context} failed: {e}")
            # Use the Python notification system
            try:
                from ..utils.notifications import notify_user
                error_msg = str(e)  # Capture the error message before lambda
                self.nvim.async_call(
                    lambda: notify_user(self.nvim, f"{error_context} failed: {error_msg}", level='error')
                )
            except Exception as notify_error:
                self._logger.error(f"Failed to notify user of {error_context} error: {notify_error}")
            raise

    def execute_sync(self, coro: Awaitable[Any], error_context: str = "operation") -> Any:
        """
        Execute an async coroutine from a sync context with proper event loop handling.

        This method handles the complex event loop detection and execution pattern
        that was repeated throughout the main plugin file.

        Args:
            coro: The coroutine to execute
            error_context: Context string for error messages

        Returns:
            The result of the coroutine execution
        """
        try:
            # Try to get current event loop
            loop = asyncio.get_event_loop()

            if loop.is_running():
                # We're in an async context but need to return a result for sync pynvim commands
                # Schedule as task but don't return it directly - let it run in background
                task = asyncio.create_task(self.execute_async(coro, error_context))

                def handle_task_exception(task):
                    """Handle exceptions from background tasks"""
                    if task.exception():
                        self._logger.error(f"Background task failed in {error_context}: {task.exception()}")
                        try:
                            # Notify user of the failure via import since we're not in async context
                            from ..utils.notifications import notify_user
                            self.nvim.async_call(lambda: notify_user(self.nvim, f"{error_context} failed: {task.exception()}", level='error'))
                        except Exception as notify_error:
                            self._logger.error(f"Failed to notify user of background task error: {notify_error}")

                task.add_done_callback(handle_task_exception)
                # Don't return the task - return None so pynvim doesn't try to serialize it
                return None
            else:
                # No running loop - run until complete
                return loop.run_until_complete(self.execute_async(coro, error_context))

        except RuntimeError:
            # No event loop exists - create new one
            return asyncio.run(self.execute_async(coro, error_context))

    def create_background_task(self, coro: Awaitable[Any], error_context: str = "background operation") -> Optional[asyncio.Task]:
        """
        Create a background task if we're in an async context.

        Args:
            coro: The coroutine to execute
            error_context: Context string for error messages

        Returns:
            The created task if successful, None otherwise
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self.execute_async(coro, error_context))

                def handle_task_exception(task):
                    """Handle exceptions from background tasks"""
                    if task.exception():
                        self._logger.error(f"Background task failed in {error_context}: {task.exception()}")

                task.add_done_callback(handle_task_exception)
                return task
        except RuntimeError:
            self._logger.warning(f"Cannot create background task for {error_context}: no event loop")
        return None


def async_command(error_context: str = "command"):
    """
    Decorator to standardize async command execution in pynvim commands.

    This decorator eliminates the boilerplate async execution code that was
    repeated in 8+ commands throughout the main plugin file.

    Args:
        error_context: Context string for error messages

    Usage:
        @async_command("cell execution")
        def run_cell(self):
            return self._run_cell_async()

        async def _run_cell_async(self):
            # Actual async implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Get the coroutine from the wrapped function
            coro = func(self, *args, **kwargs)

            # Execute using the plugin's async executor
            if hasattr(self, 'async_executor'):
                return self.async_executor.execute_sync(coro, error_context)
            else:
                # Fallback for testing or if async_executor not initialized
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        return asyncio.create_task(coro)
                    else:
                        return loop.run_until_complete(coro)
                except RuntimeError:
                    return asyncio.run(coro)
        return wrapper
    return decorator