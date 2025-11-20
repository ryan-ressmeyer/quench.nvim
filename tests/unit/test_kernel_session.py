"""
Unit tests for KernelSession and KernelSessionManager classes.
"""
import pytest
import asyncio
import json
import subprocess
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import the kernel session components
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rplugin', 'python3'))

from quench.kernel_session import KernelSession, KernelSessionManager


class TestKernelSession:
    """Test cases for the KernelSession class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.relay_queue = asyncio.Queue()
        self.buffer_name = "test_buffer"
        self.kernel_name = "python3"
    
    def test_kernel_session_init_default_kernel_name(self):
        """Test KernelSession initialization with default kernel name."""
        session = KernelSession(self.relay_queue, self.buffer_name)
        assert session.kernel_name == "python3"
        assert session.buffer_name == self.buffer_name
        assert session.relay_queue == self.relay_queue
        assert session.kernel_id is not None
        assert session.output_cache == []
    
    def test_kernel_session_init_custom_kernel_name(self):
        """Test KernelSession initialization with custom kernel name."""
        custom_kernel = "conda-env"
        session = KernelSession(self.relay_queue, self.buffer_name, custom_kernel)
        assert session.kernel_name == custom_kernel
        assert session.buffer_name == self.buffer_name
        assert session.kernel_id is not None
    
    @pytest.mark.asyncio
    async def test_kernel_session_start_success(self):
        """Test successful kernel session start."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock jupyter_client components
        mock_km = AsyncMock()
        mock_client = AsyncMock()
        # Synchronous methods should be regular Mock
        mock_client.start_channels = Mock()
        mock_client.stop_channels = Mock()
        mock_km.client = Mock(return_value=mock_client)
        
        with patch('quench.kernel_session.AsyncKernelManager', return_value=mock_km), \
             patch('quench.kernel_session.JUPYTER_CLIENT_AVAILABLE', True), \
             patch.object(session, '_listen_iopub', new_callable=AsyncMock) as mock_listen:
            
            await session.start()
            
            # Verify kernel manager setup
            assert session.km == mock_km
            assert session.client == mock_client
            mock_km.start_kernel.assert_called_once()
            mock_client.start_channels.assert_called_once()
            mock_client.wait_for_ready.assert_called_once_with(timeout=30)
            
            # Verify iopub listener started
            mock_listen.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_kernel_session_start_with_kernel_name_override(self):
        """Test starting with kernel name override."""
        session = KernelSession(self.relay_queue, self.buffer_name, "python3")
        
        mock_km = AsyncMock()
        mock_client = AsyncMock()
        # Synchronous methods should be regular Mock
        mock_client.start_channels = Mock()
        mock_client.stop_channels = Mock()
        mock_km.client = Mock(return_value=mock_client)
        
        with patch('quench.kernel_session.AsyncKernelManager', return_value=mock_km) as mock_km_class, \
             patch('quench.kernel_session.JUPYTER_CLIENT_AVAILABLE', True), \
             patch.object(session, '_listen_iopub', new_callable=AsyncMock):
            
            # Start with different kernel name
            await session.start("julia-1.6")
            
            # Verify AsyncKernelManager created with override
            mock_km_class.assert_called_once_with(kernel_name='julia-1.6')
    
    @pytest.mark.asyncio
    async def test_kernel_session_start_jupyter_not_available(self):
        """Test starting when jupyter_client is not available."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        with patch('quench.kernel_session.JUPYTER_CLIENT_AVAILABLE', False):
            with pytest.raises(RuntimeError, match="jupyter_client is not installed or imports failed"):
                await session.start()
    
    @pytest.mark.asyncio
    async def test_kernel_session_execute_success(self):
        """Test successful code execution."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock kernel client
        mock_client = AsyncMock()
        mock_client.execute = Mock(return_value="msg-id-123")
        session.client = mock_client
        
        code = "print('hello world')"
        await session.execute(code)
        
        # Verify execute was called with correct parameters
        mock_client.execute.assert_called_once_with(code)
        
        # Verify synthetic execute_input message was sent first
        assert not self.relay_queue.empty()
        kernel_id, message = await self.relay_queue.get()
        assert kernel_id == session.kernel_id
        assert message["msg_type"] == "execute_input"
        assert message["content"]["code"] == code
        
        # Verify queued status message was sent next
        assert not self.relay_queue.empty()
        kernel_id, status_message = await self.relay_queue.get()
        assert kernel_id == session.kernel_id
        assert status_message["msg_type"] == "quench_cell_status"
        assert status_message["content"]["status"] == "queued"
        assert status_message["parent_header"]["msg_id"] == "msg-id-123"
        
        # Verify running status message was sent last
        assert not self.relay_queue.empty()
        kernel_id, status_message = await self.relay_queue.get()
        assert kernel_id == session.kernel_id
        assert status_message["msg_type"] == "quench_cell_status"
        assert status_message["content"]["status"] == "running"
        assert status_message["parent_header"]["msg_id"] == "msg-id-123"
    
    @pytest.mark.asyncio
    async def test_kernel_session_execute_without_client(self):
        """Test execute when kernel client is not available."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        with pytest.raises(RuntimeError, match="Kernel client is not available"):
            await session.execute("print('test')")
    
    @pytest.mark.asyncio
    async def test_kernel_session_error_marks_queued_cells_as_skipped(self):
        """Test that when an error occurs, remaining queued cells are marked as skipped."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Set up multiple pending executions
        session.pending_executions = {
            'msg-id-1': 'running',
            'msg-id-2': 'queued', 
            'msg-id-3': 'queued',
            'msg-id-4': 'queued'
        }
        
        # Mock client for message listening
        mock_client = AsyncMock()
        session.client = mock_client
        
        # Simulate an error message for msg-id-1
        error_message = {
            'msg_type': 'error',
            'parent_header': {'msg_id': 'msg-id-1'},
            'content': {'ename': 'ValueError', 'evalue': 'test error'}
        }
        
        # Manually call the error handling logic
        parent_msg_id = error_message.get('parent_header', {}).get('msg_id')
        if parent_msg_id and parent_msg_id in session.pending_executions:
            await session._send_cell_status(parent_msg_id, 'completed_error')
            del session.pending_executions[parent_msg_id]
            
            # Mark remaining queued executions as skipped
            remaining_executions = list(session.pending_executions.keys())
            for remaining_msg_id in remaining_executions:
                if session.pending_executions[remaining_msg_id] == 'queued':
                    await session._send_cell_status(remaining_msg_id, 'skipped')
                    del session.pending_executions[remaining_msg_id]
        
        # Verify messages were sent
        messages = []
        while not self.relay_queue.empty():
            messages.append(await self.relay_queue.get())
        
        # Should have: 1 error + 3 skipped = 4 messages
        assert len(messages) == 4
        
        # Verify error message
        kernel_id, error_status = messages[0]
        assert error_status['msg_type'] == 'quench_cell_status'
        assert error_status['content']['status'] == 'completed_error'
        assert error_status['parent_header']['msg_id'] == 'msg-id-1'
        
        # Verify skipped messages
        skipped_statuses = [msg[1] for msg in messages[1:]]
        for status_msg in skipped_statuses:
            assert status_msg['msg_type'] == 'quench_cell_status'
            assert status_msg['content']['status'] == 'skipped'
            assert status_msg['parent_header']['msg_id'] in ['msg-id-2', 'msg-id-3', 'msg-id-4']
        
        # Verify pending executions were cleared
        assert len(session.pending_executions) == 0
    
    @pytest.mark.asyncio
    async def test_kernel_session_interrupt_success(self):
        """Test successful kernel interrupt."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock kernel manager
        mock_km = AsyncMock()
        mock_km.interrupt_kernel = AsyncMock()
        session.km = mock_km
        
        await session.interrupt()
        mock_km.interrupt_kernel.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_kernel_session_interrupt_without_manager(self):
        """Test interrupt when kernel manager is not available."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        with pytest.raises(RuntimeError, match="Kernel manager is not available"):
            await session.interrupt()
    
    @pytest.mark.asyncio
    async def test_kernel_session_interrupt_error_handling(self):
        """Test interrupt method error handling."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        mock_km = AsyncMock()
        mock_km.interrupt_kernel = AsyncMock(side_effect=Exception("Interrupt failed"))
        session.km = mock_km
        
        with pytest.raises(Exception, match="Interrupt failed"):
            await session.interrupt()
    
    @pytest.mark.asyncio
    async def test_kernel_session_manual_restart_success(self):
        """Test successful manual kernel restart via restart() method.

        This tests user-initiated restart (QuenchResetKernel command),
        which is different from auto-restart after kernel death.
        """
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock kernel manager
        mock_km = AsyncMock()
        mock_km.restart_kernel = AsyncMock()
        session.km = mock_km
        
        # Add items to output cache
        session.output_cache = ["item1", "item2"]
        
        await session.restart()
        
        # Verify restart_kernel was called
        mock_km.restart_kernel.assert_called_once()

        # Verify output cache was preserved (not cleared)
        assert len(session.output_cache) == 2
        assert session.output_cache == ["item1", "item2"]
        
        # Verify kernel_restarted message was queued
        assert not self.relay_queue.empty()
        kernel_id, message = await self.relay_queue.get()
        assert kernel_id == session.kernel_id
        assert message["msg_type"] == "kernel_restarted"
        assert message["content"]["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_kernel_session_restart_without_manager(self):
        """Test restart when kernel manager is not available."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        with pytest.raises(RuntimeError, match="Kernel manager is not available"):
            await session.restart()
    
    @pytest.mark.asyncio
    async def test_kernel_session_restart_error_handling(self):
        """Test restart method error handling."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)

        mock_km = AsyncMock()
        mock_km.restart_kernel = AsyncMock(side_effect=Exception("Restart failed"))
        session.km = mock_km

        with pytest.raises(Exception, match="Restart failed"):
            await session.restart()

    @pytest.mark.asyncio
    async def test_kernel_session_death_detection(self):
        """Test kernel death detection via monitoring loop."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)

        # Mock kernel manager that reports as dead
        mock_km = AsyncMock()
        mock_client = AsyncMock()

        # First check returns True (alive), second returns False (dead)
        # This simulates kernel dying during monitoring
        mock_km.is_alive = AsyncMock(side_effect=[True, False])

        session.km = mock_km
        session.client = mock_client

        # Verify kernel starts as alive
        assert session.is_dead == False

        # Start the monitoring task
        monitor_task = asyncio.create_task(session._monitor_process())

        # Wait for monitoring loop to detect death
        # The loop checks every 2 seconds, so we need to wait a bit
        await asyncio.sleep(2.5)

        # Cancel the monitoring task
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # Verify death was detected
        assert session.is_dead == True

        # Verify kernel_died message was sent to relay queue
        assert not self.relay_queue.empty()
        kernel_id, message = await self.relay_queue.get()
        assert kernel_id == session.kernel_id
        assert message["msg_type"] == "kernel_died"
        assert message["content"]["status"] == "dead"
        assert "crashed" in message["content"]["reason"].lower() or "terminated" in message["content"]["reason"].lower()

        # Verify client and manager references are cleaned up
        assert session.client is None
        assert session.km is None

    @pytest.mark.asyncio
    async def test_kernel_session_auto_restart_on_execute(self):
        """Test auto-restart mechanism when executing code after kernel death."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)

        # Simulate a dead kernel
        session.is_dead = True

        # Mock the start method to simulate successful restart
        original_start = session.start
        start_called = False

        async def mock_start(kernel_name=None):
            nonlocal start_called
            start_called = True
            # Set up minimal mocks to simulate successful start
            session.km = AsyncMock()
            session.client = AsyncMock()
            session.client.execute = Mock(return_value="msg-id-auto-restart")
            session.listener_task = AsyncMock()
            session.monitor_task = AsyncMock()
            # Clear the is_dead flag as start() does
            session.is_dead = False

        # Patch the start method
        with patch.object(session, 'start', new=mock_start):
            # Execute code
            code = "print('Testing auto-restart')"
            await session.execute(code)

            # Verify start() was called (auto-restart triggered)
            assert start_called == True

        # Verify is_dead flag was cleared
        assert session.is_dead == False

        # Verify messages were sent in correct order:
        # 1. execute_input
        # 2. quench_cell_status (queued)
        # 3. quench_cell_status (running)
        # 4. kernel_auto_restarted
        messages = []
        while not self.relay_queue.empty():
            messages.append(await self.relay_queue.get())

        # Find the kernel_auto_restarted message
        auto_restart_msg = None
        for kernel_id, msg in messages:
            if msg["msg_type"] == "kernel_auto_restarted":
                auto_restart_msg = msg
                break

        assert auto_restart_msg is not None, "kernel_auto_restarted message not found"
        assert auto_restart_msg["content"]["status"] == "ok"
        assert "auto-restart" in auto_restart_msg["content"]["reason"].lower()

        # Verify execute was called on the client after restart
        assert session.client.execute.called

    @pytest.mark.asyncio
    async def test_kernel_session_shutdown_success(self):
        """Test successful kernel shutdown."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock components
        mock_km = AsyncMock()
        
        # Create a real asyncio task that we can cancel
        async def dummy_listener():
            try:
                while True:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
        
        # Start a real task
        mock_listen_task = asyncio.create_task(dummy_listener())
        
        session.km = mock_km
        session.listener_task = mock_listen_task
        
        await session.shutdown()
        
        # Verify shutdown sequence
        assert mock_listen_task.cancelled() or mock_listen_task.done()
        mock_km.shutdown_kernel.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_kernel_session_shutdown_without_components(self):
        """Test shutdown when components are not available (should not crash)."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Should not raise exception
        await session.shutdown()
    
    @pytest.mark.asyncio
    async def test_listen_iopub_stream_message(self):
        """Test _listen_iopub handling stream messages."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock kernel client
        mock_client = AsyncMock()
        
        # Create test messages
        stream_msg = {
            "msg_type": "stream",
            "content": {"name": "stdout", "text": "Hello World"}
        }
        
        # Create a queue to control message flow
        message_queue = asyncio.Queue()
        await message_queue.put(stream_msg)
        
        # Mock get_iopub_msg to return from our queue or timeout
        async def mock_get_iopub_msg(timeout=1.0):
            try:
                return await asyncio.wait_for(message_queue.get(), timeout=0.01)
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError()
        
        mock_client.get_iopub_msg = mock_get_iopub_msg
        session.client = mock_client
        
        # Start listening task
        listen_task = asyncio.create_task(session._listen_iopub())
        
        # Wait a very short time for message processing
        await asyncio.sleep(0.02)
        
        # Cancel the task
        listen_task.cancel()
        
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
        
        # Verify message was added to output cache and relay queue
        assert stream_msg in session.output_cache
        
        # Check relay queue
        assert not self.relay_queue.empty()
        kernel_id, relayed_msg = await self.relay_queue.get()
        assert kernel_id == session.kernel_id
        assert relayed_msg == stream_msg
    
    @pytest.mark.asyncio
    async def test_listen_iopub_execute_result_message(self):
        """Test _listen_iopub handling execute_result messages."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock kernel client
        mock_client = AsyncMock()
        
        execute_result_msg = {
            "msg_type": "execute_result",
            "content": {"data": {"text/plain": "42"}, "execution_count": 1}
        }
        
        # Create a queue to control message flow
        message_queue = asyncio.Queue()
        await message_queue.put(execute_result_msg)
        
        # Mock get_iopub_msg to return from our queue or timeout
        async def mock_get_iopub_msg(timeout=1.0):
            try:
                return await asyncio.wait_for(message_queue.get(), timeout=0.01)
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError()
        
        mock_client.get_iopub_msg = mock_get_iopub_msg
        session.client = mock_client
        
        # Start and quickly cancel listening task
        listen_task = asyncio.create_task(session._listen_iopub())
        await asyncio.sleep(0.02)
        listen_task.cancel()
        
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
        
        # Verify message was processed
        assert execute_result_msg in session.output_cache
    
    @pytest.mark.asyncio
    async def test_listen_iopub_error_message(self):
        """Test _listen_iopub handling error messages."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        mock_client = AsyncMock()
        
        error_msg = {
            "msg_type": "error",
            "content": {"ename": "NameError", "evalue": "name 'x' is not defined"}
        }
        
        # Create a queue to control message flow
        message_queue = asyncio.Queue()
        await message_queue.put(error_msg)
        
        # Mock get_iopub_msg to return from our queue or timeout
        async def mock_get_iopub_msg(timeout=1.0):
            try:
                return await asyncio.wait_for(message_queue.get(), timeout=0.01)
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError()
        
        mock_client.get_iopub_msg = mock_get_iopub_msg
        session.client = mock_client
        
        listen_task = asyncio.create_task(session._listen_iopub())
        await asyncio.sleep(0.02)
        listen_task.cancel()
        
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
        
        assert error_msg in session.output_cache
    
    @pytest.mark.asyncio
    async def test_listen_iopub_cancellation(self):
        """Test _listen_iopub proper cancellation handling."""
        session = KernelSession(self.relay_queue, self.buffer_name, self.kernel_name)
        
        # Mock that takes a bit longer to timeout so we can cancel during wait
        mock_client = AsyncMock()
        
        async def mock_get_iopub_msg(timeout=1.0):
            # Sleep for a bit to simulate waiting, then timeout
            await asyncio.sleep(0.05)
            raise asyncio.TimeoutError()
        
        mock_client.get_iopub_msg = mock_get_iopub_msg
        session.client = mock_client
        
        listen_task = asyncio.create_task(session._listen_iopub())
        
        # Give it time to enter the loop and start waiting for messages
        await asyncio.sleep(0.01)
        listen_task.cancel()
        
        # Should handle cancellation gracefully
        with pytest.raises(asyncio.CancelledError):
            await listen_task


class TestKernelSessionManager:
    """Test cases for the KernelSessionManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Reset singleton for testing
        KernelSessionManager._instance = None
        KernelSessionManager._initialized = False
        self.manager = KernelSessionManager()
    
    def test_kernel_session_manager_singleton(self):
        """Test that KernelSessionManager is a singleton."""
        manager1 = KernelSessionManager()
        manager2 = KernelSessionManager()
        assert manager1 is manager2
    
    def test_discover_kernelspecs_success(self):
        """Test successful discovery of kernel specifications."""
        # Mock KernelSpecManager and its methods
        mock_ksm = Mock()
        mock_spec_python3 = Mock()
        mock_spec_python3.display_name = "Python 3"
        mock_spec_python3.argv = ["python", "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        
        mock_spec_conda = Mock()
        mock_spec_conda.display_name = "Python 3 (conda-base)"
        mock_spec_conda.argv = ["/home/user/anaconda3/bin/python", "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        
        mock_ksm.find_kernel_specs.return_value = {"python3": "/path/to/python3", "conda-base": "/path/to/conda-base"}
        mock_ksm.get_kernel_spec.side_effect = lambda name: mock_spec_python3 if name == "python3" else mock_spec_conda
        
        with patch('jupyter_client.kernelspec.KernelSpecManager', return_value=mock_ksm):
            kernelspecs = self.manager.discover_kernelspecs()
            
            # Verify KernelSpecManager calls
            mock_ksm.find_kernel_specs.assert_called_once()
            assert mock_ksm.get_kernel_spec.call_count == 2
            
            # Verify results
            assert len(kernelspecs) == 2
            
            # Check discovered kernels
            python3_kernel = next((k for k in kernelspecs if k['name'] == 'python3'), None)
            assert python3_kernel is not None
            assert python3_kernel['display_name'] == 'Python 3'
            
            conda_kernel = next((k for k in kernelspecs if k['name'] == 'conda-base'), None)
            assert conda_kernel is not None
            assert conda_kernel['display_name'] == 'Python 3 (conda-base)'
    
    def test_discover_kernelspecs_jupyter_not_found(self):
        """Test discovery when jupyter command is not found."""
        with patch('jupyter_client.kernelspec.KernelSpecManager', side_effect=ImportError("jupyter_client not found")):
            with pytest.raises(ImportError, match="jupyter_client not found"):
                self.manager.discover_kernelspecs()
    
    def test_discover_kernelspecs_subprocess_error(self):
        """Test discovery when jupyter command fails."""
        with patch('jupyter_client.kernelspec.KernelSpecManager', side_effect=Exception("KernelSpec error")):
            with pytest.raises(Exception, match="KernelSpec error"):
                self.manager.discover_kernelspecs()
    
    def test_discover_kernelspecs_invalid_json(self):
        """Test discovery with invalid JSON response."""
        mock_ksm = Mock()
        mock_ksm.find_kernel_specs.return_value = {"python3": "/path/to/python3"}
        mock_ksm.get_kernel_spec.side_effect = Exception("Failed to get kernel spec")
        
        with patch('jupyter_client.kernelspec.KernelSpecManager', return_value=mock_ksm):
            kernelspecs = self.manager.discover_kernelspecs()
            
            # Should return empty list since get_kernel_spec failed
            assert len(kernelspecs) == 0
    
    def test_discover_kernelspecs_timeout(self):
        """Test discovery with subprocess timeout."""
        mock_ksm = Mock()
        mock_ksm.find_kernel_specs.side_effect = Exception("Timeout")
        
        with patch('jupyter_client.kernelspec.KernelSpecManager', return_value=mock_ksm):
            with pytest.raises(Exception, match="Timeout"):
                self.manager.discover_kernelspecs()
    
    def test_discover_kernelspecs_empty_kernelspecs(self):
        """Test discovery when kernelspecs section is missing or empty."""
        mock_ksm = Mock()
        mock_ksm.find_kernel_specs.return_value = {}  # No kernels found
        
        with patch('jupyter_client.kernelspec.KernelSpecManager', return_value=mock_ksm):
            kernelspecs = self.manager.discover_kernelspecs()
            
            # Should return empty list
            assert len(kernelspecs) == 0
    
    @pytest.mark.asyncio
    async def test_get_or_create_session_new_session(self):
        """Test creating a new kernel session."""
        relay_queue = AsyncMock()
        
        with patch('quench.kernel_session.KernelSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-id"
            mock_session.start = AsyncMock()
            mock_session.associated_buffers = set()  # Add proper set attribute
            mock_session_class.return_value = mock_session
            
            session = await self.manager.get_or_create_session(
                bnum=1,
                relay_queue=relay_queue,
                buffer_name="test_buffer",
                kernel_name="python3"
            )
            
            # Verify session creation
            mock_session_class.assert_called_once_with(relay_queue, "test_buffer", "python3")
            mock_session.start.assert_called_once()
            
            # Verify session storage
            assert session == mock_session
            assert "test-kernel-id" in self.manager.sessions
            assert 1 in self.manager.buffer_to_kernel_map
            assert self.manager.buffer_to_kernel_map[1] == "test-kernel-id"
    
    @pytest.mark.asyncio
    async def test_get_or_create_session_existing_session(self):
        """Test retrieving an existing kernel session."""
        relay_queue = AsyncMock()
        
        # Create existing session
        existing_session = AsyncMock()
        existing_session.kernel_id = "existing-kernel-id"
        self.manager.sessions["existing-kernel-id"] = existing_session
        self.manager.buffer_to_kernel_map[1] = "existing-kernel-id"
        
        session = await self.manager.get_or_create_session(
            bnum=1,
            relay_queue=relay_queue,
            buffer_name="test_buffer"
        )
        
        # Should return existing session
        assert session == existing_session
    
    @pytest.mark.asyncio
    async def test_get_or_create_session_default_kernel_name(self):
        """Test creating session with default kernel name."""
        relay_queue = AsyncMock()
        
        with patch('quench.kernel_session.KernelSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-id-2"
            mock_session.associated_buffers = set()  # Add proper set attribute
            mock_session_class.return_value = mock_session
            
            await self.manager.get_or_create_session(
                bnum=2,
                relay_queue=relay_queue,
                buffer_name="test_buffer2"
            )
            
            # Verify None is passed for kernel_name (will default to 'python3')
            mock_session_class.assert_called_once_with(relay_queue, "test_buffer2", None)
    
    @pytest.mark.asyncio
    async def test_shutdown_all_sessions(self):
        """Test shutting down all kernel sessions."""
        # Create mock sessions
        session1 = AsyncMock()
        session2 = AsyncMock()
        session1.shutdown = AsyncMock()
        session2.shutdown = AsyncMock()
        
        self.manager.sessions = {
            "kernel1": session1,
            "kernel2": session2
        }
        
        await self.manager.shutdown_all_sessions()
        
        # Verify all sessions were shutdown
        session1.shutdown.assert_called_once()
        session2.shutdown.assert_called_once()
        
        # Verify cleanup
        assert len(self.manager.sessions) == 0
        assert len(self.manager.buffer_to_kernel_map) == 0
    
    @pytest.mark.asyncio
    async def test_shutdown_all_sessions_empty(self):
        """Test shutting down when no sessions exist."""
        # Should not raise exception
        await self.manager.shutdown_all_sessions()
        
        assert len(self.manager.sessions) == 0
        assert len(self.manager.buffer_to_kernel_map) == 0
    
    @pytest.mark.asyncio
    async def test_shutdown_all_sessions_error_handling(self):
        """Test shutdown handling when individual session shutdown fails."""
        # Create mock sessions, one that fails
        session1 = AsyncMock()
        session2 = AsyncMock()
        session1.shutdown = AsyncMock(side_effect=Exception("Shutdown failed"))
        session2.shutdown = AsyncMock()
        
        self.manager.sessions = {
            "kernel1": session1,
            "kernel2": session2
        }
        
        # Should not raise exception, but should continue with other sessions
        await self.manager.shutdown_all_sessions()
        
        # Verify both shutdowns were attempted
        session1.shutdown.assert_called_once()
        session2.shutdown.assert_called_once()
        
        # Verify cleanup still happened
        assert len(self.manager.sessions) == 0


if __name__ == '__main__':
    pytest.main([__file__])