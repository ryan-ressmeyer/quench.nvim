import asyncio
import uuid
import logging
import json
import sys
import subprocess
from typing import Optional, Dict, Set, List

try:
    from jupyter_client import AsyncKernelManager, AsyncKernelClient
    JUPYTER_CLIENT_AVAILABLE = True
except ImportError:
    # Graceful fallback if jupyter_client is not installed
    AsyncKernelManager = None
    AsyncKernelClient = None
    JUPYTER_CLIENT_AVAILABLE = False


class KernelSession:
    """
    Represents a single, running IPython kernel and its associated state.
    """

    def __init__(self, relay_queue: asyncio.Queue, buffer_name: str = None, kernel_name: str = None):
        """
        Initialize a new kernel session.

        Args:
            relay_queue: The central asyncio.Queue for broadcasting messages
            buffer_name: Optional human-readable name for the session
            kernel_name: Optional kernel name to use (defaults to 'python3')
        """
        self.kernel_id: str = str(uuid.uuid4())
        self.km: Optional[AsyncKernelManager] = None
        self.client: Optional[AsyncKernelClient] = None
        self.output_cache: list = []
        self.relay_queue: asyncio.Queue = relay_queue
        self.associated_buffers: Set[int] = set()
        self.listener_task: Optional[asyncio.Task] = None
        self.buffer_name = buffer_name or f"kernel_{self.kernel_id[:8]}"
        self.kernel_name = kernel_name or 'python3'
        self.python_executable = sys.executable
        self.created_at = __import__('datetime').datetime.now()
        self._logger = logging.getLogger(f"quench.kernel.{self.kernel_id[:8]}")
        
        # Track kernel busy/idle state for cell status indicators
        self.is_busy = False
        self.pending_executions: Dict[str, str] = {}  # msg_id -> status

    async def start(self, kernel_name: str = None):
        """
        Start the kernel and establish communication channels.
        
        Args:
            kernel_name: Optional kernel name to override the instance default
        """
        if not JUPYTER_CLIENT_AVAILABLE:
            self._logger.error("jupyter_client import failed - AsyncKernelManager/AsyncKernelClient not available")
            raise RuntimeError("jupyter_client is not installed or imports failed. Please install it to use kernel functionality.")

        try:
            # Use provided kernel_name or fall back to instance default
            effective_kernel_name = kernel_name or self.kernel_name
            
            # Create and start the kernel manager
            self.km = AsyncKernelManager(kernel_name=effective_kernel_name)
            await self.km.start_kernel()  # This IS async in jupyter_client 8.x

            # Create the client and start channels
            self.client = self.km.client()
            self.client.start_channels()  # This is synchronous

            # Wait for the client to be fully ready (this IS async)
            await self.client.wait_for_ready(timeout=30)

            # Start the IOPub listener task
            self.listener_task = asyncio.create_task(self._listen_iopub())
            
            self._logger.info(f"Kernel {self.kernel_id[:8]} (type: {effective_kernel_name}) started successfully")

        except Exception as e:
            self._logger.error(f"Failed to start kernel {self.kernel_id[:8]}: {e}")
            await self.shutdown()
            raise

    async def shutdown(self):
        """
        Safely shut down the kernel and clean up resources with timeouts.
        """
        self._logger.info(f"Shutting down kernel {self.kernel_id[:8]}")

        # 1. Prioritize shutting down the actual kernel process.
        if self.km:
            try:
                self._logger.info(f"Sending shutdown signal to kernel {self.kernel_id[:8]}")
                await asyncio.wait_for(self.km.shutdown_kernel(now=True), timeout=2.0)
                self._logger.info(f"Kernel {self.kernel_id[:8]} shut down successfully.")
            except asyncio.TimeoutError:
                self._logger.warning(f"Timeout shutting down kernel {self.kernel_id[:8]}. It may be orphaned.")
            except Exception as e:
                self._logger.error(f"Error during kernel shutdown for {self.kernel_id[:8]}: {e}")

        # 2. Cancel the listener task.
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await asyncio.wait_for(self.listener_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                self._logger.warning(f"Listener task for {self.kernel_id[:8]} had an error on cleanup: {e}")

        # 3. Clean up references.
        self.client = None
        self.km = None
        self.listener_task = None


    async def _send_cell_status(self, msg_id: str, status: str):
        """
        Send a cell status update message to the frontend.
        
        Args:
            msg_id: The original execute request message ID
            status: One of 'queued', 'running', 'completed_ok', 'completed_error'
        """
        from datetime import datetime, timezone
        status_message = {
            'header': {
                'msg_id': f"status_{msg_id}_{status}_{datetime.now(timezone.utc).isoformat()}",
                'msg_type': 'quench_cell_status',
                'username': 'quench',
                'session': self.kernel_id,
                'date': datetime.now(timezone.utc),
                'version': '5.3'
            },
            'msg_type': 'quench_cell_status',
            'parent_header': {
                'msg_id': msg_id,
                'msg_type': 'execute_request',
                'username': 'quench',
                'session': self.kernel_id,
                'date': datetime.now(timezone.utc),
                'version': '5.3'
            },
            'content': {
                'status': status
            },
            'metadata': {},
            'buffers': []
        }
        
        # Add to cache and relay
        self.output_cache.append(status_message)
        await self.relay_queue.put((self.kernel_id, status_message))
        self._logger.debug(f"Sent cell status '{status}' for msg_id {msg_id[:8]}")

    async def execute(self, code: str):
        """
        Send code to the kernel's shell channel for execution.

        Args:
            code: The Python code to execute
        """
        if not self.client:
            raise RuntimeError("Kernel client is not available. Call start() first.")

        try:
            # First, get the msg_id that will be generated
            msg_id = self.client.execute(code)
            self._logger.debug(f"Executed code in kernel {self.kernel_id[:8]}, msg_id: {msg_id}")
            
            # Create a synthetic execute_input message for the frontend using the actual execute request ID
            # This ensures the frontend has a cell to attach output to, using the same ID that output messages will reference
            from datetime import datetime, timezone
            execute_input_msg = {
                'header': {
                    'msg_id': f"synthetic_{msg_id}",  # Use a different ID for the execute_input message itself
                    'msg_type': 'execute_input',
                    'username': 'quench',
                    'session': self.kernel_id,
                    'date': datetime.now(timezone.utc),
                    'version': '5.3'
                },
                'msg_id': f"synthetic_{msg_id}",
                'msg_type': 'execute_input',
                'parent_header': {
                    'msg_id': msg_id,  # This is the key - output messages will reference this ID
                    'msg_type': 'execute_request',
                    'username': 'quench',
                    'session': self.kernel_id,
                    'date': datetime.now(timezone.utc),
                    'version': '5.3'
                },
                'metadata': {},
                'content': {
                    'code': code,
                    'execution_count': None
                },
                'buffers': []
            }
            
            self._logger.debug(f"Creating synthetic execute_input with parent_msg_id: {msg_id}")
            
            # Add to cache and relay immediately
            self.output_cache.append(execute_input_msg)
            await self.relay_queue.put((self.kernel_id, execute_input_msg))
            self._logger.debug(f"Created synthetic execute_input message for kernel {self.kernel_id[:8]}")
            
            # Now send status messages after the cell has been created
            # Track this execution and send queued status
            self.pending_executions[msg_id] = 'queued'
            await self._send_cell_status(msg_id, 'queued')
            
            # Wait for kernel to be available if it's busy
            while self.is_busy:
                await asyncio.sleep(0.1)
            
            # Send running status when execution begins
            if msg_id in self.pending_executions:
                self.pending_executions[msg_id] = 'running'
                await self._send_cell_status(msg_id, 'running')
            
            return msg_id
        except Exception as e:
            self._logger.error(f"Error executing code in kernel {self.kernel_id[:8]}: {e}")
            raise

    async def interrupt(self):
        """
        Send an interrupt signal to the running kernel.
        """
        if not self.km:
            raise RuntimeError("Kernel manager is not available. Call start() first.")
        
        try:
            await self.km.interrupt_kernel()
            self._logger.info(f"Interrupted kernel {self.kernel_id[:8]}")
        except Exception as e:
            self._logger.error(f"Error interrupting kernel {self.kernel_id[:8]}: {e}")
            raise

    async def restart(self):
        """
        Restart the kernel and clear the output cache.
        Sends a notification to the frontend about the restart.
        """
        if not self.km:
            raise RuntimeError("Kernel manager is not available. Call start() first.")
        
        try:
            self._logger.info(f"Restarting kernel {self.kernel_id[:8]}")
            
            # Restart the kernel
            await self.km.restart_kernel()
            
            # Clear the output cache to remove previous state
            self.output_cache.clear()
            
            # Create a custom message for the frontend
            from datetime import datetime, timezone
            restart_message = {
                "header": {
                    "msg_id": f"restart_{self.kernel_id}_{datetime.now(timezone.utc).isoformat()}",
                    "msg_type": "kernel_restarted",
                    "username": "quench",
                    "session": self.kernel_id,
                    "date": datetime.now(timezone.utc),
                    "version": "5.3"
                },
                "msg_type": "kernel_restarted",
                "content": {"status": "ok"},
                "metadata": {},
                "buffers": []
            }
            
            # Add the message to the relay queue
            await self.relay_queue.put((self.kernel_id, restart_message))
            
            self._logger.info(f"Kernel {self.kernel_id[:8]} restarted successfully")
            
        except Exception as e:
            self._logger.error(f"Error restarting kernel {self.kernel_id[:8]}: {e}")
            raise

    async def _listen_iopub(self):
        """
        Continuously listen to the kernel's IOPub channel for messages.
        Appends messages to output_cache and forwards them to the relay_queue.
        """
        if not self.client:
            return

        try:
            self._logger.info(f"Started IOPub listener for kernel {self.kernel_id[:8]}")
            
            while True:
                try:
                    # Wait for messages from the IOPub channel
                    message = await self.client.get_iopub_msg(timeout=1.0)
                    
                    # Skip execute_input messages since we create our own synthetic ones
                    # This prevents duplicate cells in the frontend
                    if message.get('msg_type') == 'execute_input':
                        self._logger.debug(f"Skipping real execute_input message from kernel {self.kernel_id[:8]}")
                        continue
                    
                    # Handle kernel status messages to track busy/idle state
                    if message.get('msg_type') == 'status':
                        execution_state = message.get('content', {}).get('execution_state')
                        if execution_state == 'busy':
                            self.is_busy = True
                            self._logger.debug(f"Kernel {self.kernel_id[:8]} is now busy")
                        elif execution_state == 'idle':
                            self.is_busy = False
                            self._logger.debug(f"Kernel {self.kernel_id[:8]} is now idle")
                            
                            # Check if this corresponds to a completed execution
                            parent_msg_id = message.get('parent_header', {}).get('msg_id')
                            if parent_msg_id and parent_msg_id in self.pending_executions:
                                # Assume successful completion unless we've seen an error
                                # We'll handle errors in the error message handler
                                await self._send_cell_status(parent_msg_id, 'completed_ok')
                                del self.pending_executions[parent_msg_id]
                    
                    # Handle error messages to mark cells as completed with error
                    elif message.get('msg_type') == 'error':
                        parent_msg_id = message.get('parent_header', {}).get('msg_id')
                        if parent_msg_id and parent_msg_id in self.pending_executions:
                            await self._send_cell_status(parent_msg_id, 'completed_error')
                            del self.pending_executions[parent_msg_id]
                    
                    # Append to output cache
                    self.output_cache.append(message)
                    
                    # Forward to central relay queue
                    await self.relay_queue.put((self.kernel_id, message))
                    
                    self._logger.debug(f"Relayed message from kernel {self.kernel_id[:8]}: {message.get('msg_type', 'unknown')}")

                except asyncio.TimeoutError:
                    # Timeout is expected, continue listening
                    continue
                except Exception as e:
                    # Log other errors but continue listening
                    error_msg = str(e) if e else "Unknown error"
                    
                    # Don't spam logs with Empty exceptions - they're normal timeouts
                    if "Empty" not in error_msg and e.__class__.__name__ != 'Empty':
                        self._logger.warning(f"Error receiving IOPub message from kernel {self.kernel_id[:8]}: {error_msg}")
                        
                        # Add more detailed error info for non-Empty errors
                        if hasattr(e, '__class__'):
                            self._logger.debug(f"Exception type: {e.__class__.__name__}")
                        
                        import traceback
                        self._logger.debug(f"Exception traceback: {traceback.format_exc()}")
                    continue

        except asyncio.CancelledError:
            self._logger.info(f"IOPub listener cancelled for kernel {self.kernel_id[:8]}")
            raise
        except Exception as e:
            self._logger.error(f"IOPub listener failed for kernel {self.kernel_id[:8]}: {e}")
        finally:
            self._logger.info(f"IOPub listener stopped for kernel {self.kernel_id[:8]}")


class KernelSessionManager:
    """
    A singleton that manages all active KernelSession instances.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.sessions: Dict[str, KernelSession] = {}
            self.buffer_to_kernel_map: Dict[int, str] = {}
            self._logger = logging.getLogger("quench.kernel_manager")
            KernelSessionManager._initialized = True

    async def start_session(self, relay_queue: asyncio.Queue, buffer_name: str = None, kernel_name: str = None) -> KernelSession:
        """
        Starts a new kernel session without attaching it to a buffer.

        Args:
            relay_queue: The central message relay queue
            buffer_name: Optional human-readable name for the session
            kernel_name: Optional kernel name to use (defaults to 'python3')

        Returns:
            KernelSession: The newly created session
        """
        session = KernelSession(relay_queue, buffer_name, kernel_name)
        try:
            await session.start()
            self.sessions[session.kernel_id] = session
            self._logger.info(f"Started new unattached session {session.kernel_id[:8]} ({session.buffer_name})")
            return session
        except Exception as e:
            self._logger.error(f"Failed to start session: {e}")
            raise

    async def shutdown_session(self, kernel_id: str):
        """
        Shuts down a specific kernel session and detaches all associated buffers.

        Args:
            kernel_id: ID of the kernel session to shutdown
        """
        if kernel_id in self.sessions:
            session = self.sessions[kernel_id]
            await session.shutdown()
            del self.sessions[kernel_id]

            # Detach any buffers attached to this session
            buffers_to_detach = [bnum for bnum, kid in self.buffer_to_kernel_map.items() if kid == kernel_id]
            for bnum in buffers_to_detach:
                del self.buffer_to_kernel_map[bnum]

            self._logger.info(f"Shut down session {kernel_id[:8]} and detached {len(buffers_to_detach)} buffers.")
        else:
            raise ValueError(f"Session {kernel_id} does not exist")

    def get_kernel_choices(self, running_first: bool = True):
        """
        Returns a list of dictionaries for user selection, combining running kernels and new kernelspecs.

        Args:
            running_first: If True, running kernels are listed first; otherwise new kernels first

        Returns:
            List[Dict]: List of kernel choices with display_name, value, and is_running fields
        """
        choices = []
        running_kernels = []
        for kernel_id, session in self.sessions.items():
            running_kernels.append({
                'display_name': f"Running: {session.kernel_name} ({kernel_id[:8]})",
                'value': kernel_id,
                'is_running': True
            })

        new_kernels = []
        kernelspecs = self.discover_kernelspecs()
        for spec in kernelspecs:
            new_kernels.append({
                'display_name': f"New: {spec['display_name']}",
                'value': spec['name'],
                'is_running': False
            })

        if running_first:
            choices.extend(running_kernels)
            choices.extend(new_kernels)
        else:
            choices.extend(new_kernels)
            choices.extend(running_kernels)

        return choices

    async def get_or_create_session(self, bnum: int, relay_queue: asyncio.Queue, buffer_name: str = None, kernel_name: str = None) -> KernelSession:
        """
        Get an existing session for a buffer or create a new one.

        Args:
            bnum: Buffer number
            relay_queue: The central message relay queue
            buffer_name: Optional human-readable name for the session
            kernel_name: Optional kernel name to use (defaults to 'python3')

        Returns:
            KernelSession: The session associated with the buffer
        """
        # Check if buffer already has a session
        if bnum in self.buffer_to_kernel_map:
            kernel_id = self.buffer_to_kernel_map[bnum]
            if kernel_id in self.sessions:
                self._logger.debug(f"Returning existing session for buffer {bnum}")
                return self.sessions[kernel_id]

        # Create a new session using start_session
        session = await self.start_session(relay_queue, buffer_name, kernel_name)
        self.buffer_to_kernel_map[bnum] = session.kernel_id
        session.associated_buffers.add(bnum)

        self._logger.info(f"Attached new session {session.kernel_id[:8]} to buffer {bnum}")
        return session

    async def attach_buffer_to_session(self, bnum: int, kernel_id: str):
        """
        Attach a buffer to an existing session.

        Args:
            bnum: Buffer number
            kernel_id: ID of the kernel session
        """
        if kernel_id not in self.sessions:
            raise ValueError(f"Session {kernel_id} does not exist")

        session = self.sessions[kernel_id]
        session.associated_buffers.add(bnum)
        self.buffer_to_kernel_map[bnum] = kernel_id
        
        self._logger.info(f"Attached buffer {bnum} to session {kernel_id[:8]}")

    async def get_session_for_buffer(self, bnum: int) -> Optional[KernelSession]:
        """
        Get the session associated with a buffer.

        Args:
            bnum: Buffer number

        Returns:
            KernelSession or None: The associated session, if any
        """
        if bnum not in self.buffer_to_kernel_map:
            return None

        kernel_id = self.buffer_to_kernel_map[bnum]
        return self.sessions.get(kernel_id)

    async def shutdown_all_sessions(self):
        """
        Shut down all active kernel sessions concurrently.
        """
        if not self.sessions:
            self._logger.info("No sessions to shutdown")
            return

        self._logger.info(f"Shutting down {len(self.sessions)} sessions")
        
        # Shutdown all sessions concurrently
        shutdown_tasks = [session.shutdown() for session in self.sessions.values()]
        
        try:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        except Exception as e:
            self._logger.error(f"Error during session shutdown: {e}")
        finally:
            # Clean up data structures
            self.sessions.clear()
            self.buffer_to_kernel_map.clear()
            self._logger.info("All sessions shutdown complete")

    def list_sessions(self) -> Dict[str, Dict]:
        """
        Get information about all active sessions.

        Returns:
            Dict: Session information including associated buffers
        """
        result = {}
        for kernel_id, session in self.sessions.items():
            result[kernel_id] = {
                'kernel_id': kernel_id,
                'name': session.buffer_name,
                'kernel_name': session.kernel_name,
                'python_executable': session.python_executable,
                'short_id': kernel_id[:8],
                'created_at': session.created_at.isoformat() if hasattr(session, 'created_at') else None,
                'associated_buffers': list(session.associated_buffers),
                'output_cache_size': len(session.output_cache),
                'is_alive': session.listener_task is not None and not session.listener_task.done()
            }
        return result

    def discover_kernelspecs(self) -> List[Dict[str, str]]:
        """
        Discover all available kernel specifications on the system.

        Returns:
            List[Dict]: List of kernel specifications, each containing:
                - name: Internal kernel name
                - display_name: Human-readable name
                - argv: Command line arguments for starting the kernel
        """
        kernelspecs = []
        
        try:
            # Use jupyter_client to discover kernels instead of subprocess
            from jupyter_client.kernelspec import KernelSpecManager
            ksm = KernelSpecManager()
            available_kernels = ksm.find_kernel_specs()
            
            # Get kernel specs for each available kernel
            for kernel_name in available_kernels.keys():
                try:
                    spec = ksm.get_kernel_spec(kernel_name)
                    kernelspecs.append({
                        'name': kernel_name,
                        'display_name': spec.display_name,
                        'argv': spec.argv
                    })
                except Exception as e:
                    self._logger.warning(f"Failed to get spec for kernel {kernel_name}: {e}")
                    continue
        
        except Exception as e:
            self._logger.error(f"Failed to discover kernels using jupyter_client: {e}")
            self._logger.error("Please ensure jupyter_client is installed: pip install jupyter_client")
            raise
        
        self._logger.info(f"Discovered {len(kernelspecs)} kernel specifications")
        
        # If no kernels found, log a helpful message
        if not kernelspecs:
            self._logger.warning("No Jupyter kernel specifications found. Make sure ipykernel is installed.")
            self._logger.info("To install: pip install ipykernel && python -m ipykernel install --user")
        
        return kernelspecs
