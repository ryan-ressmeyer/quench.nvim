"""
Kernel management commands for the Quench plugin.

This module contains command implementation functions for:
- Kernel interruption
- Kernel reset/restart
"""

from ..utils.notifications import notify_user


async def interrupt_kernel_command_impl(plugin):
    """
    Implementation for sending an interrupt signal to the kernel associated with the current buffer.

    Args:
        plugin: The main Quench plugin instance
    """
    plugin._logger.info("QuenchInterruptKernel called")

    # Get current buffer number
    try:
        current_bnum = plugin.nvim.current.buffer.number
    except Exception as e:
        plugin._logger.error(f"Error getting buffer number: {e}")
        notify_user(plugin.nvim, f"Error accessing buffer: {e}", level='error')
        return

    # Run async operation using AsyncExecutor
    await plugin._interrupt_kernel_async(current_bnum)

async def reset_kernel_command_impl(plugin):
    """
    Implementation for restarting the kernel associated with the current buffer and clearing its state.

    Args:
        plugin: The main Quench plugin instance
    """
    plugin._logger.info("QuenchResetKernel called")

    # Get current buffer number
    try:
        current_bnum = plugin.nvim.current.buffer.number
    except Exception as e:
        plugin._logger.error(f"Error getting buffer number: {e}")
        notify_user(plugin.nvim, f"Error accessing buffer: {e}", level='error')
        return

    # Run async operation using AsyncExecutor
    await plugin._reset_kernel_async(current_bnum)






