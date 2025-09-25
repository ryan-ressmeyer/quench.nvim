import asyncio
import logging
logging.basicConfig(filename="/tmp/quench.log", level=logging.DEBUG)
from typing import Optional 

import pynvim

# Import all the components we've built
from .kernel_session import KernelSessionManager
from .web_server import WebServer
from .ui_manager import NvimUIManager

# Import utilities
from .utils.notifications import notify_user, select_from_choices_sync

# Import core modules
from .core.config import get_web_server_host, get_web_server_port
from .core.async_executor import AsyncExecutor 

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
        self._cached_web_server_host = get_web_server_host(nvim, self._logger)
        self._cached_web_server_port = get_web_server_port(nvim, self._logger)
        
        self.web_server = WebServer(
            host=self._cached_web_server_host, 
            port=self._cached_web_server_port, 
            nvim=nvim,
            kernel_manager=self.kernel_manager
        )
        
        # Initialize async executor
        self.async_executor = AsyncExecutor(nvim, self._logger)

        # Task management
        self.message_relay_task: Optional[asyncio.Task] = None
        self.web_server_started = False
        self._cleanup_lock = asyncio.Lock()  # Lock to manage cleanup process

        self._logger.info("Quench plugin initialized")

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
                    # Notify clients before shutting down kernel sessions
                    if self.web_server and self.web_server_started:
                        await self.web_server.broadcast_kernel_update()
                    await self.kernel_manager.shutdown_all_sessions()
                    self._logger.info("All kernel sessions shut down.")
                except Exception as e:
                    self._logger.error(f"Error shutting down kernel sessions: {e}")

            self._logger.info("Async cleanup completed")


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

            selected_choice = select_from_choices_sync(self.nvim, choices, "Please select a kernel")

            if not selected_choice:
                # Fallback to first available choice
                selected_choice = choices[0]

            return selected_choice

        except Exception as e:
            self._logger.error(f"Error during kernel selection: {e}")
            self.nvim.err_write(f"Error selecting kernel: {e}\n")

        return None


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
                self._logger.info("Creating WebServer instance.")
                # Use cached host and port if available, otherwise get from config
                host = getattr(self, '_cached_web_server_host', None) or get_web_server_host(self.nvim, self._logger)
                port = getattr(self, '_cached_web_server_port', None) or get_web_server_port(self.nvim, self._logger)
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
                        notify_user(self.nvim, f"Quench web server started at {server_url}")
                    
                    try:
                        self.nvim.async_call(notify_server_started)
                    except Exception:
                        self._logger.info(f"Web server started at {server_url}")
                    
                except Exception as e:
                    self._logger.error(f"Failed to start web server: {e}")
                    try:
                        self.nvim.async_call(lambda err=e: notify_user(self.nvim, f"Error starting web server: {err}", level='error'))
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

            # Notify clients of kernel list changes
            if self.web_server and self.web_server_started:
                await self.web_server.broadcast_kernel_update()
        
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
                notify_user(self.nvim, "No active kernel session found for this buffer", level='error')
            
            try:
                self.nvim.async_call(notify_no_session)
            except:
                pass
            return
        
        try:
            await session.interrupt()
            
            def notify_success():
                notify_user(self.nvim, f"Kernel interrupted successfully")
            
            try:
                self.nvim.async_call(notify_success)
            except:
                pass
                
        except Exception as e:
            self._logger.error(f"Failed to interrupt kernel: {e}")
            def notify_error():
                notify_user(self.nvim, f"Failed to interrupt kernel: {e}", level='error')
            
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
                notify_user(self.nvim, "No active kernel session found for this buffer", level='error')
            
            try:
                self.nvim.async_call(notify_no_session)
            except:
                pass
            return
        
        try:
            await session.restart()
            
            def notify_success():
                notify_user(self.nvim, f"Kernel reset successfully - all variables and state cleared")
            
            try:
                self.nvim.async_call(notify_success)
            except:
                pass
                
        except Exception as e:
            self._logger.error(f"Failed to reset kernel: {e}")
            def notify_error():
                notify_user(self.nvim, f"Failed to reset kernel: {e}", level='error')
            
            try:
                self.nvim.async_call(notify_error)
            except:
                pass




















    async def _start_kernel_async(self, kernel_choice):
        """
        Async implementation for starting a new unattached kernel.

        Args:
            kernel_choice: Name of the kernel to start
        """
        self._logger.debug(f"Starting new unattached kernel: {kernel_choice}")

        async with self._cleanup_lock:
            # Recreate web server if it was destroyed
            if self.web_server is None:
                self._logger.info("Recreating WebServer instance.")
                # Use cached host and port if available, otherwise get from config
                host = getattr(self, '_cached_web_server_host', None) or get_web_server_host(self.nvim, self._logger)
                port = getattr(self, '_cached_web_server_port', None) or get_web_server_port(self.nvim, self._logger)
                self.web_server = WebServer(
                    host=host,
                    port=port,
                    nvim=self.nvim,
                    kernel_manager=self.kernel_manager
                )

            # Start web server if not already running
            if not self.web_server_started:
                try:
                    self._logger.info("Starting web server from QuenchStartKernel")
                    await self.web_server.start()
                    self.web_server_started = True

                    server_url = f"http://{self.web_server.host}:{self.web_server.port}"
                    def notify_server_started():
                        notify_user(self.nvim, f"Quench web server started at {server_url}")

                    try:
                        self.nvim.async_call(notify_server_started)
                    except Exception:
                        self._logger.info(f"Web server started at {server_url}")

                except Exception as e:
                    self._logger.error(f"Failed to start web server: {e}")
                    try:
                        self.nvim.async_call(lambda err=e: notify_user(self.nvim, f"Error starting web server: {err}", level='error'))
                    except Exception:
                        pass

        # Start message relay loop if not running
        if self.message_relay_task is None or self.message_relay_task.done():
            self._logger.info("Starting message relay loop from QuenchStartKernel")
            self.message_relay_task = asyncio.create_task(self._message_relay_loop())
            self._logger.info("Started message relay loop from QuenchStartKernel")

        try:
            session = await self.kernel_manager.start_session(self.relay_queue, kernel_name=kernel_choice)

            def notify_success():
                notify_user(self.nvim, f"Started new kernel: {session.kernel_name} ({session.kernel_id[:8]})")

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
                notify_user(self.nvim, f"Kernel {kernel_id[:8]} shut down successfully")

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
                host = getattr(self, '_cached_web_server_host', None) or get_web_server_host(self.nvim, self._logger)
                port = getattr(self, '_cached_web_server_port', None) or get_web_server_port(self.nvim, self._logger)
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
                        notify_user(self.nvim, f"Quench web server started at {server_url}")

                    try:
                        self.nvim.async_call(notify_server_started)
                    except Exception:
                        self._logger.info(f"Web server started at {server_url}")

                except Exception as e:
                    self._logger.error(f"Failed to start web server: {e}")
                    try:
                        self.nvim.async_call(lambda err=e: notify_user(self.nvim, f"Error starting web server: {err}", level='error'))
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
                    notify_user(self.nvim, f"Buffer attached to running kernel {kernel_id[:8]}")

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
                    notify_user(self.nvim, f"Started new kernel {session.kernel_id[:8]} and attached to buffer")

                try:
                    self.nvim.async_call(notify_success)
                except:
                    pass

        except Exception as e:
            self._logger.error(f"Failed to select kernel: {e}")
            raise

    # Debug Commands
    @pynvim.command('QuenchStatus', sync=True)
    def status_command(self):
        """
        Show status of Quench plugin components.
        """
        from .commands.debug import status_command_impl
        return status_command_impl(self)

    @pynvim.command('QuenchStop', sync=True)
    def stop_command(self):
        """
        Stop all Quench components.
        """
        self.nvim.out_write("Stopping Quench components...\n")
        try:
            # Use the same async cleanup pattern as VimLeave
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(self._async_cleanup(), loop)
            self.nvim.out_write("Quench cleanup scheduled.\n")
        except RuntimeError:
            # No running loop - this shouldn't happen in normal pynvim context
            self.nvim.err_write("No async event loop available for cleanup.\n")
        except Exception as e:
            self._logger.error(f"Error in QuenchStop: {e}")
            self.nvim.err_write(f"Stop error: {e}\n")

    @pynvim.command('QuenchDebug', sync=True)
    def debug_command(self):
        """
        Debug command to test plugin functionality and show diagnostics.
        """
        from .commands.debug import debug_command_impl
        return debug_command_impl(self)

    # Kernel Management Commands
    @pynvim.command('QuenchInterruptKernel', sync=True)
    def interrupt_kernel_command(self):
        """
        Send an interrupt signal to the kernel associated with the current buffer.
        """
        self._logger.info("QuenchInterruptKernel called")

        # Synchronous UI operations (get current buffer number)
        try:
            current_bnum = self.nvim.current.buffer.number
        except Exception as e:
            self._logger.error(f"Error getting buffer number: {e}")
            notify_user(self.nvim, f"Error accessing buffer: {e}", level='error')
            return

        # Asynchronous backend operations (kernel interruption)
        return self.async_executor.execute_sync(self._interrupt_kernel_async(current_bnum), "kernel interruption")

    @pynvim.command('QuenchResetKernel', sync=True)
    def reset_kernel_command(self):
        """
        Restart the kernel associated with the current buffer and clear its state.
        """
        self._logger.info("QuenchResetKernel called")

        # Synchronous UI operations (get current buffer number)
        try:
            current_bnum = self.nvim.current.buffer.number
        except Exception as e:
            self._logger.error(f"Error getting buffer number: {e}")
            notify_user(self.nvim, f"Error accessing buffer: {e}", level='error')
            return

        # Asynchronous backend operations (kernel reset)
        return self.async_executor.execute_sync(self._reset_kernel_async(current_bnum), "kernel reset")

    @pynvim.command('QuenchStartKernel', sync=True)
    def start_kernel_command(self):
        """
        Start a new kernel not attached to any buffers.
        """
        self._logger.info("QuenchStartKernel called")

        # Synchronous UI operations (kernel discovery and selection)
        try:
            kernelspecs = self.kernel_manager.discover_kernelspecs()
            if not kernelspecs:
                notify_user(self.nvim, "No Jupyter kernels found. Please install ipykernel.", level='error')
                return

            # Convert to choices format
            choices = [{'display_name': spec['display_name'], 'value': spec['name']} for spec in kernelspecs]
            selected_choice = select_from_choices_sync(self.nvim, choices, "Select a kernel to start")

            if not selected_choice:
                return

            kernel_choice = selected_choice['value']

        except Exception as e:
            self._logger.error(f"Error discovering kernels: {e}")
            notify_user(self.nvim, f"Error discovering kernels: {e}", level='error')
            return

        # Asynchronous backend operations (kernel startup)
        return self.async_executor.execute_sync(self._start_kernel_async(kernel_choice), "kernel start")

    @pynvim.command('QuenchShutdownKernel', sync=True)
    def shutdown_kernel_command(self):
        """
        Shutdown a running kernel and detach any buffers that are linked to it.
        """
        self._logger.info("QuenchShutdownKernel called")

        # Synchronous UI operations (list running kernels and get user selection)
        try:
            running_kernels = self.kernel_manager.list_sessions()
            if not running_kernels:
                notify_user(self.nvim, "No running kernels to shut down.")
                return

            # Convert to choices format
            choices = []
            for kernel_id, session_info in running_kernels.items():
                choices.append({
                    'display_name': f"{session_info['kernel_name']} ({session_info['short_id']}) - {len(session_info['associated_buffers'])} buffers",
                    'value': kernel_id
                })

            selected_choice = select_from_choices_sync(self.nvim, choices, "Select a kernel to shut down")

            if not selected_choice:
                return

            kernel_id = selected_choice['value']

        except Exception as e:
            self._logger.error(f"Error listing kernels: {e}")
            notify_user(self.nvim, f"Error listing kernels: {e}", level='error')
            return

        # Asynchronous backend operations (kernel shutdown)
        return self.async_executor.execute_sync(self._shutdown_kernel_async(kernel_id), "kernel shutdown")

    @pynvim.command('QuenchSelectKernel', sync=True)
    def select_kernel_command(self):
        """
        Select a kernel for the current buffer. Can attach to running kernels or start new ones.
        """
        self._logger.info("QuenchSelectKernel called")

        # Synchronous UI operations (get current buffer and present kernel choices)
        try:
            current_bnum = self.nvim.current.buffer.number
        except Exception as e:
            self._logger.error(f"Error getting buffer number: {e}")
            notify_user(self.nvim, f"Error accessing buffer: {e}", level='error')
            return

        # Get kernel choices (running kernels first for this command)
        try:
            choices = self.kernel_manager.get_kernel_choices(running_first=True)
            if not choices:
                notify_user(self.nvim, "No kernels available. Please install ipykernel.", level='error')
                return

            selected_choice = select_from_choices_sync(self.nvim, choices, "Select a kernel for this buffer")

            if not selected_choice:
                return

        except Exception as e:
            self._logger.error(f"Error getting kernel choices: {e}")
            notify_user(self.nvim, f"Error getting kernel choices: {e}", level='error')
            return

        # Asynchronous backend operations (handle kernel selection/attachment)
        return self.async_executor.execute_sync(self._select_kernel_async(current_bnum, selected_choice), "kernel selection")

    # ================================================================
    # Execution Commands (wrappers around implementation functions)
    # ================================================================

    @pynvim.command('QuenchRunCell', sync=True)
    def run_cell(self):
        """
        Execute the current cell in IPython kernel.
        """
        from .commands.execution import run_cell_impl
        return self.async_executor.execute_sync(run_cell_impl(self), "cell execution")

    @pynvim.command('QuenchRunCellAdvance', sync=True)
    def run_cell_advance(self):
        """
        Execute the current cell and advance cursor to the next cell.
        """
        from .commands.execution import run_cell_advance_impl
        return self.async_executor.execute_sync(run_cell_advance_impl(self), "cell execution and advance")

    @pynvim.command('QuenchRunSelection', range=True, sync=True)
    def run_selection(self, range_info):
        """
        Execute the current selection in IPython kernel.
        """
        from .commands.execution import run_selection_impl
        return self.async_executor.execute_sync(run_selection_impl(self, range_info), "selection execution")

    @pynvim.command('QuenchRunLine', sync=True)
    def run_line(self):
        """
        Execute the current line in IPython kernel.
        """
        from .commands.execution import run_line_impl
        return self.async_executor.execute_sync(run_line_impl(self), "line execution")

    @pynvim.command('QuenchRunAbove', sync=True)
    def run_above(self):
        """
        Execute all cells above the current cursor position.
        """
        from .commands.execution import run_above_impl
        return self.async_executor.execute_sync(run_above_impl(self), "cells above execution")

    @pynvim.command('QuenchRunBelow', sync=True)
    def run_below(self):
        """
        Execute all cells below the current cursor position.
        """
        from .commands.execution import run_below_impl
        return self.async_executor.execute_sync(run_below_impl(self), "cells below execution")

    @pynvim.command('QuenchRunAll', sync=True)
    def run_all(self):
        """
        Execute all cells in the current buffer.
        """
        from .commands.execution import run_all_impl
        return self.async_executor.execute_sync(run_all_impl(self), "all cells execution")
