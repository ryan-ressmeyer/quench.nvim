import asyncio
import uuid
import logging
import json
import sys
import subprocess
from typing import Optional, Dict, Set, List
from dataclasses import dataclass

try:
    from jupyter_client import AsyncKernelManager, AsyncKernelClient

    JUPYTER_CLIENT_AVAILABLE = True
except ImportError:
    # Graceful fallback if jupyter_client is not installed
    AsyncKernelManager = None
    AsyncKernelClient = None
    JUPYTER_CLIENT_AVAILABLE = False


@dataclass
class ExecutionRequest:
    """Represents a queued cell execution request."""

    msg_id: str
    code: str
    future: asyncio.Future
    sequence_num: int  # For message ordering


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
        self.monitor_task: Optional[asyncio.Task] = None
        self.buffer_name = buffer_name or f"kernel_{self.kernel_id[:8]}"
        self.kernel_name = kernel_name or "python3"
        self.python_executable = sys.executable
        self.created_at = __import__("datetime").datetime.now()
        self._logger = logging.getLogger(f"quench.kernel.{self.kernel_id[:8]}")

        # New queue-based execution system
        self.execution_queue: asyncio.Queue = asyncio.Queue()
        self.current_execution: Optional[ExecutionRequest] = None
        self.executor_task: Optional[asyncio.Task] = None
        self.msg_id_map: Dict[str, str] = {}  # Maps kernel msg_id → our msg_id
        self.sequence_counter: int = 0  # For message ordering
        self.is_interrupting: bool = False  # Track interrupt state
        self._idle_waiter: Optional[asyncio.Future] = None  # For waiting on kernel idle

        # Track kernel death state for auto-restart functionality
        self.is_dead = False

    async def start(self, kernel_name: str = None):
        """
        Start the kernel and establish communication channels.

        Args:
            kernel_name: Optional kernel name to override the instance default
        """
        if not JUPYTER_CLIENT_AVAILABLE:
            self._logger.error("jupyter_client import failed - AsyncKernelManager/AsyncKernelClient not available")
            raise RuntimeError(
                "jupyter_client is not installed or imports failed. Please install it to use kernel functionality."
            )

        try:
            # Cancel any existing tasks before restarting (important for auto-restart after death)
            if self.listener_task and not self.listener_task.done():
                self.listener_task.cancel()
                try:
                    await asyncio.wait_for(self.listener_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            if self.monitor_task and not self.monitor_task.done():
                self.monitor_task.cancel()
                try:
                    await asyncio.wait_for(self.monitor_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            if self.executor_task and not self.executor_task.done():
                self.executor_task.cancel()
                try:
                    await asyncio.wait_for(self.executor_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            # Use provided kernel_name or fall back to instance default
            effective_kernel_name = kernel_name or self.kernel_name

            # Create and start the kernel manager
            self.km = AsyncKernelManager(kernel_name=effective_kernel_name)
            await self.km.start_kernel()  # This IS async in jupyter_client 8.x

            # Create the client and start channels
            self.client = self.km.client()
            self.client.start_channels()  # This is synchronous

            # Broadcast 'starting' status immediately to frontend
            # This provides immediate visual feedback that the kernel is launching
            from datetime import datetime, timezone

            starting_msg = {
                "header": {
                    "msg_id": f"starting_{self.kernel_id}_{datetime.now(timezone.utc).isoformat()}",
                    "msg_type": "status",
                    "username": "quench",
                    "session": self.kernel_id,
                    "date": datetime.now(timezone.utc),
                    "version": "5.3",
                },
                "msg_type": "status",
                "content": {"execution_state": "starting"},
                "metadata": {},
                "buffers": [],
            }
            # Add to cache so it's replayed when frontend reconnects
            self.output_cache.append(starting_msg)
            await self.relay_queue.put((self.kernel_id, starting_msg))
            self._logger.debug(f"Broadcast 'starting' status for kernel {self.kernel_id[:8]}")

            # Wait for the client to be fully ready (this IS async)
            await self.client.wait_for_ready(timeout=30)

            # Start the IOPub listener task
            self.listener_task = asyncio.create_task(self._listen_iopub())

            # Start the process monitoring task
            self.monitor_task = asyncio.create_task(self._monitor_process())

            # Start the execution loop task
            self.executor_task = asyncio.create_task(self._execution_loop())
            self._logger.debug(f"Started execution loop for kernel {self.kernel_id[:8]}")

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

        # 3. Cancel the monitor task.
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await asyncio.wait_for(self.monitor_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                self._logger.warning(f"Monitor task for {self.kernel_id[:8]} had an error on cleanup: {e}")

        # 4. Cancel the executor task.
        if self.executor_task and not self.executor_task.done():
            self.executor_task.cancel()
            try:
                await asyncio.wait_for(self.executor_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                self._logger.warning(f"Executor task for {self.kernel_id[:8]} had an error on cleanup: {e}")

        # 5. Clean up references.
        self.client = None
        self.km = None
        self.listener_task = None
        self.monitor_task = None
        self.executor_task = None

    async def _send_cell_status(self, msg_id: str, status: str):
        """
        Send a cell status update message to the frontend with sequence number for ordering.

        Args:
            msg_id: The original execute request message ID
            status: One of 'queued', 'running', 'completed_ok', 'completed_error', 'skipped'
        """
        from datetime import datetime, timezone

        status_message = {
            "header": {
                "msg_id": f"status_{msg_id}_{status}_{datetime.now(timezone.utc).isoformat()}",
                "msg_type": "quench_cell_status",
                "username": "quench",
                "session": self.kernel_id,
                "date": datetime.now(timezone.utc),
                "version": "5.3",
            },
            "msg_type": "quench_cell_status",
            "parent_header": {
                "msg_id": msg_id,
                "msg_type": "execute_request",
                "username": "quench",
                "session": self.kernel_id,
                "date": datetime.now(timezone.utc),
                "version": "5.3",
            },
            "content": {
                "status": status,
                "sequence": self.sequence_counter,  # Add sequence number for message ordering
            },
            "metadata": {},
            "buffers": [],
        }

        self.sequence_counter += 1

        # Add status messages to cache so they can be replayed when frontend reconnects
        self.output_cache.append(status_message)
        await self.relay_queue.put((self.kernel_id, status_message))
        self._logger.debug(
            f"Sent cell status '{status}' for msg_id {msg_id[:8]} (seq {status_message['content']['sequence']})"
        )

    async def execute(self, code: str) -> str:
        """
        Queue code for execution. Returns immediately with msg_id.
        Actual execution happens serially in _execution_loop.

        Args:
            code: The Python code to execute

        Returns:
            str: The message ID for tracking this execution
        """
        # Auto-restart kernel if it has died
        if self.is_dead:
            self._logger.info(f"Kernel {self.kernel_id[:8]} is dead, auto-restarting before execution")

            try:
                # Restart the kernel
                await self.start(self.kernel_name)

                # Mark kernel as no longer dead
                self.is_dead = False

                # Send notification to frontend and Neovim
                from datetime import datetime, timezone

                auto_restart_msg = {
                    "header": {
                        "msg_id": f"auto_restart_{self.kernel_id}_{datetime.now(timezone.utc).isoformat()}",
                        "msg_type": "kernel_auto_restarted",
                        "username": "quench",
                        "session": self.kernel_id,
                        "date": datetime.now(timezone.utc),
                        "version": "5.3",
                    },
                    "msg_type": "kernel_auto_restarted",
                    "content": {"status": "ok", "reason": "Auto-restarted after kernel death"},
                    "metadata": {},
                    "buffers": [],
                }

                # Add to cache and relay
                self.output_cache.append(auto_restart_msg)
                await self.relay_queue.put((self.kernel_id, auto_restart_msg))

                self._logger.info(f"Kernel {self.kernel_id[:8]} auto-restarted successfully")
            except Exception as e:
                self._logger.error(f"Failed to auto-restart kernel {self.kernel_id[:8]}: {e}")
                raise RuntimeError(f"Failed to auto-restart kernel: {e}")

        if not self.client:
            raise RuntimeError("Kernel client is not available. Call start() first.")

        # Generate our own msg_id (kernel will generate its own later)
        msg_id = uuid.uuid4().hex

        # Create synthetic execute_input message immediately
        from datetime import datetime, timezone

        execute_input_msg = {
            "header": {
                "msg_id": f"synthetic_{msg_id}",
                "msg_type": "execute_input",
                "username": "quench",
                "session": self.kernel_id,
                "date": datetime.now(timezone.utc),
                "version": "5.3",
            },
            "msg_id": f"synthetic_{msg_id}",
            "msg_type": "execute_input",
            "parent_header": {
                "msg_id": msg_id,
                "msg_type": "execute_request",
                "username": "quench",
                "session": self.kernel_id,
                "date": datetime.now(timezone.utc),
                "version": "5.3",
            },
            "metadata": {},
            "content": {"code": code, "execution_count": None},
            "buffers": [],
        }

        # Send execute_input to frontend immediately
        self.output_cache.append(execute_input_msg)
        await self.relay_queue.put((self.kernel_id, execute_input_msg))

        # Send "queued" status immediately
        await self._send_cell_status(msg_id, "queued")

        # Create execution request with Future
        req = ExecutionRequest(msg_id=msg_id, code=code, future=asyncio.Future(), sequence_num=self.sequence_counter)
        self.sequence_counter += 1

        # Add to execution queue (non-blocking)
        await self.execution_queue.put(req)
        self._logger.debug(f"Queued execution {msg_id[:8]}, queue depth: {self.execution_queue.qsize()}")

        return msg_id

    async def _execution_loop(self):
        """
        Serial execution loop. Processes one cell at a time from the queue.
        This eliminates race conditions by ensuring only one cell is "running" at a time.
        """
        self._logger.info(f"Execution loop started for kernel {self.kernel_id[:8]}")

        while True:
            try:
                # Wait for next execution request
                req = await self.execution_queue.get()

                # Check if kernel died while waiting
                if self.is_dead:
                    self._logger.warning(f"Kernel dead, skipping cell {req.msg_id[:8]}")
                    await self._send_cell_status(req.msg_id, "skipped")
                    self.execution_queue.task_done()
                    continue

                # Mark as current execution
                self.current_execution = req

                try:
                    # Send "running" status (cell is now executing)
                    await self._send_cell_status(req.msg_id, "running")

                    # Send code to kernel - kernel generates its own msg_id
                    kernel_msg_id = self.client.execute(req.code)

                    # Map kernel's msg_id to our msg_id for correlation
                    self.msg_id_map[kernel_msg_id] = req.msg_id

                    self._logger.debug(
                        f"Executing cell {req.msg_id[:8]} (kernel msg_id: {kernel_msg_id[:8]}), "
                        f"queue depth: {self.execution_queue.qsize()}"
                    )

                    # Wait for completion (Future resolved by _listen_iopub)
                    await req.future

                    self._logger.debug(f"Cell {req.msg_id[:8]} completed")

                except asyncio.CancelledError:
                    # Task was cancelled (plugin shutdown)
                    self._logger.info(f"Execution loop cancelled during {req.msg_id[:8]}")
                    await self._send_cell_status(req.msg_id, "skipped")
                    break

                except Exception as e:
                    self._logger.error(f"Execution loop error for {req.msg_id[:8]}: {e}")
                    await self._send_cell_status(req.msg_id, "completed_error")

                finally:
                    self.current_execution = None
                    self.execution_queue.task_done()

            except asyncio.CancelledError:
                self._logger.info("Execution loop cancelled")
                break
            except Exception as e:
                self._logger.error(f"Unexpected execution loop error: {e}")
                # Continue loop - don't crash on errors

        self._logger.info(f"Execution loop stopped for kernel {self.kernel_id[:8]}")

    async def interrupt(self):
        """
        Send interrupt signal to kernel and wait for it to actually stop.
        Drains execution queue and marks pending cells as skipped.
        """
        if not self.km:
            raise RuntimeError("Kernel manager is not available. Call start() first.")

        try:
            self._logger.info(f"Interrupting kernel {self.kernel_id[:8]}")
            self.is_interrupting = True

            # Send interrupt signal to kernel
            await self.km.interrupt_kernel()

            # Wait for kernel to actually go idle (with timeout)
            try:
                await asyncio.wait_for(self._wait_for_kernel_idle(), timeout=5.0)
            except asyncio.TimeoutError:
                self._logger.warning(f"Kernel {self.kernel_id[:8]} didn't go idle after interrupt")

            # Drain the queue - mark all pending cells as skipped
            await self._drain_queue(reason="skipped")

            self.is_interrupting = False
            self._logger.info(f"Kernel {self.kernel_id[:8]} interrupted, queue drained")

        except Exception as e:
            self.is_interrupting = False
            self._logger.error(f"Error interrupting kernel {self.kernel_id[:8]}: {e}")
            raise

    async def _wait_for_kernel_idle(self):
        """
        Wait for kernel to transition to idle state.
        Used after interrupt to ensure kernel actually stopped.
        """
        # Create a future that will be resolved when we see idle status
        idle_future = asyncio.Future()
        self._idle_waiter = idle_future

        # Wait for the future to be resolved (by _listen_iopub)
        await idle_future

        self._idle_waiter = None

    async def _drain_queue(self, reason: str = "skipped"):
        """
        Empty the execution queue and mark all pending cells with given status.
        Used during interrupt/restart to clean up queued cells.
        """
        # Cancel current execution if any
        if self.current_execution and not self.current_execution.future.done():
            if not self.current_execution.future.cancelled():
                self.current_execution.future.cancel()
                await self._send_cell_status(self.current_execution.msg_id, reason)
            self.current_execution = None

        # Drain all queued cells
        drained_count = 0
        while not self.execution_queue.empty():
            try:
                req = self.execution_queue.get_nowait()
                await self._send_cell_status(req.msg_id, reason)
                self.execution_queue.task_done()
                drained_count += 1
            except asyncio.QueueEmpty:
                break

        if drained_count > 0:
            self._logger.info(f"Drained {drained_count} cells from queue (reason: {reason})")

    async def restart(self):
        """
        Restart kernel and clear execution queue.
        Sends a notification to the frontend about the restart.
        """
        if not self.km:
            raise RuntimeError("Kernel manager is not available. Call start() first.")

        try:
            self._logger.info(f"Restarting kernel {self.kernel_id[:8]}")

            # Drain queue BEFORE restarting
            await self._drain_queue(reason="skipped")

            # Cancel existing tasks before restart
            if self.listener_task and not self.listener_task.done():
                self.listener_task.cancel()
                try:
                    await asyncio.wait_for(self.listener_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            if self.monitor_task and not self.monitor_task.done():
                self.monitor_task.cancel()
                try:
                    await asyncio.wait_for(self.monitor_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            if self.executor_task and not self.executor_task.done():
                self.executor_task.cancel()
                try:
                    await asyncio.wait_for(self.executor_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            # Restart the kernel
            await self.km.restart_kernel()

            # Wait for the client to reconnect to restarted kernel
            await self.client.wait_for_ready(timeout=30)

            # Clear stale message ID mappings from old kernel
            self.msg_id_map.clear()

            # Restart the IOPub listener task
            self.listener_task = asyncio.create_task(self._listen_iopub())

            # Restart the process monitoring task
            self.monitor_task = asyncio.create_task(self._monitor_process())

            # Restart the execution loop task
            self.executor_task = asyncio.create_task(self._execution_loop())
            self._logger.debug(f"Restarted execution loop for kernel {self.kernel_id[:8]}")

            # Note: We preserve the output cache to maintain execution history
            # Users can still see previous outputs even after restart

            # Create a custom message for the frontend
            from datetime import datetime, timezone

            restart_message = {
                "header": {
                    "msg_id": f"restart_{self.kernel_id}_{datetime.now(timezone.utc).isoformat()}",
                    "msg_type": "kernel_restarted",
                    "username": "quench",
                    "session": self.kernel_id,
                    "date": datetime.now(timezone.utc),
                    "version": "5.3",
                },
                "msg_type": "kernel_restarted",
                "content": {"status": "ok"},
                "metadata": {},
                "buffers": [],
            }

            # Add to cache so it's replayed when frontend reconnects
            self.output_cache.append(restart_message)
            # Add the message to the relay queue
            await self.relay_queue.put((self.kernel_id, restart_message))

            self._logger.info(f"Kernel {self.kernel_id[:8]} restarted successfully")

        except Exception as e:
            self._logger.error(f"Error restarting kernel {self.kernel_id[:8]}: {e}")
            raise

    async def _listen_iopub(self):
        """
        Listen to IOPub channel for kernel messages.
        Resolves Futures when cells complete.
        """
        if not self.client:
            return

        try:
            self._logger.info(f"Started IOPub listener for kernel {self.kernel_id[:8]}")

            while True:
                try:
                    # Wait for messages from the IOPub channel
                    message = await self.client.get_iopub_msg(timeout=1.0)
                    msg_type = message.get("msg_type")
                    kernel_msg_id = message.get("parent_header", {}).get("msg_id")

                    # Skip our own synthetic execute_input messages
                    if msg_type == "execute_input" and message.get("header", {}).get("msg_id", "").startswith(
                        "synthetic_"
                    ):
                        continue

                    # Translate kernel msg_id to our msg_id
                    our_msg_id = self.msg_id_map.get(kernel_msg_id, kernel_msg_id)

                    # Update parent_header with our msg_id for frontend
                    if kernel_msg_id in self.msg_id_map:
                        message["parent_header"]["msg_id"] = our_msg_id

                    # Handle status messages
                    if msg_type == "status":
                        execution_state = message.get("content", {}).get("execution_state")

                        if execution_state == "idle":
                            # Resolve idle waiter if waiting for interrupt
                            if self._idle_waiter and not self._idle_waiter.done():
                                self._idle_waiter.set_result(True)

                            # If this idle corresponds to current execution, mark complete
                            if self.current_execution and kernel_msg_id in self.msg_id_map:
                                if self.msg_id_map[kernel_msg_id] == self.current_execution.msg_id:
                                    if not self.current_execution.future.done():
                                        # Check if there was an error (tracked via error handler below)
                                        if not hasattr(self.current_execution, "_had_error"):
                                            await self._send_cell_status(self.current_execution.msg_id, "completed_ok")
                                        # Resolve the future unless it was cancelled
                                        if not self.current_execution.future.cancelled():
                                            self.current_execution.future.set_result(True)

                                    # Clean up msg_id mapping
                                    if kernel_msg_id in self.msg_id_map:
                                        del self.msg_id_map[kernel_msg_id]

                    # Handle error messages
                    elif msg_type == "error":
                        if self.current_execution and kernel_msg_id in self.msg_id_map:
                            if self.msg_id_map[kernel_msg_id] == self.current_execution.msg_id:
                                # Mark that this execution had an error
                                self.current_execution._had_error = True
                                await self._send_cell_status(self.current_execution.msg_id, "completed_error")

                    # Cache coalescing: merge consecutive stream messages in the cache
                    # to reduce reload time, while still sending granular updates to
                    # the relay queue for real-time feedback.
                    should_append_to_cache = True

                    if msg_type == "stream" and self.output_cache:
                        last_msg = self.output_cache[-1]

                        # Check if compatible for merging
                        if (
                            last_msg.get("msg_type") == "stream"
                            and last_msg.get("content", {}).get("name") == message.get("content", {}).get("name")
                            and last_msg.get("parent_header", {}).get("msg_id") == our_msg_id
                        ):
                            # Merge text into the existing cache entry
                            last_msg["content"]["text"] += message["content"]["text"]
                            should_append_to_cache = False
                            self._logger.debug(f"Coalesced stream message into cache for kernel {self.kernel_id[:8]}")

                    # Add to cache and relay
                    if should_append_to_cache:
                        self.output_cache.append(message)

                    await self.relay_queue.put((self.kernel_id, message))

                    self._logger.debug(f"Relayed message from kernel {self.kernel_id[:8]}: {msg_type}")

                except asyncio.TimeoutError:
                    # Timeout is expected, continue listening
                    continue
                except Exception as e:
                    # Log other errors but continue listening
                    error_msg = str(e) if e else "Unknown error"

                    # Don't spam logs with Empty exceptions - they're normal timeouts
                    if "Empty" not in error_msg and e.__class__.__name__ != "Empty":
                        self._logger.warning(
                            f"Error receiving IOPub message from kernel {self.kernel_id[:8]}: {error_msg}"
                        )

                        # Add more detailed error info for non-Empty errors
                        if hasattr(e, "__class__"):
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

    async def _monitor_process(self):
        """
        Periodically check if the kernel process is still alive.
        If the process dies unexpectedly, notify the frontend and clean up resources.
        """
        try:
            while True:
                if self.km and not await self.km.is_alive():
                    self._logger.warning(f"Kernel {self.kernel_id[:8]} process died unexpectedly.")

                    # Mark kernel as dead for auto-restart functionality
                    self.is_dead = True

                    # Drain the execution queue to prevent old cells from running after restart
                    await self._drain_queue(reason="skipped")
                    self._logger.info(f"Drained execution queue due to kernel death")

                    # Notify Frontend
                    from datetime import datetime, timezone

                    death_msg = {
                        "header": {
                            "msg_id": f"death_{self.kernel_id}",
                            "msg_type": "kernel_died",
                            "date": datetime.now(timezone.utc),
                            "version": "5.3",
                        },
                        "msg_type": "kernel_died",
                        "content": {"reason": "Process crashed or was terminated by OS", "status": "dead"},
                    }
                    # Add to cache so it's replayed when frontend reconnects
                    self.output_cache.append(death_msg)
                    await self.relay_queue.put((self.kernel_id, death_msg))

                    # Clean up the client and kernel manager references
                    # Don't call shutdown() as it would try to cancel this task from within itself
                    try:
                        if self.client:
                            self.client.stop_channels()
                            self.client = None
                        self.km = None
                    except Exception as e:
                        self._logger.error(f"Error during cleanup of dead kernel: {e}")

                    break  # Stop monitoring

                await asyncio.sleep(2.0)  # Check every 2 seconds

        except asyncio.CancelledError:
            pass


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

    async def start_session(
        self, relay_queue: asyncio.Queue, buffer_name: str = None, kernel_name: str = None
    ) -> KernelSession:
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
            running_kernels.append(
                {
                    "display_name": f"Running: {session.kernel_name} ({kernel_id[:8]})",
                    "value": kernel_id,
                    "is_running": True,
                }
            )

        new_kernels = []
        kernelspecs = self.discover_kernelspecs()
        for spec in kernelspecs:
            new_kernels.append(
                {"display_name": f"New: {spec['display_name']}", "value": spec["name"], "is_running": False}
            )

        if running_first:
            choices.extend(running_kernels)
            choices.extend(new_kernels)
        else:
            choices.extend(new_kernels)
            choices.extend(running_kernels)

        return choices

    async def get_or_create_session(
        self, bnum: int, relay_queue: asyncio.Queue, buffer_name: str = None, kernel_name: str = None
    ) -> KernelSession:
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
                "kernel_id": kernel_id,
                "name": session.buffer_name,
                "kernel_name": session.kernel_name,
                "python_executable": session.python_executable,
                "short_id": kernel_id[:8],
                "created_at": session.created_at.isoformat() if hasattr(session, "created_at") else None,
                "associated_buffers": list(session.associated_buffers),
                "output_cache_size": len(session.output_cache),
                "is_alive": session.listener_task is not None and not session.listener_task.done(),
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
                    kernelspecs.append({"name": kernel_name, "display_name": spec.display_name, "argv": spec.argv})
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
