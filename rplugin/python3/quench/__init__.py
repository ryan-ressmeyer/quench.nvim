import asyncio
import logging
logging.basicConfig(filename="/tmp/quench.log", level=logging.DEBUG)
import re
from typing import Optional

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
        self.web_server = WebServer(
            host=self._get_web_server_host(), 
            port=self._get_web_server_port(), 
            nvim=nvim,
            kernel_manager=self.kernel_manager
        )
        
        # Task management
        self.message_relay_task: Optional[asyncio.Task] = None
        self.web_server_started = False
        
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
        Handle Vim exit - clean up all resources.
        
        This method is called synchronously when Neovim is shutting down.
        """
        self._logger.info("Vim leaving - starting cleanup")
        
        # Run cleanup in asyncio context
        try:
            # Create new event loop if none exists
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run the async cleanup
            loop.run_until_complete(self._cleanup())
            
        except Exception as e:
            self._logger.error(f"Error during cleanup: {e}")
        finally:
            self._logger.info("Cleanup completed")

    async def _cleanup(self):
        """
        Async cleanup method to shut down all components gracefully.
        """
        self._logger.info("Starting async cleanup")
        
        # Cancel message relay task
        if self.message_relay_task and not self.message_relay_task.done():
            self.message_relay_task.cancel()
            try:
                await self.message_relay_task
            except asyncio.CancelledError:
                pass
        
        # Stop web server
        if self.web_server_started:
            try:
                await self.web_server.stop()
            except Exception as e:
                self._logger.error(f"Error stopping web server: {e}")
        
        # Shutdown all kernel sessions
        try:
            await self.kernel_manager.shutdown_all_sessions()
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
                kernel_name = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_name:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_name}")
                
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
                        task = asyncio.create_task(self._run_cell_async(current_bnum, cell_code, kernel_name))
                        
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
                        loop.run_until_complete(self._run_cell_async(current_bnum, cell_code, kernel_name))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, cell_code, kernel_name))
                    
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
        """
        # Check for an existing session
        if bnum in self.kernel_manager.buffer_to_kernel_map:
            kernel_id = self.kernel_manager.buffer_to_kernel_map[bnum]
            if kernel_id in self.kernel_manager.sessions:
                return self.kernel_manager.sessions[kernel_id].kernel_name

        # Discover kernels and prompt for selection
        try:
            kernelspecs = self.kernel_manager.discover_kernelspecs()
            if not kernelspecs:
                self.nvim.err_write("No Jupyter kernels found. Please install ipykernel.\n")
                return None

            if len(kernelspecs) == 1:
                return kernelspecs[0]['name']

            # Create choices for the user
            choices = [f"{i+1}. {spec['display_name']}" for i, spec in enumerate(kernelspecs)]
            self.nvim.out_write("Please select a kernel:\n" + "\n".join(choices) + "\n")
            
            # Get user input
            choice = self.nvim.call('input', 'Enter kernel number: ')
            
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(kernelspecs):
                    return kernelspecs[choice_idx]['name']
            except (ValueError, IndexError):
                self.nvim.err_write("Invalid selection. Using the default kernel.\n")
                return kernelspecs[0]['name']

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

    async def _run_cell_async(self, current_bnum, cell_code, kernel_name):
        """
        Async implementation of cell execution.
        Takes pre-collected data to avoid Neovim API calls from wrong thread.
        
        Args:
            current_bnum: Buffer number
            cell_code: Code to execute
            kernel_name: Name of the kernel to use
        """
        self._logger.debug(f"Starting async execution for buffer {current_bnum}")
        
        # Start web server if not already running
        if not self.web_server_started:
            try:
                await self.web_server.start()
                self.web_server_started = True
                
                # Show web server info to user (use async_call for thread safety)
                server_url = f"http://{self.web_server.host}:{self.web_server.port}"
                def notify_server_started():
                    self._notify_user(f"Quench web server started at {server_url}")
                
                try:
                    self.nvim.async_call(notify_server_started)
                except:
                    # If async_call fails, just log it
                    self._logger.info(f"Web server started at {server_url}")
                
            except Exception as e:
                self._logger.error(f"Failed to start web server: {e}")
                def notify_error():
                    self._notify_user(f"Error starting web server: {e}", level='error')
                try:
                    self.nvim.async_call(notify_error)
                except:
                    pass
                # Continue without web server
        
        
        # Get or create kernel session for this buffer
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
            kernel_name
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
        try:
            self.nvim.out_write("Stopping Quench components...\n")
            
            # Run cleanup
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            loop.run_until_complete(self._cleanup())
            self.web_server_started = False
            
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
            
            # Select kernel synchronously
            try:
                kernel_name = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_name:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_name}")
                
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
                        task = asyncio.create_task(self._run_cell_async(current_bnum, cell_code, kernel_name))
                        
                        # Add callback to advance cursor after execution
                        def handle_task_and_advance(task):
                            if task.exception():
                                self._logger.error(f"Background task failed: {task.exception()}")
                                try:
                                    self.nvim.async_call(lambda: self._notify_user(f"Execution failed: {task.exception()}", level='error'))
                                except:
                                    pass
                            else:
                                # Advance cursor to line following cell end
                                def advance_cursor():
                                    try:
                                        advance_to_line = cell_end_line + 1 if cell_end_line < len(lines) else len(lines)
                                        self.nvim.current.window.cursor = (advance_to_line, 0)
                                    except Exception as e:
                                        self._logger.error(f"Error advancing cursor: {e}")
                                
                                try:
                                    self.nvim.async_call(advance_cursor)
                                except:
                                    pass
                        
                        task.add_done_callback(handle_task_and_advance)
                    else:
                        # Run in existing loop
                        loop.run_until_complete(self._run_cell_async(current_bnum, cell_code, kernel_name))
                        # Advance cursor after execution
                        advance_to_line = cell_end_line + 1 if cell_end_line < len(lines) else len(lines)
                        self.nvim.current.window.cursor = (advance_to_line, 0)
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, cell_code, kernel_name))
                    # Advance cursor after execution
                    advance_to_line = cell_end_line + 1 if cell_end_line < len(lines) else len(lines)
                    self.nvim.current.window.cursor = (advance_to_line, 0)
                    
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
                kernel_name = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_name:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_name}")
                
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
                        task = asyncio.create_task(self._run_cell_async(current_bnum, selected_code, kernel_name))
                        
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
                        loop.run_until_complete(self._run_cell_async(current_bnum, selected_code, kernel_name))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, selected_code, kernel_name))
                    
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
                kernel_name = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_name:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_name}")
                
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
                        task = asyncio.create_task(self._run_cell_async(current_bnum, current_line_code, kernel_name))
                        
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
                        loop.run_until_complete(self._run_cell_async(current_bnum, current_line_code, kernel_name))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, current_line_code, kernel_name))
                    
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
                kernel_name = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_name:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_name}")
                
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
                        task = asyncio.create_task(self._run_cell_async(current_bnum, combined_code, kernel_name))
                        
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
                        loop.run_until_complete(self._run_cell_async(current_bnum, combined_code, kernel_name))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, combined_code, kernel_name))
                    
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
                kernel_name = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_name:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_name}")
                
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
                        task = asyncio.create_task(self._run_cell_async(current_bnum, combined_code, kernel_name))
                        
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
                        loop.run_until_complete(self._run_cell_async(current_bnum, combined_code, kernel_name))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, combined_code, kernel_name))
                    
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
                kernel_name = self._get_or_select_kernel_sync(current_bnum)
                if not kernel_name:
                    self._notify_user("Kernel selection failed. Aborting execution.", level='error')
                    return
                
                self._logger.info(f"Using kernel: {kernel_name}")
                
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
                        task = asyncio.create_task(self._run_cell_async(current_bnum, combined_code, kernel_name))
                        
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
                        loop.run_until_complete(self._run_cell_async(current_bnum, combined_code, kernel_name))
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(self._run_cell_async(current_bnum, combined_code, kernel_name))
                    
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

    @pynvim.function('SayHello', sync=True)
    def say_hello_function(self, args):
        """
        Simple function for testing plugin functionality.
        """
        name = args[0] if args else 'stranger'
        return f"Hello, {name}!"
