"""
AsyncExecutor - Standardized async execution patterns for Quench plugin.

This module provides centralized async execution handling to eliminate the
repetitive boilerplate.
"""

import asyncio
import logging
from typing import Any, Awaitable, Optional


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
                    lambda: notify_user(self.nvim, f"{error_context} failed: {error_msg}", level="error")
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
        # Handle early returns from impl functions (e.g., validation failures)
        if coro is None:
            return None

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

                            self.nvim.async_call(
                                lambda: notify_user(
                                    self.nvim, f"{error_context} failed: {task.exception()}", level="error"
                                )
                            )
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
