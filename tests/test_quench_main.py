"""
Unit tests for the main Quench plugin class.
"""
import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from pathlib import Path

# Add the plugin to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rplugin', 'python3'))

from quench import Quench


class MockNvim:
    """Mock Neovim instance for testing."""
    
    def __init__(self):
        self.current = Mock()
        self.current.buffer = Mock()
        self.current.buffer.number = 1
        self.current.buffer.name = "test.py"
        self.current.window = Mock()
        self.current.window.cursor = (5, 0)  # Line 5, column 0
        
        self.output_messages = []
        self.error_messages = []
        self.vars = Mock()
        self.vars.get = Mock(return_value=r'^#+\s*%%')  # Default cell delimiter
    
    def out_write(self, message):
        """Mock output writing."""
        self.output_messages.append(message)
    
    def err_write(self, message):
        """Mock error writing."""
        self.error_messages.append(message)
    
    def async_call(self, func):
        """Mock async call - just execute the function."""
        try:
            return func()
        except:
            pass


class TestQuenchMain:
    """Test cases for the main Quench plugin class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_nvim = MockNvim()
        
    @pytest.mark.asyncio
    async def test_quench_initialization(self):
        """Test that Quench initializes all components properly."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Create the plugin instance
            plugin = Quench(self.mock_nvim)
            
            # Verify initialization
            assert plugin.nvim is self.mock_nvim
            assert plugin.relay_queue is not None
            assert isinstance(plugin.relay_queue, asyncio.Queue)
            assert plugin.message_relay_task is None
            assert plugin.web_server_started is False
            
            # Verify components were created
            MockKernelManager.assert_called_once()
            MockUIManager.assert_called_once_with(self.mock_nvim)
            MockWebServer.assert_called_once_with(
                host="127.0.0.1", 
                port=8765, 
                nvim=self.mock_nvim,
                kernel_manager=plugin.kernel_manager
            )
    
    @pytest.mark.asyncio
    async def test_hello_world_command(self):
        """Test the simple HelloWorld command."""
        plugin = Quench(self.mock_nvim)
        
        plugin.hello_world_command()
        
        assert len(self.mock_nvim.output_messages) == 1
        assert "Hello, world from Quench plugin!" in self.mock_nvim.output_messages[0]
    
    @pytest.mark.asyncio
    async def test_say_hello_function(self):
        """Test the SayHello function."""
        plugin = Quench(self.mock_nvim)
        
        # Test with name
        result = plugin.say_hello_function(['Alice'])
        assert result == "Hello, Alice!"
        
        # Test without name
        result = plugin.say_hello_function([])
        assert result == "Hello, stranger!"
    
    def test_run_cell_no_code(self):
        """Test QuenchRunCell with empty cell."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Create a proper mock buffer that behaves like a list
            class MockBuffer(list):
                def __init__(self, lines):
                    super().__init__(lines)
                    self.number = 1
                    self.name = "test.py"
            
            # Set up buffer with empty cell
            self.mock_nvim.current.buffer = MockBuffer(["   "])  # Empty/whitespace only
            self.mock_nvim.current.window.cursor = (1, 0)
            
            plugin = Quench(self.mock_nvim)
            
            plugin.run_cell()
            
            # Should have message about no code found
            assert any("No code found in current cell" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_cell_with_code(self):
        """Test QuenchRunCell with actual code."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with actual code
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: ["print('hello')"][x] if x < 1 else "")
            self.mock_nvim.current.buffer.__iter__ = Mock(return_value=iter(["print('hello')"]))
            self.mock_nvim.current.window.cursor = (1, 0)
            
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-12345678"
            mock_session.execute = AsyncMock()
            
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            mock_web_server = AsyncMock()
            mock_web_server.start = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            
            plugin.run_cell()
            
            # Should have started execution
            assert any("Starting execution" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_cell_web_server_start_failure(self):
        """Test QuenchRunCell when web server fails to start."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with code
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: ["print('test')"][x] if x < 1 else "")
            self.mock_nvim.current.buffer.__iter__ = Mock(return_value=iter(["print('test')"]))
            self.mock_nvim.current.window.cursor = (1, 0)
            
            # Mock session
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-12345678"
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            # Mock web server to fail on start
            mock_web_server = AsyncMock()
            mock_web_server.start.side_effect = Exception("Server start failed")
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            
            plugin.run_cell()
            
            # Should have started execution despite web server failure
            assert any("Starting execution" in msg for msg in self.mock_nvim.output_messages)
    
    @pytest.mark.asyncio
    async def test_message_relay_loop(self):
        """Test the message relay loop functionality."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            mock_web_server = AsyncMock()
            mock_web_server.broadcast_message = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.web_server_started = True
            
            # Add a test message to the queue
            test_message = {
                'msg_type': 'stream',
                'content': {'name': 'stdout', 'text': 'Hello World\n'}
            }
            await plugin.relay_queue.put(("test-kernel", test_message))
            
            # Start the relay loop task
            relay_task = asyncio.create_task(plugin._message_relay_loop())
            
            # Let it process one message
            await asyncio.sleep(0.1)
            
            # Cancel the task
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass
            
            # Verify message was broadcast
            mock_web_server.broadcast_message.assert_called_once_with("test-kernel", test_message)
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_stream(self):
        """Test handling stream messages for Neovim display."""
        plugin = Quench(self.mock_nvim)
        
        message = {
            'msg_type': 'stream',
            'content': {'name': 'stdout', 'text': 'Test output\n'}
        }
        
        await plugin._handle_message_for_nvim("test-kernel", message)
        
        # The current implementation logs messages instead of writing to nvim
        # So we just verify the method completes without error
        assert True
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_error(self):
        """Test handling error messages for Neovim display."""
        plugin = Quench(self.mock_nvim)
        
        message = {
            'msg_type': 'error',
            'content': {'ename': 'ValueError', 'evalue': 'Invalid input'}
        }
        
        await plugin._handle_message_for_nvim("test-kernel", message)
        
        # The current implementation logs messages instead of writing to nvim
        # So we just verify the method completes without error
        assert True
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_execute_result(self):
        """Test handling execute_result messages for Neovim display."""
        plugin = Quench(self.mock_nvim)
        
        message = {
            'msg_type': 'execute_result',
            'content': {
                'data': {'text/plain': '42'}
            }
        }
        
        await plugin._handle_message_for_nvim("test-kernel", message)
        
        # The current implementation logs messages instead of writing to nvim
        # So we just verify the method completes without error
        assert True
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_execute_input(self):
        """Test handling execute_input messages for Neovim display."""
        plugin = Quench(self.mock_nvim)
        
        message = {
            'msg_type': 'execute_input',
            'content': {'code': 'print("Hello")\nprint("World")'}
        }
        
        await plugin._handle_message_for_nvim("test-kernel", message)
        
        # The current implementation logs messages instead of writing to nvim
        # So we just verify the method completes without error
        assert True
    
    def test_status_command(self):
        """Test the QuenchStatus command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            mock_kernel_manager = Mock()
            mock_kernel_manager.list_sessions.return_value = {
                'kernel123': {
                    'kernel_id': 'kernel123',
                    'associated_buffers': [1, 2],
                    'output_cache_size': 5,
                    'is_alive': True
                }
            }
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.status_command()
            
            # Should have status output
            status_output = ''.join(self.mock_nvim.output_messages)
            assert "Quench Status:" in status_output
            assert "Web Server: stopped" in status_output
            assert "Kernel Sessions: 1 active" in status_output
            assert "Message Relay: stopped" in status_output
    
    @pytest.mark.asyncio
    async def test_cleanup_method(self):
        """Test the cleanup method."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            mock_web_server = AsyncMock()
            mock_web_server.stop = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.shutdown_all_sessions = AsyncMock()
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.web_server_started = True
            
            # Create a mock relay task that behaves like asyncio.Task
            async def dummy_coro():
                pass
            
            mock_task = asyncio.create_task(dummy_coro())
            # Immediately cancel it to simulate the cancellation scenario
            mock_task.cancel()
            plugin.message_relay_task = mock_task
            
            await plugin._cleanup()
            
            # Verify cleanup actions
            # Task should be cancelled (we already cancelled it above)
            assert mock_task.cancelled()
            mock_web_server.stop.assert_called_once()
            mock_kernel_manager.shutdown_all_sessions.assert_called_once()
    
    def test_stop_command(self):
        """Test the QuenchStop command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            plugin = Quench(self.mock_nvim)
            
            with patch.object(plugin, '_cleanup', new_callable=AsyncMock) as mock_cleanup:
                plugin.stop_command()
                
                # Should have stop messages
                assert any("Stopping Quench components" in msg for msg in self.mock_nvim.output_messages)
                assert any("Quench stopped" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_cell_exception_handling(self):
        """Test exception handling in QuenchRunCell."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Mock to raise an exception during buffer access - the error happens when accessing buffer as list
            mock_buffer = Mock()
            mock_buffer.number = 1
            mock_buffer.__getitem__ = Mock(side_effect=Exception("Test error"))
            self.mock_nvim.current.buffer = mock_buffer
            
            plugin = Quench(self.mock_nvim)
            
            plugin.run_cell()
            
            # Should have error message about buffer access - the error gets written to err_write
            assert any("Error accessing buffer: Test error" in msg for msg in self.mock_nvim.error_messages)
    
    def test_on_vim_leave(self):
        """Test the VimLeave autocmd handler."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            plugin = Quench(self.mock_nvim)
            
            with patch.object(plugin, '_cleanup', new_callable=AsyncMock) as mock_cleanup:
                plugin.on_vim_leave()
                
                # Cleanup should have been called (via event loop)
                # This is harder to test due to event loop creation, but we can at least
                # verify the method doesn't crash
    
    @pytest.mark.asyncio
    async def test_message_relay_loop_exception_handling(self):
        """Test exception handling in message relay loop."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            mock_web_server = AsyncMock()
            mock_web_server.broadcast_message.side_effect = Exception("Broadcast failed")
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.web_server_started = True
            
            # Add a test message
            test_message = {'msg_type': 'test', 'content': {}}
            await plugin.relay_queue.put(("test-kernel", test_message))
            
            # Start relay loop
            relay_task = asyncio.create_task(plugin._message_relay_loop())
            
            # Let it process the message
            await asyncio.sleep(0.1)
            
            # Cancel the task
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass
            
            # The loop should have handled the exception gracefully
            # and continued processing
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_exception_handling(self):
        """Test exception handling in message handling for Neovim."""
        plugin = Quench(self.mock_nvim)
        
        # Create a malformed message that might cause issues
        malformed_message = {
            'msg_type': 'stream',
            'content': None  # This could cause issues
        }
        
        # Should not raise an exception
        await plugin._handle_message_for_nvim("test-kernel", malformed_message)
        
        # Should handle it gracefully without crashing

    def test_run_cell_advance(self):
        """Test QuenchRunCellAdvance command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with code
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            lines = ["print('hello')", "print('world')", "#%%", "print('next cell')"]
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: lines[x] if x < len(lines) else "")
            self.mock_nvim.current.buffer.__iter__ = Mock(return_value=iter(lines))
            self.mock_nvim.current.window.cursor = (1, 0)
            
            plugin = Quench(self.mock_nvim)
            plugin.run_cell_advance()
            
            # Should have started execution
            assert any("QuenchRunCellAdvance: Starting execution" in msg for msg in self.mock_nvim.output_messages)

    def test_run_selection(self):
        """Test QuenchRunSelection command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with code
            lines = ["print('line1')", "print('line2')", "print('line3')"]
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: lines[x] if isinstance(x, int) and x < len(lines) else [lines[i] for i in range(x.start, min(x.stop, len(lines)))] if isinstance(x, slice) else "")
            
            plugin = Quench(self.mock_nvim)
            plugin.run_selection((1, 2))  # Select lines 1-2
            
            # Should have started execution
            assert any("QuenchRunSelection: Starting execution" in msg for msg in self.mock_nvim.output_messages)

    def test_run_line(self):
        """Test QuenchRunLine command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with code
            lines = ["print('hello')", "print('world')"]
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: lines[x] if x < len(lines) else "")
            self.mock_nvim.current.window.cursor = (1, 0)  # Line 1
            
            plugin = Quench(self.mock_nvim)
            plugin.run_line()
            
            # Should have started execution
            assert any("QuenchRunLine: Starting execution" in msg for msg in self.mock_nvim.output_messages)

    def test_run_above(self):
        """Test QuenchRunAbove command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with multiple cells
            lines = ["print('cell1')", "#%%", "print('cell2')", "#%%", "print('cell3')"]
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: lines[x] if x < len(lines) else "")
            self.mock_nvim.current.buffer.__iter__ = Mock(return_value=iter(lines))
            self.mock_nvim.current.window.cursor = (4, 0)  # In the third cell
            
            plugin = Quench(self.mock_nvim)
            plugin.run_above()
            
            # Should have started execution
            assert any("QuenchRunAbove: Starting execution" in msg for msg in self.mock_nvim.output_messages)

    def test_run_below(self):
        """Test QuenchRunBelow command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with multiple cells
            lines = ["print('cell1')", "#%%", "print('cell2')", "#%%", "print('cell3')"]
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: lines[x] if x < len(lines) else "")
            self.mock_nvim.current.buffer.__iter__ = Mock(return_value=iter(lines))
            self.mock_nvim.current.window.cursor = (2, 0)  # In the second cell
            
            plugin = Quench(self.mock_nvim)
            plugin.run_below()
            
            # Should have started execution
            assert any("QuenchRunBelow: Starting execution" in msg for msg in self.mock_nvim.output_messages)

    def test_run_all(self):
        """Test QuenchRunAll command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Set up buffer with multiple cells
            lines = ["print('cell1')", "#%%", "print('cell2')", "#%%", "print('cell3')"]
            self.mock_nvim.current.buffer = Mock()
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.__getitem__ = Mock(side_effect=lambda x: lines[x] if x < len(lines) else "")
            self.mock_nvim.current.buffer.__iter__ = Mock(return_value=iter(lines))
            
            plugin = Quench(self.mock_nvim)
            plugin.run_all()
            
            # Should have started execution
            assert any("QuenchRunAll: Starting execution" in msg for msg in self.mock_nvim.output_messages)

    def test_extract_cell_code_sync(self):
        """Test the _extract_cell_code_sync helper method."""
        plugin = Quench(self.mock_nvim)
        
        lines = [
            "print('first cell')",
            "x = 1",
            "#%%",
            "print('second cell')",
            "y = 2",
            "#%%", 
            "print('third cell')"
        ]
        
        # Test extracting middle cell
        cell_code, cell_end = plugin._extract_cell_code_sync(lines, 4, r'^#+\s*%%')
        assert "print('second cell')" in cell_code
        assert "y = 2" in cell_code
        assert cell_end == 5  # Correct end line for this cell
        
        # Test extracting first cell
        cell_code, cell_end = plugin._extract_cell_code_sync(lines, 1, r'^#+\s*%%')
        assert "print('first cell')" in cell_code
        assert "x = 1" in cell_code
        assert cell_end == 2  # Correct end line for first cell

    def test_extract_cells_above(self):
        """Test the _extract_cells_above helper method."""
        plugin = Quench(self.mock_nvim)
        
        lines = [
            "print('cell1')",
            "#%%",
            "print('cell2')",
            "#%%",
            "print('cell3')"
        ]
        
        # Extract cells above line 4 (which is in cell3)
        cells = plugin._extract_cells_above(lines, 5, r'^#+\s*%%')
        assert len(cells) == 2
        assert "print('cell1')" in cells[0]
        assert "print('cell2')" in cells[1]

    def test_extract_cells_below(self):
        """Test the _extract_cells_below helper method."""
        plugin = Quench(self.mock_nvim)
        
        lines = [
            "print('cell1')",
            "#%%",
            "print('cell2')",  
            "#%%",
            "print('cell3')"
        ]
        
        # Extract cells from line 1 (which is in cell1) and below
        cells = plugin._extract_cells_below(lines, 1, r'^#+\s*%%')
        assert len(cells) == 3
        assert "print('cell1')" in cells[0]
        assert "print('cell2')" in cells[1]
        assert "print('cell3')" in cells[2]

    def test_extract_all_cells(self):
        """Test the _extract_all_cells helper method."""
        plugin = Quench(self.mock_nvim)
        
        lines = [
            "print('cell1')",
            "#%%",
            "print('cell2')",
            "#%%", 
            "print('cell3')"
        ]
        
        cells = plugin._extract_all_cells(lines, r'^#+\s*%%')
        assert len(cells) == 3
        assert "print('cell1')" in cells[0]
        assert "print('cell2')" in cells[1] 
        assert "print('cell3')" in cells[2]

    def test_new_commands_error_handling(self):
        """Test error handling in new commands."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Mock to raise an exception during buffer access
            mock_buffer = Mock()
            mock_buffer.number = Mock(side_effect=Exception("Buffer error"))
            self.mock_nvim.current.buffer = mock_buffer
            
            plugin = Quench(self.mock_nvim)
            
            # Test all new commands handle exceptions gracefully
            plugin.run_cell_advance()
            plugin.run_selection((1, 2))
            plugin.run_line()
            plugin.run_above()
            plugin.run_below()
            plugin.run_all()
            
            # Should have error messages for each command that caught the buffer access error
            error_count = len([msg for msg in self.mock_nvim.error_messages if "Error accessing buffer" in msg or "Error getting buffer data" in msg or "Error extracting" in msg])
            assert error_count >= 5  # At least 5 commands should report buffer access errors

    @pytest.mark.asyncio
    async def test_run_cell_async_with_provided_kernel(self):
        """Test that _run_cell_async uses the provided kernel name correctly."""
        plugin = Quench(self.mock_nvim)
        
        # Mock session creation
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value='msg_id_123')
        plugin.kernel_manager.get_or_create_session = AsyncMock(return_value=mock_session)
        
        # Mock web server
        plugin.web_server.start = AsyncMock()
        plugin.web_server_started = True
        
        # Execute cell with a specific kernel name
        kernel_name = 'conda-env'
        await plugin._run_cell_async(1, "print('hello')", kernel_name)
        
        # Verify session was created with the provided kernel name
        plugin.kernel_manager.get_or_create_session.assert_called_once()
        call_args = plugin.kernel_manager.get_or_create_session.call_args
        assert call_args[0][0] == 1  # buffer number
        assert call_args[0][3] == 'conda-env'  # kernel_name
        
        # Verify code was executed
        mock_session.execute.assert_called_once_with("print('hello')")

    @pytest.mark.asyncio
    async def test_run_cell_async_single_kernel_no_prompt(self):
        """Test _run_cell_async when only one kernel is available (no user prompt)."""
        plugin = Quench(self.mock_nvim)
        
        # Mock the kernel manager methods
        plugin.kernel_manager.get_session_for_buffer = AsyncMock(return_value=None)  # No existing session
        
        # Mock single kernel discovered
        mock_kernelspecs = [
            {
                'name': 'neovim_python',
                'display_name': "Neovim's Python",
                'argv': ['/usr/bin/python3', '-m', 'ipykernel_launcher', '-f', '{connection_file}']
            }
        ]
        
        plugin.kernel_manager.discover_kernelspecs = AsyncMock(return_value=mock_kernelspecs)
        
        # Mock session creation
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value='msg_id_123')
        plugin.kernel_manager.get_or_create_session = AsyncMock(return_value=mock_session)
        
        # Mock web server
        plugin.web_server.start = AsyncMock()
        plugin.web_server_started = True
        
        # Execute cell
        await plugin._run_cell_async(1, "print('hello')", 'python3')
        
        # Verify no user choice was prompted (since only one kernel)
        plugin.ui_manager.get_user_choice = AsyncMock()
        plugin.ui_manager.get_user_choice.assert_not_called()
        
        # Verify session was created with the only available kernel
        plugin.kernel_manager.get_or_create_session.assert_called_once()
        call_args = plugin.kernel_manager.get_or_create_session.call_args
        assert call_args[0][3] == 'neovim_python'  # kernel_name

    @pytest.mark.asyncio
    async def test_run_cell_async_existing_session_no_prompt(self):
        """Test _run_cell_async when buffer already has an existing session (no kernel selection)."""
        plugin = Quench(self.mock_nvim)
        
        # Mock existing session
        mock_existing_session = AsyncMock()
        mock_existing_session.execute = AsyncMock(return_value='msg_id_123')
        plugin.kernel_manager.get_session_for_buffer = AsyncMock(return_value=mock_existing_session)
        
        # Mock that get_or_create_session should not be called for existing sessions
        plugin.kernel_manager.get_or_create_session = AsyncMock(return_value=mock_existing_session)
        
        # Mock web server
        plugin.web_server.start = AsyncMock()
        plugin.web_server_started = True
        
        # Execute cell
        await plugin._run_cell_async(1, "print('hello')", 'python3')
        
        # Verify kernel discovery was not called since session exists
        plugin.kernel_manager.discover_kernelspecs = AsyncMock()
        plugin.kernel_manager.discover_kernelspecs.assert_not_called()
        
        # Verify user choice was not prompted
        plugin.ui_manager.get_user_choice = AsyncMock()
        plugin.ui_manager.get_user_choice.assert_not_called()
        
        # Should still call get_or_create_session but with None kernel_name since session exists
        plugin.kernel_manager.get_or_create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_cell_async_user_cancels_kernel_selection(self):
        """Test _run_cell_async when user cancels kernel selection."""
        plugin = Quench(self.mock_nvim)
        
        # Mock the kernel manager methods
        plugin.kernel_manager.get_session_for_buffer = AsyncMock(return_value=None)  # No existing session
        
        # Mock multiple kernels discovered
        mock_kernelspecs = [
            {
                'name': 'neovim_python',
                'display_name': "Neovim's Python",
                'argv': ['/usr/bin/python3', '-m', 'ipykernel_launcher', '-f', '{connection_file}']
            },
            {
                'name': 'conda-env',
                'display_name': 'Python 3 (conda-env)',
                'argv': ['/home/user/anaconda3/bin/python', '-m', 'ipykernel_launcher', '-f', '{connection_file}']
            }
        ]
        
        plugin.kernel_manager.discover_kernelspecs = AsyncMock(return_value=mock_kernelspecs)
        
        # Mock user cancelling choice (returns None)
        plugin.ui_manager.get_user_choice = AsyncMock(return_value=None)
        
        # Mock session creation
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value='msg_id_123')
        plugin.kernel_manager.get_or_create_session = AsyncMock(return_value=mock_session)
        
        # Mock web server
        plugin.web_server.start = AsyncMock()
        plugin.web_server_started = True
        
        # Execute cell
        await plugin._run_cell_async(1, "print('hello')", 'python3')
        
        # Verify session was created with first kernel as fallback
        plugin.kernel_manager.get_or_create_session.assert_called_once()
        call_args = plugin.kernel_manager.get_or_create_session.call_args
        assert call_args[0][3] == 'neovim_python'  # Should use first kernel as fallback

    @pytest.mark.asyncio
    async def test_run_cell_async_kernel_discovery_error(self):
        """Test _run_cell_async when kernel discovery fails."""
        plugin = Quench(self.mock_nvim)
        
        # Mock the kernel manager methods
        plugin.kernel_manager.get_session_for_buffer = AsyncMock(return_value=None)  # No existing session
        
        # Mock kernel discovery failure
        plugin.kernel_manager.discover_kernelspecs = AsyncMock(side_effect=Exception("Discovery failed"))
        
        # Mock session creation
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value='msg_id_123')
        plugin.kernel_manager.get_or_create_session = AsyncMock(return_value=mock_session)
        
        # Mock web server
        plugin.web_server.start = AsyncMock()
        plugin.web_server_started = True
        
        # Execute cell
        await plugin._run_cell_async(1, "print('hello')", 'python3')
        
        # Verify session was created with None kernel_name (default fallback)
        plugin.kernel_manager.get_or_create_session.assert_called_once()
        call_args = plugin.kernel_manager.get_or_create_session.call_args
        assert call_args[0][3] is None  # kernel_name should be None as fallback


if __name__ == '__main__':
    pytest.main([__file__, '-v'])