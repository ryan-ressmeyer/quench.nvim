import asyncio
import uuid
import logging
from typing import Optional, Dict, Set

try:
    from jupyter_client import AsyncKernelManager
    from jupyter_client.asyncioclient import AsyncKernelClient
except ImportError:
    # Graceful fallback if jupyter_client is not installed
    AsyncKernelManager = None
    AsyncKernelClient = None


class KernelSession:
    """
    Represents a single, running IPython kernel and its associated state.
    """

    def __init__(self, relay_queue: asyncio.Queue):
        """
        Initialize a new kernel session.

        Args:
            relay_queue: The central asyncio.Queue for broadcasting messages
        """
        self.kernel_id: str = str(uuid.uuid4())
        self.km: Optional[AsyncKernelManager] = None
        self.client: Optional[AsyncKernelClient] = None
        self.output_cache: list = []
        self.relay_queue: asyncio.Queue = relay_queue
        self.associated_buffers: Set[int] = set()
        self.listener_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger(f"quench.kernel.{self.kernel_id[:8]}")

    async def start(self):
        """
        Start the kernel and establish communication channels.
        """
        if AsyncKernelManager is None:
            raise RuntimeError("jupyter_client is not installed. Please install it to use kernel functionality.")

        try:
            # Create and start the kernel manager
            self.km = AsyncKernelManager(kernel_name='python3')
            await self.km.start_kernel()

            # Create the client and start channels
            self.client = self.km.client()
            await self.client.start_channels()

            # Wait for the client to be fully ready
            await self.client.wait_for_ready(timeout=30)

            # Start the IOPub listener task
            self.listener_task = asyncio.create_task(self._listen_iopub())
            
            self._logger.info(f"Kernel {self.kernel_id[:8]} started successfully")

        except Exception as e:
            self._logger.error(f"Failed to start kernel {self.kernel_id[:8]}: {e}")
            await self.shutdown()
            raise

    async def shutdown(self):
        """
        Safely shut down the kernel and clean up resources.
        """
        self._logger.info(f"Shutting down kernel {self.kernel_id[:8]}")

        # Cancel the listener task
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass

        # Stop client channels
        if self.client:
            try:
                self.client.stop_channels()
            except Exception as e:
                self._logger.warning(f"Error stopping client channels: {e}")

        # Shutdown the kernel
        if self.km:
            try:
                await self.km.shutdown_kernel()
            except Exception as e:
                self._logger.warning(f"Error shutting down kernel: {e}")

        # Clean up references
        self.client = None
        self.km = None
        self.listener_task = None

    async def execute(self, code: str):
        """
        Send code to the kernel's shell channel for execution.

        Args:
            code: The Python code to execute
        """
        if not self.client:
            raise RuntimeError("Kernel client is not available. Call start() first.")

        try:
            # Send the code for execution
            msg_id = self.client.execute(code)
            self._logger.debug(f"Executed code in kernel {self.kernel_id[:8]}, msg_id: {msg_id}")
            return msg_id
        except Exception as e:
            self._logger.error(f"Error executing code in kernel {self.kernel_id[:8]}: {e}")
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
                    self._logger.warning(f"Error receiving IOPub message from kernel {self.kernel_id[:8]}: {e}")
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

    async def get_or_create_session(self, bnum: int, relay_queue: asyncio.Queue) -> KernelSession:
        """
        Get an existing session for a buffer or create a new one.

        Args:
            bnum: Buffer number
            relay_queue: The central message relay queue

        Returns:
            KernelSession: The session associated with the buffer
        """
        # Check if buffer already has a session
        if bnum in self.buffer_to_kernel_map:
            kernel_id = self.buffer_to_kernel_map[bnum]
            if kernel_id in self.sessions:
                self._logger.debug(f"Returning existing session for buffer {bnum}")
                return self.sessions[kernel_id]

        # Create a new session
        session = KernelSession(relay_queue)
        
        try:
            await session.start()
            
            # Store the session and map the buffer
            self.sessions[session.kernel_id] = session
            self.buffer_to_kernel_map[bnum] = session.kernel_id
            session.associated_buffers.add(bnum)
            
            self._logger.info(f"Created new session {session.kernel_id[:8]} for buffer {bnum}")
            return session
            
        except Exception as e:
            self._logger.error(f"Failed to create session for buffer {bnum}: {e}")
            raise

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
                'associated_buffers': list(session.associated_buffers),
                'output_cache_size': len(session.output_cache),
                'is_alive': session.listener_task is not None and not session.listener_task.done()
            }
        return result