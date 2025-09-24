"""
Debug and status commands for the Quench plugin.

This module contains command implementation functions for:
- Plugin status information
- Plugin shutdown
- Debug diagnostics
- Basic connectivity testing
"""

import asyncio


def status_command_impl(plugin):
    """
    Implementation for showing status of Quench plugin components.

    Args:
        plugin: The main Quench plugin instance
    """
    try:
        # Web server status
        server_status = "running" if plugin.web_server_started else "stopped"
        server_url = f"http://{plugin.web_server.host}:{plugin.web_server.port}"

        # Kernel sessions status
        sessions = plugin.kernel_manager.list_sessions()
        session_count = len(sessions)

        # Message relay status
        relay_status = "running" if (plugin.message_relay_task and not plugin.message_relay_task.done()) else "stopped"

        status_msg = f"""Quench Status:
  Web Server: {server_status} ({server_url})
  Kernel Sessions: {session_count} active
  Message Relay: {relay_status}
"""

        if sessions:
            status_msg += "\nActive Sessions:\n"
            for kernel_id, info in sessions.items():
                buffers = ', '.join(map(str, info['associated_buffers']))
                status_msg += f"  {kernel_id[:8]}: buffers [{buffers}], cache size: {info['output_cache_size']}\n"

        plugin.nvim.out_write(status_msg)

    except Exception as e:
        plugin._logger.error(f"Error in QuenchStatus: {e}")
        plugin.nvim.err_write(f"Status error: {e}\n")


def stop_command_impl(plugin):
    """
    Implementation for stopping all Quench components.

    Args:
        plugin: The main Quench plugin instance
    """
    plugin.nvim.out_write("Stopping Quench components...\n")
    try:
        plugin._cleanup()
        plugin.nvim.out_write("Quench stopped.\n")
    except Exception as e:
        plugin._logger.error(f"Error in QuenchStop: {e}")
        plugin.nvim.err_write(f"Stop error: {e}\n")


def hello_world_command_impl(plugin):
    """
    Implementation for simple hello world command for testing plugin loading.

    Args:
        plugin: The main Quench plugin instance
    """
    plugin.nvim.out_write("Hello, world from Quench plugin!\n")


def debug_command_impl(plugin):
    """
    Implementation for debug command to test plugin functionality and show diagnostics.

    Args:
        plugin: The main Quench plugin instance
    """
    try:
        plugin._logger.info("QuenchDebug called")
        plugin.nvim.out_write("=== Quench Debug Info ===\n")

        # Test logging
        plugin.nvim.out_write("✓ Plugin loaded and responding\n")
        plugin._logger.info("Debug command executed successfully")

        # Test buffer access
        try:
            current_bnum = plugin.nvim.current.buffer.number
            current_line = plugin.nvim.current.window.cursor[0]
            plugin.nvim.out_write(f"✓ Buffer access: buffer {current_bnum}, line {current_line}\n")
        except Exception as e:
            plugin.nvim.out_write(f"✗ Buffer access failed: {e}\n")

        # Test dependencies
        try:
            import jupyter_client
            plugin.nvim.out_write("✓ jupyter_client available\n")
        except ImportError:
            plugin.nvim.out_write("✗ jupyter_client not available\n")

        try:
            import aiohttp
            plugin.nvim.out_write("✓ aiohttp available\n")
        except ImportError:
            plugin.nvim.out_write("✗ aiohttp not available\n")

        # Test async functionality
        try:
            import asyncio
            plugin.nvim.out_write("✓ asyncio available\n")
            try:
                loop = asyncio.get_event_loop()
                plugin.nvim.out_write(f"✓ Event loop: {type(loop).__name__}\n")
            except RuntimeError:
                plugin.nvim.out_write("✗ No event loop found\n")
        except Exception as e:
            plugin.nvim.out_write(f"✗ Asyncio test failed: {e}\n")

        plugin.nvim.out_write("=== End Debug Info ===\n")

    except Exception as e:
        plugin._logger.error(f"Error in QuenchDebug: {e}")
        plugin.nvim.err_write(f"Debug error: {e}\n")