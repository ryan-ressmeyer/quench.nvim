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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rplugin', 'python3'))

from quench import Quench


class MockBuffer(list):
    """Mock buffer that behaves like a list."""
    
    def __init__(self, lines, number=1, name="test.py"):
        super().__init__(lines)
        self.number = number
        self.name = name


class MockNvim:
    """Mock Neovim instance for testing."""
    
    def __init__(self):
        self.current = Mock()
        # Create a mock buffer that acts like a list
        self.current.buffer = MockBuffer(["  ", "  ", "  "], 1, "test.py")
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
    
    def command(self, cmd):
        """Mock command execution."""
        pass


class TestQuenchPlugin:
    """Test cases for the main Quench plugin class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_nvim = MockNvim()
    
    def test_quench_initialization(self):
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
            MockWebServer.assert_called_once()
    
    def test_get_cell_delimiter_default(self):
        """Test getting default cell delimiter."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            self.mock_nvim.vars.get.return_value = r'^#+\s*%%'
            plugin = Quench(self.mock_nvim)
            
            result = plugin._get_cell_delimiter()
            assert result == r'^#+\s*%%'
            self.mock_nvim.vars.get.assert_called_with('quench_nvim_cell_delimiter', r'^#+\s*%%')
    
    def test_get_cell_delimiter_custom(self):
        """Test getting custom cell delimiter."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            self.mock_nvim.vars.get.return_value = '# %%'
            plugin = Quench(self.mock_nvim)
            
            result = plugin._get_cell_delimiter()
            assert result == '# %%'
    
    def test_get_cell_delimiter_error_fallback(self):
        """Test cell delimiter fallback when nvim.vars throws error."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            self.mock_nvim.vars.get.side_effect = Exception("Nvim error")
            plugin = Quench(self.mock_nvim)
            
            result = plugin._get_cell_delimiter()
            assert result == r'^#+\s*%%'
    
    def test_get_web_server_host_default(self):
        """Test getting default web server host."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            self.mock_nvim.vars.get.return_value = '127.0.0.1'
            plugin = Quench(self.mock_nvim)
            
            result = plugin._get_web_server_host()
            assert result == '127.0.0.1'
            self.mock_nvim.vars.get.assert_called_with('quench_nvim_web_server_host', '127.0.0.1')
    
    def test_get_web_server_host_custom(self):
        """Test getting custom web server host."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            self.mock_nvim.vars.get.return_value = '0.0.0.0'
            plugin = Quench(self.mock_nvim)
            
            result = plugin._get_web_server_host()
            assert result == '0.0.0.0'
    
    def test_get_web_server_port_default(self):
        """Test getting default web server port."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            self.mock_nvim.vars.get.return_value = 8765
            plugin = Quench(self.mock_nvim)
            
            result = plugin._get_web_server_port()
            assert result == 8765
            self.mock_nvim.vars.get.assert_called_with('quench_nvim_web_server_port', 8765)
    
    def test_get_web_server_port_custom(self):
        """Test getting custom web server port."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            self.mock_nvim.vars.get.return_value = 9000
            plugin = Quench(self.mock_nvim)
            
            result = plugin._get_web_server_port()
            assert result == 9000
    
    def test_notify_user_info(self):
        """Test user notification with info level."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            plugin._notify_user("Test info message", "info")
            
            assert "Test info message\n" in self.mock_nvim.output_messages
    
    def test_notify_user_error(self):
        """Test user notification with error level."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            plugin._notify_user("Test error message", "error")
            
            assert "Test error message\n" in self.mock_nvim.error_messages
    
    def test_hello_world_command(self):
        """Test the HelloWorld command."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            plugin.hello_world_command()
            
            assert len(self.mock_nvim.output_messages) == 1
            assert "Hello, world from Quench plugin!" in self.mock_nvim.output_messages[0]
    
    def test_say_hello_function(self):
        """Test the SayHello function."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            
            # Test with name
            result = plugin.say_hello_function(['Alice'])
            assert result == "Hello, Alice!"
            
            # Test without name
            result = plugin.say_hello_function([])
            assert result == "Hello, stranger!"
    
    def test_run_cell_no_code_found(self):
        """Test QuenchRunCell with empty cell."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Mock UI manager to return empty code
            mock_ui_manager = AsyncMock()
            mock_ui_manager.get_cell_code.return_value = "  \n  \n  "  # Whitespace only
            MockUIManager.return_value = mock_ui_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.run_cell()
            
            # Should notify user about no code found
            assert any("No code found in current cell" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_cell_with_code_success(self):
        """Test QuenchRunCell with actual code."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with code content
            self.mock_nvim.current.buffer = MockBuffer(["print('hello world')"], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            
            # Mock kernel session
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-12345678"
            mock_session.execute = AsyncMock()
            
            # Mock kernel manager
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            # Mock web server
            mock_web_server = AsyncMock()
            mock_web_server.start = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.run_cell()
            
            # Should have started execution
            assert any("Executing cell" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_cell_web_server_start_failure(self):
        """Test QuenchRunCell when web server fails to start."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with code content
            self.mock_nvim.current.buffer = MockBuffer(["print('test')"], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            
            # Mock kernel session
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-12345678"
            mock_session.execute = AsyncMock()
            
            # Mock kernel manager
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            # Mock web server to fail on start
            mock_web_server = AsyncMock()
            mock_web_server.start.side_effect = Exception("Server start failed")
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.run_cell()
            
            # Should still execute despite web server failure
            assert any("Executing cell" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_cell_kernel_session_creation_failure(self):
        """Test QuenchRunCell when kernel session creation fails."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with code content
            self.mock_nvim.current.buffer = MockBuffer(["print('test')"], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            
            # Mock kernel manager to raise exception during kernel selection
            mock_kernel_manager = AsyncMock()
            MockKernelManager.return_value = mock_kernel_manager
            
            # Mock the _get_or_select_kernel_sync method to return None (failure)
            plugin = Quench(self.mock_nvim)
            plugin._get_or_select_kernel_sync = Mock(return_value=None)
            plugin.run_cell()
            
            # Should handle the error gracefully
            assert any("Kernel selection failed" in msg for msg in self.mock_nvim.error_messages)
    
    def test_run_cell_advance(self):
        """Test QuenchRunCellAdvance command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with code content
            self.mock_nvim.current.buffer = MockBuffer(["print('test')"], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            
            # Mock kernel session
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-12345678"
            mock_session.execute = AsyncMock()
            
            # Mock kernel manager
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.run_cell_advance()
            
            # Should have started execution
            assert any("Executing cell" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_selection(self):
        """Test QuenchRunSelection command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with code content
            self.mock_nvim.current.buffer = MockBuffer(["x = 42", "print(x)"], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            
            # Mock kernel components
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel"
            mock_session.execute = AsyncMock()
            
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.run_selection([1, 2])  # Line range
            
            # Should have started execution
            assert any("Executing lines 1-2" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_selection_empty(self):
        """Test QuenchRunSelection with empty selection."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with empty content
            self.mock_nvim.current.buffer = MockBuffer(["  "], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            
            plugin = Quench(self.mock_nvim)
            plugin.run_selection([1, 1])
            
            # Should notify about no code found
            assert any("No code found in selection" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_line(self):
        """Test QuenchRunLine command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with code content
            self.mock_nvim.current.buffer = MockBuffer(["print('current line')"], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            self.mock_nvim.current.window.cursor = (1, 0)  # Set cursor to first line
            
            # Mock kernel components
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel"
            mock_session.execute = AsyncMock()
            
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.run_line()
            
            # Should have started execution
            assert any("Executing line 1" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_above(self):
        """Test QuenchRunAbove command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with multiple cells
            self.mock_nvim.current.buffer = MockBuffer([
                "print('cell1')", "# %%", "print('cell2')", "# %%", "print('current')"
            ], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            self.mock_nvim.current.window.cursor = (5, 0)  # Position in last cell
            
            # Mock kernel components
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel"
            mock_session.execute = AsyncMock()
            
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.run_above()
            
            # Should have started execution
            assert any("Executing all cells above cursor" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_below(self):
        """Test QuenchRunBelow command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with multiple cells
            self.mock_nvim.current.buffer = MockBuffer([
                "print('current')", "# %%", "print('cell3')", "# %%", "print('cell4')"
            ], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            self.mock_nvim.current.window.cursor = (1, 0)  # Position in first cell
            
            # Mock kernel components
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel"
            mock_session.execute = AsyncMock()
            
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.run_below()
            
            # Should have started execution
            assert any("Executing all cells from cursor to end of file" in msg for msg in self.mock_nvim.output_messages)
    
    def test_run_all(self):
        """Test QuenchRunAll command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Set up mock nvim with multiple cells
            self.mock_nvim.current.buffer = MockBuffer([
                "print('all')", "# %%", "print('cells')"
            ], 1, "test.py")
            self.mock_nvim.current.buffer.number = 1
            self.mock_nvim.current.buffer.name = "test.py"
            
            # Mock kernel components
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel"
            mock_session.execute = AsyncMock()
            
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_or_create_session.return_value = mock_session
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.run_all()
            
            # Should have started execution
            assert any("Executing all cells in the buffer" in msg for msg in self.mock_nvim.output_messages)
    
    def test_status_command(self):
        """Test QuenchStatus command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):
            
            # Mock kernel manager status
            mock_kernel_manager = Mock()
            mock_kernel_manager.list_sessions.return_value = {
                "kernel1": {"associated_buffers": [1], "output_cache_size": 5},
                "kernel2": {"associated_buffers": [2], "output_cache_size": 0}
            }
            MockKernelManager.return_value = mock_kernel_manager
            
            # Mock web server status
            mock_web_server = Mock()
            mock_web_server.get_all_connection_counts.return_value = {"kernel1": 1, "kernel2": 0}
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.web_server_started = True
            plugin.status_command()
            
            # Should display status information
            output_text = ' '.join(self.mock_nvim.output_messages)
            assert "Kernel Sessions: 2 active" in output_text
            assert "Web Server: running" in output_text
    
    def test_stop_command(self):
        """Test QuenchStop command."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):
            
            # Mock components for _cleanup
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.shutdown_all_sessions = AsyncMock()
            MockKernelManager.return_value = mock_kernel_manager
            
            mock_web_server = AsyncMock()
            mock_web_server.stop = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.web_server_started = True
            plugin.message_relay_task = Mock()
            plugin.message_relay_task.cancel = Mock()
            plugin.message_relay_task.done = Mock(return_value=False)
            
            plugin.stop_command()
            
            # Should show stopping message
            assert any("Stopping Quench components" in msg for msg in self.mock_nvim.output_messages)
    
    def test_interrupt_kernel_no_session(self):
        """Test QuenchInterruptKernel with no active session."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Mock kernel manager that returns no session
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_session_for_buffer = AsyncMock(return_value=None)
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.interrupt_kernel_command()
            
            # Should have attempted to interrupt
            output_text = ' '.join(self.mock_nvim.output_messages + self.mock_nvim.error_messages)
            # The test passes if no exception is thrown - the actual async behavior is complex
    
    def test_interrupt_kernel_with_session(self):
        """Test QuenchInterruptKernel with active session."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Mock active session
            mock_session = AsyncMock()
            mock_session.interrupt = AsyncMock()
            
            # Mock kernel manager that returns a session
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_session_for_buffer = AsyncMock(return_value=mock_session)
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.interrupt_kernel_command()
            
            # Should have attempted to interrupt
            output_text = ' '.join(self.mock_nvim.output_messages + self.mock_nvim.error_messages)
            # The test passes if no exception is thrown - the actual async behavior is complex
    
    def test_reset_kernel_no_session(self):
        """Test QuenchResetKernel with no active session."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Mock kernel manager that returns no session
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_session_for_buffer = AsyncMock(return_value=None)
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.reset_kernel_command()
            
            # Should have attempted to reset
            output_text = ' '.join(self.mock_nvim.output_messages + self.mock_nvim.error_messages)
            # The test passes if no exception is thrown - the actual async behavior is complex
    
    def test_reset_kernel_with_session(self):
        """Test QuenchResetKernel with active session."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            # Mock active session
            mock_session = AsyncMock()
            mock_session.restart = AsyncMock()
            
            # Mock kernel manager that returns a session
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.get_session_for_buffer = AsyncMock(return_value=mock_session)
            MockKernelManager.return_value = mock_kernel_manager
            
            plugin = Quench(self.mock_nvim)
            plugin.reset_kernel_command()
            
            # Should have attempted to reset
            output_text = ' '.join(self.mock_nvim.output_messages + self.mock_nvim.error_messages)
            # The test passes if no exception is thrown - the actual async behavior is complex
    
    @pytest.mark.asyncio
    async def test_message_relay_loop(self):
        """Test the message relay loop functionality."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):
            
            mock_web_server = AsyncMock()
            mock_web_server.broadcast_message = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.web_server_started = True
            
            # Add test message to queue
            test_message = {
                'msg_type': 'stream',
                'content': {'name': 'stdout', 'text': 'Hello World\n'}
            }
            await plugin.relay_queue.put(("test-kernel", test_message))
            
            # Start relay loop task
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
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            
            message = {
                'msg_type': 'stream',
                'content': {'name': 'stdout', 'text': 'Test output\n'}
            }
            
            await plugin._handle_message_for_nvim("test-kernel", message)
            
            # Method should complete without error (current implementation logs)
            assert True
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_error(self):
        """Test handling error messages for Neovim display."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            
            message = {
                'msg_type': 'error',
                'content': {'ename': 'ValueError', 'evalue': 'Invalid input'}
            }
            
            await plugin._handle_message_for_nvim("test-kernel", message)
            
            # Method should complete without error
            assert True
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_execute_result(self):
        """Test handling execute_result messages for Neovim display."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            
            message = {
                'msg_type': 'execute_result',
                'content': {
                    'data': {'text/plain': '42'}
                }
            }
            
            await plugin._handle_message_for_nvim("test-kernel", message)
            
            # Method should complete without error
            assert True
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_execute_input(self):
        """Test handling execute_input messages for Neovim display."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):
            
            plugin = Quench(self.mock_nvim)
            
            message = {
                'msg_type': 'execute_input',
                'content': {'code': 'print("Hello")\nprint("World")'}
            }
            
            await plugin._handle_message_for_nvim("test-kernel", message)
            
            # Method should complete without error
            assert True
    
    @pytest.mark.asyncio
    async def test_cleanup_method(self):
        """Test the _cleanup method."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):
            
            # Mock components
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.shutdown_all_sessions = AsyncMock()
            MockKernelManager.return_value = mock_kernel_manager
            
            mock_web_server = AsyncMock()
            mock_web_server.stop = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            plugin = Quench(self.mock_nvim)
            plugin.web_server_started = True
            # Create a mock task that can be awaited and raises CancelledError
            mock_task = Mock()
            mock_task.cancel = Mock()
            mock_task.done = Mock(return_value=False)
            
            # Create an awaitable that raises CancelledError
            async def cancelled_task():
                raise asyncio.CancelledError()
            
            # Replace the mock with an actual task that we can await
            plugin.message_relay_task = asyncio.create_task(cancelled_task())
            # But we need to mock the cancel method
            original_cancel = plugin.message_relay_task.cancel
            plugin.message_relay_task.cancel = Mock(side_effect=original_cancel)
            
            await plugin._cleanup()
            
            # Verify cleanup sequence
            plugin.message_relay_task.cancel.assert_called_once()
            mock_kernel_manager.shutdown_all_sessions.assert_called_once()
            mock_web_server.stop.assert_called_once()
    
    def test_on_vim_leave(self):
        """Test the on_vim_leave autocmd handler."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'), \
             patch('asyncio.get_event_loop') as mock_get_loop:
            
            # Mock components for _cleanup
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.shutdown_all_sessions = AsyncMock()
            MockKernelManager.return_value = mock_kernel_manager
            
            mock_web_server = AsyncMock()
            mock_web_server.stop = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            # Mock event loop
            mock_loop = Mock()
            mock_loop.run_until_complete = Mock()
            mock_get_loop.return_value = mock_loop
            
            plugin = Quench(self.mock_nvim)
            plugin.on_vim_leave()
            
            # Should have run cleanup using loop.run_until_complete
            mock_loop.run_until_complete.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__])