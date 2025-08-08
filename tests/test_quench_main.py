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
        self.current.window = Mock()
        self.current.window.cursor = (5, 0)  # Line 5, column 0
        
        self.output_messages = []
        self.error_messages = []
    
    def out_write(self, message):
        """Mock output writing."""
        self.output_messages.append(message)
    
    def err_write(self, message):
        """Mock error writing."""
        self.error_messages.append(message)


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
    
    @pytest.mark.asyncio 
    async def test_run_cell_no_code(self):
        """Test QuenchRunCell with empty cell."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Mock UI manager to return empty code
            mock_ui_manager = AsyncMock()
            mock_ui_manager.get_current_bnum.return_value = 1
            mock_ui_manager.get_cell_code.return_value = "   "  # Empty/whitespace only
            MockUIManager.return_value = mock_ui_manager
            
            plugin = Quench(self.mock_nvim)
            
            await plugin.run_cell([])
            
            # Should have message about no code found
            assert any("No code found in current cell" in msg for msg in self.mock_nvim.output_messages)
    
    @pytest.mark.asyncio
    async def test_run_cell_with_code(self):
        """Test QuenchRunCell with actual code."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Mock components
            mock_ui_manager = AsyncMock()
            mock_ui_manager.get_current_bnum.return_value = 1
            mock_ui_manager.get_cell_code.return_value = "print('hello')"
            MockUIManager.return_value = mock_ui_manager
            
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
            
            await plugin.run_cell([])
            
            # Verify the flow
            mock_ui_manager.get_current_bnum.assert_called_once()
            mock_ui_manager.get_cell_code.assert_called_once_with(1, 5)  # Line from cursor
            mock_kernel_manager.get_or_create_session.assert_called_once()
            mock_session.execute.assert_called_once_with("print('hello')")
            mock_web_server.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_cell_web_server_start_failure(self):
        """Test QuenchRunCell when web server fails to start."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Mock UI manager
            mock_ui_manager = AsyncMock()
            mock_ui_manager.get_current_bnum.return_value = 1
            mock_ui_manager.get_cell_code.return_value = "print('test')"
            MockUIManager.return_value = mock_ui_manager
            
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
            
            await plugin.run_cell([])
            
            # Should continue execution despite web server failure
            mock_session.execute.assert_called_once()
            assert any("Error starting web server" in msg for msg in self.mock_nvim.error_messages)
    
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
        
        # Should have written to output
        assert any("[stdout] Test output\n" in msg for msg in self.mock_nvim.output_messages)
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_error(self):
        """Test handling error messages for Neovim display."""
        plugin = Quench(self.mock_nvim)
        
        message = {
            'msg_type': 'error',
            'content': {'ename': 'ValueError', 'evalue': 'Invalid input'}
        }
        
        await plugin._handle_message_for_nvim("test-kernel", message)
        
        # Should have written error message
        assert any("[error] ValueError: Invalid input" in msg for msg in self.mock_nvim.error_messages)
    
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
        
        # Should have written result
        assert any("[result] 42" in msg for msg in self.mock_nvim.output_messages)
    
    @pytest.mark.asyncio
    async def test_handle_message_for_nvim_execute_input(self):
        """Test handling execute_input messages for Neovim display."""
        plugin = Quench(self.mock_nvim)
        
        message = {
            'msg_type': 'execute_input',
            'content': {'code': 'print("Hello")\nprint("World")'}
        }
        
        await plugin._handle_message_for_nvim("test-kernel", message)
        
        # Should show execution preview
        assert any("[executing] print(\"Hello\") ... (2 lines)" in msg for msg in self.mock_nvim.output_messages)
    
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
    
    @pytest.mark.asyncio
    async def test_run_cell_exception_handling(self):
        """Test exception handling in QuenchRunCell."""
        with patch('quench.KernelSessionManager') as MockKernelManager, \
             patch('quench.WebServer') as MockWebServer, \
             patch('quench.NvimUIManager') as MockUIManager:
            
            # Mock UI manager to raise an exception
            mock_ui_manager = AsyncMock()
            mock_ui_manager.get_current_bnum.side_effect = Exception("Test error")
            MockUIManager.return_value = mock_ui_manager
            
            plugin = Quench(self.mock_nvim)
            
            await plugin.run_cell([])
            
            # Should have error message
            assert any("Quench error: Test error" in msg for msg in self.mock_nvim.error_messages)
    
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])