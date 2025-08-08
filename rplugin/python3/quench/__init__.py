import asyncio
import logging
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
            host="127.0.0.1", 
            port=8765, 
            nvim=nvim,
            kernel_manager=self.kernel_manager
        )
        
        # Task management
        self.message_relay_task: Optional[asyncio.Task] = None
        self.web_server_started = False
        
        self._logger.info("Quench plugin initialized")

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

    @pynvim.function("QuenchRunCell", sync=False)
    async def run_cell(self, args):
        """
        Execute the current cell in IPython kernel.
        
        This is the main function users will call to execute Python code cells.
        """
        try:
            self._logger.info("QuenchRunCell called")
            
            # Get current buffer and line number
            current_bnum = await self.ui_manager.get_current_bnum()
            current_line = self.nvim.current.window.cursor[0]  # 1-indexed
            
            self._logger.debug(f"Current buffer: {current_bnum}, line: {current_line}")
            
            # Extract cell code
            cell_code = await self.ui_manager.get_cell_code(current_bnum, current_line)
            
            if not cell_code.strip():
                self.nvim.out_write("No code found in current cell\n")
                return
            
            self._logger.debug(f"Cell code extracted: {len(cell_code)} characters")
            
            # Start web server if not already running
            if not self.web_server_started:
                try:
                    await self.web_server.start()
                    self.web_server_started = True
                    
                    # Show web server info to user
                    server_url = f"http://{self.web_server.host}:{self.web_server.port}"
                    self.nvim.out_write(f"Quench web server started at {server_url}\n")
                    
                except Exception as e:
                    self._logger.error(f"Failed to start web server: {e}")
                    self.nvim.err_write(f"Error starting web server: {e}\n")
                    # Continue without web server
            
            # Get or create kernel session for this buffer
            session = await self.kernel_manager.get_or_create_session(
                current_bnum, 
                self.relay_queue
            )
            
            # Start message relay loop if not running
            if self.message_relay_task is None or self.message_relay_task.done():
                self.message_relay_task = asyncio.create_task(self._message_relay_loop())
                self._logger.info("Started message relay loop")
            
            # Execute the code
            self._logger.info(f"Executing cell code in kernel {session.kernel_id[:8]}")
            await session.execute(cell_code)
            
            # Show execution feedback to user
            if self.web_server_started:
                kernel_url = f"http://{self.web_server.host}:{self.web_server.port}?kernel_id={session.kernel_id}"
                self.nvim.out_write(f"Code executed - view output at: {kernel_url}\n")
            else:
                self.nvim.out_write("Code executed - check output buffer\n")
                
        except Exception as e:
            self._logger.error(f"Error in QuenchRunCell: {e}")
            self.nvim.err_write(f"Quench error: {e}\n")

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
            if msg_type == 'stream':
                # Handle stdout/stderr output
                stream_name = content.get('name', 'stdout')
                text = content.get('text', '')
                
                if text.strip():
                    # Write to Neovim command line for immediate feedback
                    self.nvim.out_write(f"[{stream_name}] {text}")
                    
            elif msg_type == 'execute_result':
                # Handle execution results
                data = content.get('data', {})
                if 'text/plain' in data:
                    result_text = data['text/plain']
                    if isinstance(result_text, list):
                        result_text = '\n'.join(result_text)
                    
                    if result_text.strip():
                        self.nvim.out_write(f"[result] {result_text}\n")
                        
            elif msg_type == 'error':
                # Handle errors
                error_name = content.get('ename', 'Error')
                error_value = content.get('evalue', '')
                
                error_msg = f"[error] {error_name}: {error_value}\n"
                self.nvim.err_write(error_msg)
                
            elif msg_type == 'execute_input':
                # Show what code was executed
                code = content.get('code', '')
                if code.strip():
                    # Show first few lines of executed code
                    code_lines = code.split('\n')
                    preview = code_lines[0]
                    if len(code_lines) > 1:
                        preview += f" ... ({len(code_lines)} lines)"
                    
                    self.nvim.out_write(f"[executing] {preview}\n")
                    
        except Exception as e:
            self._logger.warning(f"Error handling message for Neovim: {e}")

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

    # Keep the original HelloWorld command for backward compatibility
    @pynvim.command('HelloWorld', sync=True)
    def hello_world_command(self):
        """
        Simple hello world command for testing plugin loading.
        """
        self.nvim.out_write("Hello, world from Quench plugin!\n")

    @pynvim.function('SayHello', sync=True)
    def say_hello_function(self, args):
        """
        Simple function for testing plugin functionality.
        """
        name = args[0] if args else 'stranger'
        return f"Hello, {name}!"