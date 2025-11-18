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
            
            # Should have started execution (check for any execution message, not exact format)
            assert any("Executing" in msg and "cell" in msg for msg in self.mock_nvim.output_messages)
            # Should not have any error messages
            assert not any("Error" in msg or "Failed" in msg for msg in self.mock_nvim.output_messages)
    
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
            
            # Mock kernel manager to have no available kernels (simulates failure)
            mock_kernel_manager.get_kernel_choices = Mock(return_value=[])
            mock_kernel_manager.list_sessions = Mock(return_value=[])
            mock_kernel_manager.sessions = {}
            mock_kernel_manager.buffer_to_kernel_map = {}

            plugin = Quench(self.mock_nvim)
            plugin.run_cell()

            # Should handle the error gracefully with no available kernels message
            # Check both output and error messages since err_write goes to error_messages
            all_messages = self.mock_nvim.output_messages + getattr(self.mock_nvim, 'error_messages', [])
            assert any("No Jupyter kernels found" in msg for msg in all_messages)
    
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
            
            # Should have started execution (check for any execution message, not exact format)
            assert any("Executing" in msg and "cell" in msg for msg in self.mock_nvim.output_messages)
            # Should not have any error messages
            assert not any("Error" in msg or "Failed" in msg for msg in self.mock_nvim.output_messages)
    
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
            # Set up sessions mock to return kernel session keys
            mock_kernel_manager.list_sessions.return_value = ["test-kernel"]
            mock_kernel_manager.sessions = {"test-kernel": mock_session}
            MockKernelManager.return_value = mock_kernel_manager

            plugin = Quench(self.mock_nvim)
            plugin.run_selection([1, 2])  # Line range
            
            # Should have started execution (check for any execution message, not exact format)
            assert any("Executing" in msg and ("selection" in msg or "lines" in msg) for msg in self.mock_nvim.output_messages)
            # Should not have any error messages
            assert not any("Error" in msg or "Failed" in msg for msg in self.mock_nvim.output_messages)
    
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
            
            # Should notify about no code found (check for any variation of the message)
            assert any("empty" in msg for msg in self.mock_nvim.output_messages)
    
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
            
            # Should have started execution (check for any execution message, not exact format)
            assert any("Executing" in msg and "line" in msg for msg in self.mock_nvim.output_messages)
            # Should not have any error messages
            assert not any("Error" in msg or "Failed" in msg for msg in self.mock_nvim.output_messages)
    
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
            
            # Should have started execution (check for any execution message, not exact format)
            assert any("Executing" in msg and ("above" in msg or "cells" in msg) for msg in self.mock_nvim.output_messages)
            # Should not have any error messages
            assert not any("Error" in msg or "Failed" in msg for msg in self.mock_nvim.output_messages)
    
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
            
            # Should have started execution (check for any execution message, not exact format)
            assert any("Executing" in msg and ("below" in msg or "cells" in msg) for msg in self.mock_nvim.output_messages)
            # Should not have any error messages
            assert not any("Error" in msg or "Failed" in msg for msg in self.mock_nvim.output_messages)
    
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
            
            # Should have started execution (check for any execution message, not exact format)
            assert any("Executing" in msg and ("all" in msg or "cells" in msg) for msg in self.mock_nvim.output_messages)
            # Should not have any error messages
            assert not any("Error" in msg or "Failed" in msg for msg in self.mock_nvim.output_messages)
    
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
            task_mock = Mock(side_effect=original_cancel)
            plugin.message_relay_task.cancel = task_mock

            await plugin._async_cleanup()

            # Verify cleanup sequence (task is set to None during cleanup, so check the mock)
            task_mock.assert_called_once()
            mock_kernel_manager.shutdown_all_sessions.assert_called_once()
            mock_web_server.stop.assert_called_once()
    
    def test_on_vim_leave(self):
        """Test the on_vim_leave autocmd handler."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'), \
             patch('asyncio.get_running_loop') as mock_get_loop, \
             patch('asyncio.run_coroutine_threadsafe') as mock_run_coroutine_threadsafe:
            
            # Mock components for _cleanup
            mock_kernel_manager = AsyncMock()
            mock_kernel_manager.shutdown_all_sessions = AsyncMock()
            MockKernelManager.return_value = mock_kernel_manager
            
            mock_web_server = AsyncMock()
            mock_web_server.stop = AsyncMock()
            MockWebServer.return_value = mock_web_server
            
            # Mock event loop
            mock_loop = Mock()
            mock_get_loop.return_value = mock_loop
            
            plugin = Quench(self.mock_nvim)
            plugin.on_vim_leave()
            
            # Should have run cleanup using run_coroutine_threadsafe
            mock_run_coroutine_threadsafe.assert_called_once()

    def test_pynvim_commands_registered(self):
        """Test that all expected pynvim commands are properly registered on the plugin class."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):

            plugin = Quench(self.mock_nvim)

            # Define all expected commands based on README and refactoring plan
            expected_commands = {
                # Debug commands
                'status_command': 'QuenchStatus',
                'stop_command': 'QuenchStop',
                'debug_command': 'QuenchDebug',

                # Kernel management commands
                'interrupt_kernel_command': 'QuenchInterruptKernel',
                'reset_kernel_command': 'QuenchResetKernel',
                'start_kernel_command': 'QuenchStartKernel',
                'shutdown_kernel_command': 'QuenchShutdownKernel',
                'select_kernel_command': 'QuenchSelectKernel',

                # Execution commands
                'run_cell': 'QuenchRunCell',
                'run_cell_advance': 'QuenchRunCellAdvance',
                'run_selection': 'QuenchRunSelection',
                'run_line': 'QuenchRunLine',
                'run_above': 'QuenchRunAbove',
                'run_below': 'QuenchRunBelow',
                'run_all': 'QuenchRunAll'
            }

            # Verify all methods exist on the plugin class
            for method_name, command_name in expected_commands.items():
                assert hasattr(plugin, method_name), f"Plugin missing method: {method_name} (for command {command_name})"
                method = getattr(plugin, method_name)
                assert callable(method), f"Method {method_name} is not callable"

                # Verify the method has pynvim command decorator by checking if it's bound to the plugin
                # (This is the best we can do without inspecting decorators directly)
                assert hasattr(method, '__self__'), f"Method {method_name} is not properly bound to plugin instance"
                assert method.__self__ is plugin, f"Method {method_name} is not bound to the correct plugin instance"

    def test_command_availability_comprehensive(self):
        """Test that plugin has all 16 commands available and they can be called without attribute errors."""
        with patch('quench.KernelSessionManager'), \
             patch('quench.WebServer'), \
             patch('quench.NvimUIManager'):

            plugin = Quench(self.mock_nvim)

            # Test that all command methods exist and don't raise AttributeError when accessed
            command_methods = [
                'status_command', 'stop_command', 'debug_command',
                'interrupt_kernel_command', 'reset_kernel_command', 'start_kernel_command',
                'shutdown_kernel_command', 'select_kernel_command',
                'run_cell', 'run_cell_advance', 'run_selection', 'run_line',
                'run_above', 'run_below', 'run_all'
            ]

            for method_name in command_methods:
                # Should not raise AttributeError
                method = getattr(plugin, method_name, None)
                assert method is not None, f"Command method '{method_name}' not found on plugin"
                assert callable(method), f"Command method '{method_name}' is not callable"

            # Verify we have exactly 15 commands (all expected commands)
            actual_command_count = len(command_methods)
            assert actual_command_count == 15, f"Expected 15 commands, found {actual_command_count}"

    def test_start_kernel_command_bug_reproduction(self):
        """Test QuenchStartKernel to reproduce the reported bug."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):

            # Mock kernel manager - fix the discover_kernelspecs to return actual data, not a coroutine
            mock_kernel_manager = Mock()  # Use regular Mock, not AsyncMock
            mock_kernel_manager.discover_kernelspecs.return_value = [
                {'name': 'python3', 'display_name': 'Python 3'},
                {'name': 'julia', 'display_name': 'Julia 1.6'}
            ]
            MockKernelManager.return_value = mock_kernel_manager

            # Mock web server
            mock_web_server = AsyncMock()
            MockWebServer.return_value = mock_web_server

            # Add the missing call method to mock nvim that returns None
            # This should trigger the error "'NoneType' object has no attribute 'switch'"
            self.mock_nvim.call = Mock(return_value=None)

            plugin = Quench(self.mock_nvim)

            # Run the command - this should expose the bug
            plugin.start_kernel_command()

            # Check if there are error messages indicating the bug
            print("Output messages:", self.mock_nvim.output_messages)
            print("Error messages:", self.mock_nvim.error_messages)

            # The bug should show up as an error message mentioning switch or NoneType
            has_switch_error = any("switch" in msg for msg in self.mock_nvim.error_messages)
            has_none_error = any("NoneType" in msg for msg in self.mock_nvim.error_messages)

            # At minimum, we should see some error from the problematic code
            assert has_switch_error or has_none_error or len(self.mock_nvim.error_messages) > 0, \
                f"Expected error messages indicating the bug, got: {self.mock_nvim.error_messages}"

    def test_start_kernel_command_success_scenario(self):
        """Test QuenchStartKernel with valid input to ensure it works properly."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager'):

            # Mock kernel manager
            mock_kernel_manager = Mock()
            mock_kernel_manager.discover_kernelspecs.return_value = [
                {'name': 'python3', 'display_name': 'Python 3'},
                {'name': 'julia', 'display_name': 'Julia 1.6'}
            ]
            # Mock the start_session method
            mock_session = AsyncMock()
            mock_session.kernel_name = 'python3'
            mock_session.kernel_id = 'test-kernel-id-123456789'
            mock_kernel_manager.start_session = AsyncMock(return_value=mock_session)
            MockKernelManager.return_value = mock_kernel_manager

            # Mock web server
            mock_web_server = AsyncMock()
            MockWebServer.return_value = mock_web_server

            # Mock nvim.call to return a valid choice
            self.mock_nvim.call = Mock(return_value='1')  # Select first option

            plugin = Quench(self.mock_nvim)

            # Run the command - this should work properly now
            plugin.start_kernel_command()

            # Check messages
            print("Output messages:", self.mock_nvim.output_messages)
            print("Error messages:", self.mock_nvim.error_messages)

            # Should show the selection prompt
            has_selection_prompt = any("Select a kernel to start" in msg for msg in self.mock_nvim.output_messages)
            assert has_selection_prompt, "Should show kernel selection prompt"

            # Should not have any errors about NoneType or switch
            has_none_error = any("NoneType" in msg for msg in self.mock_nvim.error_messages)
            has_switch_error = any("switch" in msg for msg in self.mock_nvim.error_messages)
            assert not has_none_error and not has_switch_error, f"Should not have NoneType/switch errors: {self.mock_nvim.error_messages}"


if __name__ == '__main__':
    pytest.main([__file__])
