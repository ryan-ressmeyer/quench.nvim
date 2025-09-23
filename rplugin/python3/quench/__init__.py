import asyncio
import logging
logging.basicConfig(filename="/tmp/quench.log", level=logging.DEBUG)
import re
from typing import Optional
import concurrent.futures 

import pynvim

# Import all the components we've built
from .kernel_session import KernelSessionManager
from .web_server import WebServer
from .ui_manager import NvimUIManager


@pynvim.plugin
class Quench:
    """
    Main Quench plugin class that integrates all components for interactive Python development.
    
    Provides cell-based execution similar to VS Code's Jupyter extension, managing IPython kernels
    and routing output to both terminal and web browser for rich media display.
    """

    def __init__(self, nvim):
        """
        Initialize the plugin with all required components.

        Args:
            nvim: The pynvim.Nvim instance for interacting with Neovim.
        """
        self.nvim = nvim
        
        # Set up logging
        self._logger = logging.getLogger("quench.main")
        
        # Initialize central message relay queue
        self.relay_queue: asyncio.Queue = asyncio.Queue()
        
        # Initialize all manager components
        self.kernel_manager = KernelSessionManager()
        self.ui_manager = NvimUIManager(nvim)
        
        # Cache web server configuration
        self._cached_web_server_host = self._get_web_server_host()
        self._cached_web_server_port = self._get_web_server_port()
        
        self.web_server = WebServer(
            host=self._cached_web_server_host, 
            port=self._cached_web_server_port, 
            nvim=nvim,
            kernel_manager=self.kernel_manager
        )
        
        # Task management
        self.message_relay_task: Optional[asyncio.Task] = None
        self.web_server_started = False
        self._cleanup_lock = asyncio.Lock()  # Lock to manage cleanup process
        
        self._logger.info("Quench plugin initialized")

    def _notify_user(self, message, level='info'):
        """Send a single-line notification to the user."""
        if level == 'info':
            self.nvim.out_write(message + '\n')
        elif level == 'error':
            self.nvim.err_write(message + '\n')

    def _get_cell_delimiter(self):
        """
        Get the cell delimiter pattern from Neovim global variable.
        
        Returns:
            str: The regex pattern for cell delimiters, defaults to '^#+\\s*%%' if not set.
                 This matches one or more '#' characters followed by optional spaces and '%%'.
        """
        try:
            delimiter = self.nvim.vars.get('quench_nvim_cell_delimiter', r'^#+\s*%%')
            return delimiter
        except Exception:
            self._logger.warning("Failed to get custom cell delimiter, using default '^#+\\s*%%'")
            return r'^#+\s*%%'
    
    def _get_web_server_host(self):
        """
        Get the web server host from Neovim global variable.
        
        Returns:
            str: The host address for the web server, defaults to '127.0.0.1' if not set.
        """
        try:
            return self.nvim.vars.get('quench_nvim_web_server_host', '127.0.0.1')
        except Exception as e:
            self._logger.warning(f"Error getting web server host from Neovim variable: {e}")
            return '127.0.0.1'
    
    def _get_web_server_port(self):
        """
        Get the web server port from Neovim global variable.
        
        Returns:
            int: The port number for the web server, defaults to 8765 if not set.
        """
        try:
            return self.nvim.vars.get('quench_nvim_web_server_port', 8765)
        except Exception as e:
            self._logger.warning(f"Error getting web server port from Neovim variable: {e}")
            return 8765

    @pynvim.autocmd("VimLeave", sync=True)
    def on_vim_leave(self):
        """
        Handle Vim exit - fires off the async cleanup and allows Neovim to exit immediately.
        This is a synchronous handler that schedules the async task without waiting for it.
        """
        self._logger.info("Vim leaving - scheduling 'fire and forget' async cleanup.")
        try:
            # Get the running event loop.
            loop = asyncio.get_running_loop()

            # Schedule the cleanup task on the loop. We don't store or wait on
            # the future. This allows the synchronous handler to return
            # immediately, making the UI feel responsive. The pynvim host
            # process will stay alive in the background until the task completes.
            asyncio.run_coroutine_threadsafe(self._async_cleanup(), loop)
            
            self._logger.info("Cleanup task scheduled. Neovim can now exit.")

        except Exception as e:
            self._logger.error(f"Error scheduling VimLeave cleanup: {e}")

    def _cleanup(self):
        """
        This method is now deprecated in favor of the new on_vim_leave logic.
        You can remove it or leave it, but it will no longer be called by on_vim_leave.
        """
        pass # This method is no longer used by the VimLeave autocmd.

    async def _async_cleanup(self):
        """
        A unified and sequential async cleanup method to prevent race conditions.
        """
        async with self._cleanup_lock:
            if not self.web_server_started and self.message_relay_task is None:
                self._logger.info("Cleanup not needed; components already stopped.")
                return

            self._logger.info("Starting async cleanup")

            # 1. Stop the web server and destroy the instance
            if self.web_server:
                try:
                    # Cache the host and port before destroying the instance
                    self._cached_web_server_host = self.web_server.host
                    self._cached_web_server_port = self.web_server.port
                    await self.web_server.stop()
                    self._logger.info("Web server stopped.")
                except Exception as e:
                    self._logger.error(f"Error stopping web server: {e}")
                finally:
                    self.web_server = None  # Destroy the instance
                    self.web_server_started = False

            # 2. Cancel the message relay task
            if self.message_relay_task and not self.message_relay_task.done():
                self.message_relay_task.cancel()
                try:
                    await self.message_relay_task
                except asyncio.CancelledError:
                    pass  # This is expected
                except Exception as e:
                    # Handle case where task is a mock or other object
                    self._logger.debug(f"Task cancellation handled: {e}")
                self.message_relay_task = None
                self._logger.info("Message relay task stopped.")

            # 3. Shutdown all kernel sessions
            if self.kernel_manager:
                try:
                    await self.kernel_manager.shutdown_all_sessions()
                    self._logger.info("All kernel sessions shut down.")
                except Exception as e:
                    self._logger.error(f"Error shutting down kernel sessions: {e}")

            self._logger.info("Async cleanup completed")

    @pynvim.command("QuenchRunCell", sync=True)
    def run_cell(self):
        """
        Execute the current cell in IPython kernel.
        
        This is the main function users will call to execute Python code cells.
        """
        try:
            self._logger.info("QuenchRunCell called - starting execution")
            
            # Get all the synchronous Neovim data we need first (from main thread)
            try:
                current_bnum = self.nvim.current.buffer.number
                current_line = self.nvim.current.window.cursor[0]  # 1-indexed
                
                # Get buffer content synchronously
                buffer = self.nvim.current.buffer
                lines = buffer[:]
                self._logger.info(f"Got buffer data: {current_bnum}, line {current_line}, {len(lines)} lines")
                
            except Exception as e:
                self._logger.error(f"Error getting buffer data: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return
            
            # Extract cell code synchronously
            try:
                delimiter_pattern = self._get_cell_delimiter()
                cell_code, cell_start_line, cell_end_line = self._extract_cell_code_sync(lines, current_line, delimiter_pattern)
                if not cell_code.strip():
                    self._notify_user("No code found in current cell")
                    return
                
                self._logger.debug(f"Cell code extracted: {len(cell_code)} characters")
                self._notify_user(f"Quench: Executing cell (lines {cell_start_line}-{cell_end_line})")
                
            except Exception as e:
                self._logger.error(f"Error extracting cell code: {e}")
                self._notify_user(f"Error extracting cell: {e}", level='error')
                return
            
            # Select kernel synchronously
            try:
                kernel_choice = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_choice:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return

                self._logger.info(f"Using kernel choice: {kernel_choice}")

            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Error selecting kernel: {e}", level='error')
                return

            # Now run the async parts with the data we collected
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._run_cell_async(current_bnum, cell_code, kernel_choice))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, cell_code, kernel_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, cell_code, kernel_choice))
                    
            except Exception as e:
                self._logger.error(f"Error in async execution: {e}")
                import traceback
                self._logger.error(f"Traceback: {traceback.format_exc()}")
                self._notify_user(f"Execution error: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunCell: {e}")
            import traceback
            self._logger.error(f"Traceback: {traceback.format_exc()}")
            self._notify_user(f"Quench error: {e}", level='error')

    def _get_or_select_kernel_sync(self, bnum):
        """
        Synchronously get the kernel for the buffer or prompt the user to select one.

        Args:
            bnum: Buffer number

        Returns:
            dict: A choice dictionary with 'value', 'is_running' keys, or None if failed
        """
        # Check for an existing session
        if bnum in self.kernel_manager.buffer_to_kernel_map:
            kernel_id = self.kernel_manager.buffer_to_kernel_map[bnum]
            if kernel_id in self.kernel_manager.sessions:
                session = self.kernel_manager.sessions[kernel_id]
                return {
                    'value': kernel_id,
                    'is_running': True,
                    'kernel_choice': session.kernel_name
                }

        # Get kernel choices (new kernels first for automatic kernel selection)
        try:
            choices = self.kernel_manager.get_kernel_choices(running_first=False)
            if not choices:
                self.nvim.err_write("No Jupyter kernels found. Please install ipykernel.\n")
                return None

            if len(choices) == 1:
                return choices[0]

            selected_choice = self._select_from_choices_sync(choices, "Please select a kernel")

            if not selected_choice:
                # Fallback to first available choice
                selected_choice = choices[0]

            return selected_choice

        except Exception as e:
            self._logger.error(f"Error during kernel selection: {e}")
            self.nvim.err_write(f"Error selecting kernel: {e}\n")

        return None

    def _extract_cell_code_sync(self, lines, lnum, delimiter_pattern):
        """
        Extract cell code synchronously (no async calls).
        Same logic as ui_manager.get_cell_code but without async.
        
        Args:
            lines: List of buffer lines
            lnum: Current line number (1-indexed)
            delimiter_pattern: Regex pattern for cell delimiters
            
        Returns:
            tuple: (cell_code, cell_start_line, cell_end_line) where lines are 1-indexed
        """
        if not lines:
            return "", 0, 0

        # Convert to 0-indexed for Python list access
        current_line_idx = lnum - 1
        if current_line_idx >= len(lines):
            current_line_idx = len(lines) - 1

        # Find the start of the current cell
        cell_start = 0
        for i in range(current_line_idx, -1, -1):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                if i == current_line_idx:
                    # If we're on a cell delimiter line, start from the next line
                    cell_start = i + 1
                else:
                    # Found a previous delimiter, start after it
                    cell_start = i + 1
                break

        # Find the end of the current cell
        cell_end = len(lines)
        for i in range(current_line_idx + 1, len(lines)):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                cell_end = i
                break

        # Extract the cell content
        cell_lines = lines[cell_start:cell_end]
        
        # Remove empty lines at the beginning and end
        while cell_lines and not cell_lines[0].strip():
            cell_lines.pop(0)
        while cell_lines and not cell_lines[-1].strip():
            cell_lines.pop()

        return '\n'.join(cell_lines), cell_start + 1, cell_end

    async def _run_cell_async(self, current_bnum, cell_code, kernel_choice):
        """
        Async implementation of cell execution.
        Takes pre-collected data to avoid Neovim API calls from wrong thread.

        Args:
            current_bnum: Buffer number
            cell_code: Code to execute
            kernel_choice: Choice dictionary with 'value', 'is_running' keys
        """
        self._logger.debug(f"Starting async execution for buffer {current_bnum}")
        
        async with self._cleanup_lock:
            # Recreate web server if it was destroyed
            if self.web_server is None:
                self._logger.info("Recreating WebServer instance.")
                # Use cached host and port if available, otherwise get from config
                host = getattr(self, '_cached_web_server_host', None) or self._get_web_server_host()
                port = getattr(self, '_cached_web_server_port', None) or self._get_web_server_port()
                self.web_server = WebServer(
                    host=host,
                    port=port,
                    nvim=self.nvim,
                    kernel_manager=self.kernel_manager
                )

            # Start web server if not already running
            if not self.web_server_started:
                try:
                    await self.web_server.start()
                    self.web_server_started = True
                    
                    server_url = f"http://{self.web_server.host}:{self.web_server.port}"
                    def notify_server_started():
                        self._notify_user(f"Quench web server started at {server_url}")
                    
                    try:
                        self.nvim.async_call(notify_server_started)
                    except Exception:
                        self._logger.info(f"Web server started at {server_url}")
                    
                except Exception as e:
                    self._logger.error(f"Failed to start web server: {e}")
                    try:
                        self.nvim.async_call(lambda err=e: self._notify_user(f"Error starting web server: {err}", level='error'))
                    except Exception:
                        pass
        
        # Get or create kernel session for this buffer
        if kernel_choice['is_running']:
            # Attach to existing running kernel
            kernel_id = kernel_choice['value']
            await self.kernel_manager.attach_buffer_to_session(current_bnum, kernel_id)
            session = self.kernel_manager.sessions[kernel_id]
        else:
            # Create a new kernel session
            kernel_choice_value = kernel_choice['value']

            # Try to get a meaningful buffer name
            try:
                buffer_name = self.nvim.current.buffer.name or f"buffer_{current_bnum}"
                if buffer_name:
                    # Extract just the filename
                    import os
                    buffer_name = os.path.basename(buffer_name)
            except:
                buffer_name = f"buffer_{current_bnum}"

            session = await self.kernel_manager.get_or_create_session(
                current_bnum,
                self.relay_queue,
                buffer_name,
                kernel_choice_value
            )
        
        # Start message relay loop if not running
        if self.message_relay_task is None or self.message_relay_task.done():
            self.message_relay_task = asyncio.create_task(self._message_relay_loop())
            self._logger.info("Started message relay loop")
        
        # Execute the code
        self._logger.info(f"Executing cell code in kernel {session.kernel_id[:8]}")
        await session.execute(cell_code)

    async def _message_relay_loop(self):
        """
        Continuously relay messages from kernels to both web server and UI.
        
        This loop reads from the central relay_queue and forwards messages to:
        1. Web server for WebSocket clients
        2. UI manager for text output in Neovim buffers
        """
        self._logger.info("Message relay loop started")
        
        try:
            while True:
                # Get message from the central queue
                kernel_id, message = await self.relay_queue.get()
                
                msg_type = message.get('msg_type', 'unknown')
                self._logger.debug(f"Relaying message: {msg_type} from kernel {kernel_id[:8]}")
                
                # Forward to web server for WebSocket clients
                if self.web_server_started:
                    try:
                        await self.web_server.broadcast_message(kernel_id, message)
                    except Exception as e:
                        self._logger.warning(f"Error broadcasting to web clients: {e}")
                
                # Forward text-based messages to Neovim output buffer
                await self._handle_message_for_nvim(kernel_id, message)
                
                # Mark task as done
                self.relay_queue.task_done()
                
        except asyncio.CancelledError:
            self._logger.info("Message relay loop cancelled")
            raise
        except Exception as e:
            self._logger.error(f"Error in message relay loop: {e}")
        finally:
            self._logger.info("Message relay loop stopped")

    async def _handle_message_for_nvim(self, kernel_id: str, message: dict):
        """
        Handle messages for display in Neovim buffers.
        
        Args:
            kernel_id: ID of the kernel that sent the message
            message: The kernel message to handle
        """
        msg_type = message.get('msg_type')
        content = message.get('content', {})
        
        try:
            # Add debugging for message structure
            parent_msg_id = message.get('parent_header', {}).get('msg_id', 'none')
            self._logger.debug(f"Processing message type: {msg_type}, content keys: {list(content.keys()) if content else 'None'}, parent_msg_id: {parent_msg_id}")
            
            if msg_type == 'stream':
                # Handle stdout/stderr output
                stream_name = content.get('name', 'stdout')
                text = content.get('text', '')
                
                if text.strip():
                    # Log output instead of writing to Neovim to avoid threading issues
                    self._logger.info(f"[{kernel_id[:8]}] {stream_name}: {text.strip()}")
                    
            elif msg_type == 'execute_result':
                # Handle execution results
                data = content.get('data', {})
                if 'text/plain' in data:
                    result_text = data['text/plain']
                    if isinstance(result_text, list):
                        result_text = '\n'.join(result_text)
                    
                    if result_text.strip():
                        self._logger.info(f"[{kernel_id[:8]}] Result: {result_text.strip()}")
                        
            elif msg_type == 'error':
                # Handle errors
                error_name = content.get('ename', 'Error')
                error_value = content.get('evalue', '')
                
                self._logger.error(f"[{kernel_id[:8]}] Error: {error_name}: {error_value}")
                
            elif msg_type == 'execute_input':
                # Show what code was executed
                code = content.get('code', '')
                if code.strip():
                    # Show first few lines of executed code
                    code_lines = code.split('\n')
                    preview = code_lines[0]
                    if len(code_lines) > 1:
                        preview += f" ... ({len(code_lines)} lines)"
                    
                    self._logger.info(f"[{kernel_id[:8]}] Executing: {preview}")
                    
        except Exception as e:
            error_msg = str(e) if e else "Unknown error"
            self._logger.warning(f"Error handling message for Neovim: {error_msg}")
            
            # Add detailed debugging
            import traceback
            self._logger.debug(f"Exception type: {e.__class__.__name__ if e else 'None'}")
            self._logger.debug(f"Message structure: {message}")
            self._logger.debug(f"Exception traceback: {traceback.format_exc()}")

    async def _interrupt_kernel_async(self, current_bnum):
        """
        Async implementation for interrupting a kernel.
        
        Args:
            current_bnum: Buffer number
        """
        self._logger.debug(f"Starting async interrupt for buffer {current_bnum}")
        
        # Get existing session for this buffer
        session = await self.kernel_manager.get_session_for_buffer(current_bnum)
        
        if session is None:
            def notify_no_session():
                self._notify_user("No active kernel session found for this buffer", level='error')
            
            try:
                self.nvim.async_call(notify_no_session)
            except:
                pass
            return
        
        try:
            await session.interrupt()
            
            def notify_success():
                self._notify_user(f"Kernel interrupted successfully")
            
            try:
                self.nvim.async_call(notify_success)
            except:
                pass
                
        except Exception as e:
            self._logger.error(f"Failed to interrupt kernel: {e}")
            def notify_error():
                self._notify_user(f"Failed to interrupt kernel: {e}", level='error')
            
            try:
                self.nvim.async_call(notify_error)
            except:
                pass

    async def _reset_kernel_async(self, current_bnum):
        """
        Async implementation for resetting a kernel.
        
        Args:
            current_bnum: Buffer number
        """
        self._logger.debug(f"Starting async reset for buffer {current_bnum}")
        
        # Get existing session for this buffer
        session = await self.kernel_manager.get_session_for_buffer(current_bnum)
        
        if session is None:
            def notify_no_session():
                self._notify_user("No active kernel session found for this buffer", level='error')
            
            try:
                self.nvim.async_call(notify_no_session)
            except:
                pass
            return
        
        try:
            await session.restart()
            
            def notify_success():
                self._notify_user(f"Kernel reset successfully - all variables and state cleared")
            
            try:
                self.nvim.async_call(notify_success)
            except:
                pass
                
        except Exception as e:
            self._logger.error(f"Failed to reset kernel: {e}")
            def notify_error():
                self._notify_user(f"Failed to reset kernel: {e}", level='error')
            
            try:
                self.nvim.async_call(notify_error)
            except:
                pass

    @pynvim.command('QuenchStatus', sync=True)
    def status_command(self):
        """
        Show status of Quench plugin components.
        """
        try:
            # Web server status
            server_status = "running" if self.web_server_started else "stopped"
            server_url = f"http://{self.web_server.host}:{self.web_server.port}"
            
            # Kernel sessions status
            sessions = self.kernel_manager.list_sessions()
            session_count = len(sessions)
            
            # Message relay status
            relay_status = "running" if (self.message_relay_task and not self.message_relay_task.done()) else "stopped"
            
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
            
            self.nvim.out_write(status_msg)
            
        except Exception as e:
            self._logger.error(f"Error in QuenchStatus: {e}")
            self.nvim.err_write(f"Status error: {e}\n")

    @pynvim.command('QuenchStop', sync=True)
    def stop_command(self):
        """
        Stop all Quench components.
        """
        self.nvim.out_write("Stopping Quench components...\n")
        try:
            self._cleanup()
            self.nvim.out_write("Quench stopped.\n")
        except Exception as e:
            self._logger.error(f"Error in QuenchStop: {e}")
            self.nvim.err_write(f"Stop error: {e}\n")

    @pynvim.command("QuenchRunCellAdvance", sync=True)
    def run_cell_advance(self):
        """
        Execute the current cell and advance cursor to the line following the end of that cell.
        """
        try:
            self._logger.info("QuenchRunCellAdvance called - starting execution")
            
            # Get current position and buffer data
            try:
                current_bnum = self.nvim.current.buffer.number
                current_line = self.nvim.current.window.cursor[0]  # 1-indexed
                buffer = self.nvim.current.buffer
                lines = buffer[:]
                
            except Exception as e:
                self._logger.error(f"Error getting buffer data: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return
            
            # Extract cell code and get end line
            try:
                delimiter_pattern = self._get_cell_delimiter()
                cell_code, cell_start_line, cell_end_line = self._extract_cell_code_sync(lines, current_line, delimiter_pattern)
                if not cell_code.strip():
                    self._notify_user("No code found in current cell")
                    return
                
                self._logger.debug(f"Cell code extracted: {len(cell_code)} characters, ends at line {cell_end_line}")
                self._notify_user(f"Quench: Executing cell (lines {cell_start_line}-{cell_end_line})")
                
            except Exception as e:
                self._logger.error(f"Error extracting cell code: {e}")
                self._notify_user(f"Error extracting cell: {e}", level='error')
                return
            
            # Immediately advance the cursor
            try:
                advance_to_line = cell_end_line + 1 if cell_end_line < len(lines) else len(lines)
                self.nvim.current.window.cursor = (advance_to_line, 0)
            except Exception as e:
                self._logger.error(f"Error advancing cursor: {e}")
                # Don't block execution if cursor advancement fails, just log it.

            # Select kernel synchronously
            try:
                kernel_choice = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_choice:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_choice}")
                
            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Error selecting kernel: {e}", level='error')
                return
            
            # Execute the cell
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._run_cell_async(current_bnum, cell_code, kernel_choice))
                        
                        # The callback now only handles errors, no longer advances cursor.
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, cell_code, kernel_choice))

                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, cell_code, kernel_choice))
                    
            except Exception as e:
                self._logger.error(f"Error in async execution: {e}")
                self._notify_user(f"Execution error: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunCellAdvance: {e}")
            self._notify_user(f"Quench error: {e}", level='error')

    @pynvim.command("QuenchRunSelection", range=True, sync=True)
    def run_selection(self, range_info):
        """
        Execute the code from the visually selected lines.
        
        Args:
            range_info: Range information from Neovim (start_line, end_line)
        """
        try:
            self._logger.info("QuenchRunSelection called - starting execution")
            
            # Get range information
            try:
                start_line, end_line = range_info
                current_bnum = self.nvim.current.buffer.number
                buffer = self.nvim.current.buffer
                
                # Extract selected lines (convert to 0-indexed for buffer access)
                selected_lines = buffer[start_line-1:end_line]
                selected_code = '\n'.join(selected_lines)
                
                if not selected_code.strip():
                    self._notify_user("No code found in selection")
                    return
                
                self._logger.debug(f"Selected code extracted: {len(selected_code)} characters from lines {start_line}-{end_line}")
                self._notify_user(f"Quench: Executing lines {start_line}-{end_line}")
                
            except Exception as e:
                self._logger.error(f"Error extracting selection: {e}")
                self._notify_user(f"Error extracting selection: {e}", level='error')
                return
            
            # Select kernel synchronously
            try:
                kernel_choice = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_choice:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_choice}")
                
            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Error selecting kernel: {e}", level='error')
                return
            
            # Execute the selection
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._run_cell_async(current_bnum, selected_code, kernel_choice))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, selected_code, kernel_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, selected_code, kernel_choice))
                    
            except Exception as e:
                self._logger.error(f"Error in async execution: {e}")
                self._notify_user(f"Execution error: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunSelection: {e}")
            self._notify_user(f"Quench error: {e}", level='error')

    @pynvim.command("QuenchRunLine", sync=True)
    def run_line(self):
        """
        Execute only the line the cursor is currently on.
        """
        try:
            self._logger.info("QuenchRunLine called - starting execution")
            
            # Get current line
            try:
                current_bnum = self.nvim.current.buffer.number
                current_line_num = self.nvim.current.window.cursor[0]  # 1-indexed
                buffer = self.nvim.current.buffer
                
                # Extract current line (convert to 0-indexed for buffer access)
                current_line_code = buffer[current_line_num - 1]
                
                if not current_line_code.strip():
                    self._notify_user("Current line is empty")
                    return
                
                self._logger.debug(f"Current line code: {current_line_code}")
                self._notify_user(f"Quench: Executing line {current_line_num}")
                
            except Exception as e:
                self._logger.error(f"Error extracting current line: {e}")
                self._notify_user(f"Error extracting current line: {e}", level='error')
                return
            
            # Select kernel synchronously
            try:
                kernel_choice = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_choice:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_choice}")
                
            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Error selecting kernel: {e}", level='error')
                return
            
            # Execute the line
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._run_cell_async(current_bnum, current_line_code, kernel_choice))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, current_line_code, kernel_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, current_line_code, kernel_choice))
                    
            except Exception as e:
                self._logger.error(f"Error in async execution: {e}")
                self._notify_user(f"Execution error: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunLine: {e}")
            self._notify_user(f"Quench error: {e}", level='error')

    @pynvim.command("QuenchRunAbove", sync=True)
    def run_above(self):
        """
        Run all cells from the top of the buffer up to (but not including) the current cell.
        """
        try:
            self._logger.info("QuenchRunAbove called - starting execution")
            
            # Get buffer data
            try:
                current_bnum = self.nvim.current.buffer.number
                current_line = self.nvim.current.window.cursor[0]  # 1-indexed
                buffer = self.nvim.current.buffer
                lines = buffer[:]
                
            except Exception as e:
                self._logger.error(f"Error getting buffer data: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return
            
            # Find all cells above current position
            try:
                delimiter_pattern = self._get_cell_delimiter()
                cells_to_run = self._extract_cells_above(lines, current_line, delimiter_pattern)
                
                if not cells_to_run:
                    self._notify_user("No cells found above current position")
                    return
                
                # Combine all cell codes
                combined_code = '\n\n'.join(cells_to_run)
                self._logger.debug(f"Combined code from {len(cells_to_run)} cells: {len(combined_code)} characters")
                self._notify_user("Quench: Executing all cells above cursor")
                
            except Exception as e:
                self._logger.error(f"Error extracting cells above: {e}")
                self._notify_user(f"Error extracting cells: {e}", level='error')
                return
            
            # Select kernel synchronously
            try:
                kernel_choice = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_choice:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_choice}")
                
            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Error selecting kernel: {e}", level='error')
                return
            
            # Execute the combined code
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                    
            except Exception as e:
                self._logger.error(f"Error in async execution: {e}")
                self._notify_user(f"Execution error: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunAbove: {e}")
            self._notify_user(f"Quench error: {e}", level='error')

    @pynvim.command("QuenchRunBelow", sync=True)
    def run_below(self):
        """
        Run all cells from the current cell to the end of the buffer.
        """
        try:
            self._logger.info("QuenchRunBelow called - starting execution")
            
            # Get buffer data
            try:
                current_bnum = self.nvim.current.buffer.number
                current_line = self.nvim.current.window.cursor[0]  # 1-indexed
                buffer = self.nvim.current.buffer
                lines = buffer[:]
                
            except Exception as e:
                self._logger.error(f"Error getting buffer data: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return
            
            # Find all cells from current position to end
            try:
                delimiter_pattern = self._get_cell_delimiter()
                cells_to_run = self._extract_cells_below(lines, current_line, delimiter_pattern)
                
                if not cells_to_run:
                    self._notify_user("No cells found from current position to end")
                    return
                
                # Combine all cell codes
                combined_code = '\n\n'.join(cells_to_run)
                self._logger.debug(f"Combined code from {len(cells_to_run)} cells: {len(combined_code)} characters")
                self._notify_user("Quench: Executing all cells from cursor to end of file")
                
            except Exception as e:
                self._logger.error(f"Error extracting cells below: {e}")
                self._notify_user(f"Error extracting cells: {e}", level='error')
                return
            
            # Select kernel synchronously
            try:
                kernel_choice = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_choice:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_choice}")
                
            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Error selecting kernel: {e}", level='error')
                return
            
            # Execute the combined code
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                    
            except Exception as e:
                self._logger.error(f"Error in async execution: {e}")
                self._notify_user(f"Execution error: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunBelow: {e}")
            self._notify_user(f"Quench error: {e}", level='error')

    @pynvim.command("QuenchRunAll", sync=True)
    def run_all(self):
        """
        Run all cells in the current buffer.
        """
        try:
            self._logger.info("QuenchRunAll called - starting execution")
            
            # Get buffer data
            try:
                current_bnum = self.nvim.current.buffer.number
                buffer = self.nvim.current.buffer
                lines = buffer[:]
                
            except Exception as e:
                self._logger.error(f"Error getting buffer data: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return
            
            # Find all cells in the buffer
            try:
                delimiter_pattern = self._get_cell_delimiter()
                all_cells = self._extract_all_cells(lines, delimiter_pattern)
                
                if not all_cells:
                    self._notify_user("No cells found in buffer")
                    return
                
                # Combine all cell codes
                combined_code = '\n\n'.join(all_cells)
                self._logger.debug(f"Combined code from {len(all_cells)} cells: {len(combined_code)} characters")
                self._notify_user("Quench: Executing all cells in the buffer")
                
            except Exception as e:
                self._logger.error(f"Error extracting all cells: {e}")
                self._notify_user(f"Error extracting cells: {e}", level='error')
                return
            
            # Select kernel synchronously
            try:
                kernel_choice = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_choice:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_choice}")
                
            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Error selecting kernel: {e}", level='error')
                return
            
            # Execute the combined code
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, combined_code, kernel_choice))
                    
            except Exception as e:
                self._logger.error(f"Error in async execution: {e}")
                self._notify_user(f"Execution error: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunAll: {e}")
            self._notify_user(f"Quench error: {e}", level='error')

    def _extract_cells_above(self, lines, current_line, delimiter_pattern):
        """
        Extract all cell codes from the top of buffer up to (but not including) current cell.
        
        Args:
            lines: List of buffer lines
            current_line: Current cursor line (1-indexed)
            delimiter_pattern: Regex pattern for cell delimiters
            
        Returns:
            list: List of cell code strings
        """
        if not lines:
            return []

        # Convert to 0-indexed
        current_line_idx = current_line - 1
        if current_line_idx >= len(lines):
            current_line_idx = len(lines) - 1

        # Find start of current cell
        current_cell_start = 0
        for i in range(current_line_idx, -1, -1):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                if i == current_line_idx:
                    # If we're on a delimiter, current cell starts at next line
                    current_cell_start = i + 1
                else:
                    # Found previous delimiter, current cell starts after it
                    current_cell_start = i + 1
                break

        # Find all cell delimiters before current cell
        cell_starts = [0]  # Buffer always starts a cell
        for i in range(current_cell_start):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                cell_starts.append(i + 1)  # Cell starts after delimiter

        # Extract cells
        cells = []
        for i in range(len(cell_starts)):
            start = cell_starts[i]
            end = cell_starts[i + 1] - 1 if i + 1 < len(cell_starts) else current_cell_start
            
            if start < end:
                cell_lines = lines[start:end]
                # Remove empty lines at beginning and end
                while cell_lines and not cell_lines[0].strip():
                    cell_lines.pop(0)
                while cell_lines and not cell_lines[-1].strip():
                    cell_lines.pop()
                
                if cell_lines:
                    cells.append('\n'.join(cell_lines))

        return cells

    def _extract_cells_below(self, lines, current_line, delimiter_pattern):
        """
        Extract all cell codes from current cell to end of buffer.
        
        Args:
            lines: List of buffer lines
            current_line: Current cursor line (1-indexed)
            delimiter_pattern: Regex pattern for cell delimiters
            
        Returns:
            list: List of cell code strings
        """
        if not lines:
            return []

        # Convert to 0-indexed
        current_line_idx = current_line - 1
        if current_line_idx >= len(lines):
            current_line_idx = len(lines) - 1

        # Find start of current cell
        current_cell_start = 0
        for i in range(current_line_idx, -1, -1):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                if i == current_line_idx:
                    # If we're on a delimiter, current cell starts at next line
                    current_cell_start = i + 1
                else:
                    # Found previous delimiter, current cell starts after it
                    current_cell_start = i + 1
                break

        # Find all cell delimiters from current position to end
        cell_starts = [current_cell_start]
        for i in range(current_cell_start, len(lines)):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                cell_starts.append(i + 1)  # Cell starts after delimiter

        # Extract cells
        cells = []
        for i in range(len(cell_starts)):
            start = cell_starts[i]
            end = cell_starts[i + 1] - 1 if i + 1 < len(cell_starts) else len(lines)
            
            if start < end:
                cell_lines = lines[start:end]
                # Remove empty lines at beginning and end
                while cell_lines and not cell_lines[0].strip():
                    cell_lines.pop(0)
                while cell_lines and not cell_lines[-1].strip():
                    cell_lines.pop()
                
                if cell_lines:
                    cells.append('\n'.join(cell_lines))

        return cells

    def _extract_all_cells(self, lines, delimiter_pattern):
        """
        Extract all cell codes from the entire buffer.
        
        Args:
            lines: List of buffer lines
            delimiter_pattern: Regex pattern for cell delimiters
            
        Returns:
            list: List of cell code strings
        """
        if not lines:
            return []

        # Find all cell delimiters
        cell_starts = [0]  # Buffer always starts a cell
        for i, line in enumerate(lines):
            if re.match(delimiter_pattern, line.strip()):
                cell_starts.append(i + 1)  # Cell starts after delimiter

        # Extract cells
        cells = []
        for i in range(len(cell_starts)):
            start = cell_starts[i]
            end = cell_starts[i + 1] - 1 if i + 1 < len(cell_starts) else len(lines)
            
            if start < end:
                cell_lines = lines[start:end]
                # Remove empty lines at beginning and end
                while cell_lines and not cell_lines[0].strip():
                    cell_lines.pop(0)
                while cell_lines and not cell_lines[-1].strip():
                    cell_lines.pop()
                
                if cell_lines:
                    cells.append('\n'.join(cell_lines))

        return cells

    # Keep the original HelloWorld command for backward compatibility
    @pynvim.command('HelloWorld', sync=True)
    def hello_world_command(self):
        """
        Simple hello world command for testing plugin loading.
        """
        self.nvim.out_write("Hello, world from Quench plugin!\n")

    @pynvim.command('QuenchDebug', sync=True)
    def debug_command(self):
        """
        Debug command to test plugin functionality and show diagnostics.
        """
        try:
            self._logger.info("QuenchDebug called")
            self.nvim.out_write("=== Quench Debug Info ===\n")
            
            # Test logging
            self.nvim.out_write("✓ Plugin loaded and responding\n")
            self._logger.info("Debug command executed successfully")
            
            # Test buffer access
            try:
                current_bnum = self.nvim.current.buffer.number
                current_line = self.nvim.current.window.cursor[0]
                self.nvim.out_write(f"✓ Buffer access: buffer {current_bnum}, line {current_line}\n")
            except Exception as e:
                self.nvim.out_write(f"✗ Buffer access failed: {e}\n")
            
            # Test dependencies
            try:
                import jupyter_client
                self.nvim.out_write("✓ jupyter_client available\n")
            except ImportError:
                self.nvim.out_write("✗ jupyter_client not available\n")
                
            try:
                import aiohttp
                self.nvim.out_write("✓ aiohttp available\n")
            except ImportError:
                self.nvim.out_write("✗ aiohttp not available\n")
            
            # Test async functionality
            try:
                import asyncio
                self.nvim.out_write("✓ asyncio available\n")
                try:
                    loop = asyncio.get_event_loop()
                    self.nvim.out_write(f"✓ Event loop: {type(loop).__name__}\n")
                except RuntimeError:
                    self.nvim.out_write("✗ No event loop found\n")
            except Exception as e:
                self.nvim.out_write(f"✗ Asyncio test failed: {e}\n")
                
            self.nvim.out_write("=== End Debug Info ===\n")
            
        except Exception as e:
            self._logger.error(f"Error in QuenchDebug: {e}")
            self.nvim.err_write(f"Debug error: {e}\n")

    @pynvim.command('QuenchInterruptKernel', sync=True)
    def interrupt_kernel_command(self):
        """
        Send an interrupt signal to the kernel associated with the current buffer.
        """
        try:
            self._logger.info("QuenchInterruptKernel called")
            
            # Get current buffer number
            try:
                current_bnum = self.nvim.current.buffer.number
            except Exception as e:
                self._logger.error(f"Error getting buffer number: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return
            
            # Run async operation
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._interrupt_kernel_async(current_bnum))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Interrupt task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Interrupt failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._interrupt_kernel_async(current_bnum))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._interrupt_kernel_async(current_bnum))
            except Exception as e:
                self._logger.error(f"Error in _interrupt_kernel_async: {e}")
                self._notify_user(f"Interrupt failed: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchInterruptKernel: {e}")
            self.nvim.err_write(f"Interrupt kernel error: {e}\n")

    @pynvim.command('QuenchResetKernel', sync=True)
    def reset_kernel_command(self):
        """
        Restart the kernel associated with the current buffer and clear its state.
        """
        try:
            self._logger.info("QuenchResetKernel called")
            
            # Get current buffer number
            try:
                current_bnum = self.nvim.current.buffer.number
            except Exception as e:
                self._logger.error(f"Error getting buffer number: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return
            
            # Run async operation
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._reset_kernel_async(current_bnum))
                        
                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Reset task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Kernel reset failed: {task.exception()}", level='error'))
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._reset_kernel_async(current_bnum))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._reset_kernel_async(current_bnum))
            except Exception as e:
                self._logger.error(f"Error in _reset_kernel_async: {e}")
                self._notify_user(f"Kernel reset failed: {e}", level='error')
                
        except Exception as e:
            self._logger.error(f"Error in QuenchResetKernel: {e}")
            self.nvim.err_write(f"Reset kernel error: {e}\n")

    def _select_from_choices_sync(self, choices, prompt_title):
        """
        Helper method to present choices to user and get their selection.

        Args:
            choices: List of choice dictionaries with 'display_name' and 'value' keys
            prompt_title: Title to display to the user

        Returns:
            The selected choice dictionary or None if cancelled/failed
        """
        if not choices:
            self._notify_user("No choices available", level='error')
            return None

        if len(choices) == 1:
            return choices[0]

        # Create display choices with numbers
        display_choices = [f"{i+1}. {choice['display_name']}" for i, choice in enumerate(choices)]
        self.nvim.out_write(f"{prompt_title}:\n" + "\n".join(display_choices) + "\n")

        # Get user input
        choice_input = self.nvim.call('input', 'Enter selection number: ')

        try:
            choice_idx = int(choice_input) - 1
            if 0 <= choice_idx < len(choices):
                return choices[choice_idx]
            else:
                self._notify_user("Invalid selection", level='error')
                return None
        except (ValueError, IndexError):
            self._notify_user("Invalid input. Selection cancelled.", level='error')
            return None

    @pynvim.command("QuenchStartKernel", sync=True)
    def start_kernel_command(self):
        """
        Start a new kernel not attached to any buffers.
        """
        try:
            self._logger.info("QuenchStartKernel called")

            # Get available kernelspecs
            try:
                kernelspecs = self.kernel_manager.discover_kernelspecs()
                if not kernelspecs:
                    self._notify_user("No Jupyter kernels found. Please install ipykernel.", level='error')
                    return

                # Convert to choices format
                choices = [{'display_name': spec['display_name'], 'value': spec['name']} for spec in kernelspecs]
                selected_choice = self._select_from_choices_sync(choices, "Select a kernel to start")

                if not selected_choice:
                    return

                kernel_choice = selected_choice['value']

            except Exception as e:
                self._logger.error(f"Error discovering kernels: {e}")
                self._notify_user(f"Error discovering kernels: {e}", level='error')
                return

            # Start the kernel asynchronously
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._start_kernel_async(kernel_choice))

                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Start kernel task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Failed to start kernel: {task.exception()}", level='error'))
                                except:
                                    pass

                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._start_kernel_async(kernel_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._start_kernel_async(kernel_choice))
            except Exception as e:
                self._logger.error(f"Error starting kernel: {e}")
                self._notify_user(f"Failed to start kernel: {e}", level='error')

        except Exception as e:
            self._logger.error(f"Error in QuenchStartKernel: {e}")
            self._notify_user(f"Start kernel error: {e}", level='error')

    @pynvim.command("QuenchShutdownKernel", sync=True)
    def shutdown_kernel_command(self):
        """
        Shutdown a running kernel and detach any buffers that are linked to it.
        """
        try:
            self._logger.info("QuenchShutdownKernel called")

            # Get running kernels
            try:
                running_kernels = self.kernel_manager.list_sessions()
                if not running_kernels:
                    self._notify_user("No running kernels to shut down.")
                    return

                # Convert to choices format
                choices = []
                for kernel_id, session_info in running_kernels.items():
                    choices.append({
                        'display_name': f"{session_info['kernel_name']} ({session_info['short_id']}) - {len(session_info['associated_buffers'])} buffers",
                        'value': kernel_id
                    })

                selected_choice = self._select_from_choices_sync(choices, "Select a kernel to shut down")

                if not selected_choice:
                    return

                kernel_id = selected_choice['value']

            except Exception as e:
                self._logger.error(f"Error listing kernels: {e}")
                self._notify_user(f"Error listing kernels: {e}", level='error')
                return

            # Shutdown the kernel asynchronously
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._shutdown_kernel_async(kernel_id))

                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Shutdown kernel task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Failed to shut down kernel: {task.exception()}", level='error'))
                                except:
                                    pass

                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._shutdown_kernel_async(kernel_id))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._shutdown_kernel_async(kernel_id))
            except Exception as e:
                self._logger.error(f"Error shutting down kernel: {e}")
                self._notify_user(f"Failed to shut down kernel: {e}", level='error')

        except Exception as e:
            self._logger.error(f"Error in QuenchShutdownKernel: {e}")
            self._notify_user(f"Shutdown kernel error: {e}", level='error')

    @pynvim.command("QuenchSelectKernel", sync=True)
    def select_kernel_command(self):
        """
        Select a kernel for the current buffer. Can attach to running kernels or start new ones.
        """
        try:
            self._logger.info("QuenchSelectKernel called")

            # Get current buffer number
            try:
                current_bnum = self.nvim.current.buffer.number
            except Exception as e:
                self._logger.error(f"Error getting buffer number: {e}")
                self._notify_user(f"Error accessing buffer: {e}", level='error')
                return

            # Get kernel choices (running kernels first for this command)
            try:
                choices = self.kernel_manager.get_kernel_choices(running_first=True)
                if not choices:
                    self._notify_user("No kernels available. Please install ipykernel.", level='error')
                    return

                selected_choice = self._select_from_choices_sync(choices, "Select a kernel for this buffer")

                if not selected_choice:
                    return

            except Exception as e:
                self._logger.error(f"Error getting kernel choices: {e}")
                self._notify_user(f"Error getting kernel choices: {e}", level='error')
                return

            # Handle selection asynchronously
            try:
                # Try to get or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task in existing loop
                        task = asyncio.create_task(self._select_kernel_async(current_bnum, selected_choice))

                        # Add error callback to the task
                        def handle_task_exception(task):
                            if task.exception():
                                self._logger.error(f"Select kernel task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Failed to select kernel: {task.exception()}", level='error'))
                                except:
                                    pass

                        task.add_done_callback(handle_task_exception)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._select_kernel_async(current_bnum, selected_choice))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._select_kernel_async(current_bnum, selected_choice))
            except Exception as e:
                self._logger.error(f"Error selecting kernel: {e}")
                self._notify_user(f"Failed to select kernel: {e}", level='error')

        except Exception as e:
            self._logger.error(f"Error in QuenchSelectKernel: {e}")
            self._notify_user(f"Select kernel error: {e}", level='error')

    async def _start_kernel_async(self, kernel_choice):
        """
        Async implementation for starting a new unattached kernel.

        Args:
            kernel_choice: Name of the kernel to start
        """
        self._logger.debug(f"Starting new unattached kernel: {kernel_choice}")

        try:
            session = await self.kernel_manager.start_session(self.relay_queue, kernel_name=kernel_choice)

            def notify_success():
                self._notify_user(f"Started new kernel: {session.kernel_name} ({session.kernel_id[:8]})")

            try:
                self.nvim.async_call(notify_success)
            except:
                pass

        except Exception as e:
            self._logger.error(f"Failed to start kernel: {e}")
            raise

    async def _shutdown_kernel_async(self, kernel_id):
        """
        Async implementation for shutting down a kernel.

        Args:
            kernel_id: ID of the kernel to shutdown
        """
        self._logger.debug(f"Shutting down kernel: {kernel_id[:8]}")

        try:
            await self.kernel_manager.shutdown_session(kernel_id)

            def notify_success():
                self._notify_user(f"Kernel {kernel_id[:8]} shut down successfully")

            try:
                self.nvim.async_call(notify_success)
            except:
                pass

        except Exception as e:
            self._logger.error(f"Failed to shutdown kernel: {e}")
            raise

    async def _select_kernel_async(self, bnum, selected_choice):
        """
        Async implementation for selecting a kernel for a buffer.

        Args:
            bnum: Buffer number
            selected_choice: Choice dictionary with 'value' and 'is_running' keys
        """
        self._logger.debug(f"Selecting kernel for buffer {bnum}: {selected_choice}")

        async with self._cleanup_lock:
            # Recreate web server if it was destroyed
            if self.web_server is None:
                self._logger.info("Recreating WebServer instance.")
                # Use cached host and port if available, otherwise get from config
                host = getattr(self, '_cached_web_server_host', None) or self._get_web_server_host()
                port = getattr(self, '_cached_web_server_port', None) or self._get_web_server_port()
                self.web_server = WebServer(
                    host=host,
                    port=port,
                    nvim=self.nvim,
                    kernel_manager=self.kernel_manager
                )

            # Start web server if not already running
            if not self.web_server_started:
                try:
                    await self.web_server.start()
                    self.web_server_started = True

                    server_url = f"http://{self.web_server.host}:{self.web_server.port}"
                    def notify_server_started():
                        self._notify_user(f"Quench web server started at {server_url}")

                    try:
                        self.nvim.async_call(notify_server_started)
                    except Exception:
                        self._logger.info(f"Web server started at {server_url}")

                except Exception as e:
                    self._logger.error(f"Failed to start web server: {e}")
                    try:
                        self.nvim.async_call(lambda err=e: self._notify_user(f"Error starting web server: {err}", level='error'))
                    except Exception:
                        pass

        # Start message relay loop if not running
        if self.message_relay_task is None or self.message_relay_task.done():
            self.message_relay_task = asyncio.create_task(self._message_relay_loop())
            self._logger.info("Started message relay loop")

        try:
            if selected_choice['is_running']:
                # Attach to existing kernel
                kernel_id = selected_choice['value']
                await self.kernel_manager.attach_buffer_to_session(bnum, kernel_id)

                def notify_success():
                    self._notify_user(f"Buffer attached to running kernel {kernel_id[:8]}")

                try:
                    self.nvim.async_call(notify_success)
                except:
                    pass
            else:
                # Start a new kernel and attach
                kernel_choice_value = selected_choice['value']
                try:
                    buffer_name = self.nvim.current.buffer.name or f"buffer_{bnum}"
                    if buffer_name:
                        import os
                        buffer_name = os.path.basename(buffer_name)
                except:
                    buffer_name = f"buffer_{bnum}"

                # For "New:" selections, always create a new session
                session = await self.kernel_manager.start_session(self.relay_queue, buffer_name, kernel_choice_value)
                # Attach the buffer to the new session
                await self.kernel_manager.attach_buffer_to_session(bnum, session.kernel_id)

                def notify_success():
                    self._notify_user(f"Started new kernel {session.kernel_id[:8]} and attached to buffer")

                try:
                    self.nvim.async_call(notify_success)
                except:
                    pass

        except Exception as e:
            self._logger.error(f"Failed to select kernel: {e}")
            raise

    @pynvim.function('SayHello', sync=True)
    def say_hello_function(self, args):
        """
        Simple function for testing plugin functionality.
        """
        name = args[0] if args else 'stranger'
        return f"Hello, {name}!"
