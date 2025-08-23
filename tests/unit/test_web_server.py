"""
Unit tests for WebServer class.
"""
import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

# Import the web server
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rplugin', 'python3'))

from quench.web_server import WebServer, DateTimeEncoder


class TestDateTimeEncoder:
    """Test cases for the DateTimeEncoder class."""
    
    def test_datetime_encoding(self):
        """Test that datetime objects are properly encoded."""
        dt = datetime(2023, 1, 15, 14, 30, 45)
        encoder = DateTimeEncoder()
        result = encoder.default(dt)
        assert result == "2023-01-15T14:30:45"
    
    def test_non_datetime_encoding(self):
        """Test that non-datetime objects use default encoding."""
        encoder = DateTimeEncoder()
        with pytest.raises(TypeError):
            encoder.default("not a datetime")
    
    def test_json_dumps_with_datetime(self):
        """Test json.dumps with DateTimeEncoder handles datetime."""
        data = {
            "timestamp": datetime(2023, 1, 15, 14, 30, 45),
            "message": "test"
        }
        result = json.dumps(data, cls=DateTimeEncoder)
        expected = '{"timestamp": "2023-01-15T14:30:45", "message": "test"}'
        assert result == expected


class TestWebServer:
    """Test cases for the WebServer class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_nvim = Mock()
        self.mock_kernel_manager = Mock()
        self.web_server = WebServer(
            host="127.0.0.1",
            port=8765,
            nvim=self.mock_nvim,
            kernel_manager=self.mock_kernel_manager
        )
    
    def test_web_server_init(self):
        """Test WebServer initialization."""
        assert self.web_server.host == "127.0.0.1"
        assert self.web_server.port == 8765
        assert self.web_server.nvim == self.mock_nvim
        assert self.web_server.kernel_manager == self.mock_kernel_manager
        assert self.web_server.app is None
        assert self.web_server.runner is None
        assert self.web_server.site is None
        assert self.web_server.active_connections == {}
    
    def test_web_server_init_defaults(self):
        """Test WebServer initialization with default parameters."""
        server = WebServer()
        assert server.host == "127.0.0.1"
        assert server.port == 8765
        assert server.nvim is None
        assert server.kernel_manager is None
    
    def test_get_frontend_path(self):
        """Test getting the frontend path."""
        path = self.web_server._get_frontend_path()
        assert path.endswith('frontend')
        assert Path(path).is_absolute()
    
    @pytest.mark.asyncio
    async def test_start_aiohttp_not_available(self):
        """Test starting server when aiohttp is not available."""
        with patch('quench.web_server.web', None):
            with pytest.raises(RuntimeError, match="aiohttp is not installed"):
                await self.web_server.start()
    
    @pytest.mark.asyncio
    async def test_start_success(self):
        """Test successful server startup."""
        with patch('quench.web_server.web') as mock_web:
            # Mock aiohttp components
            mock_app = Mock()
            mock_runner = AsyncMock()
            mock_site = AsyncMock()
            
            mock_web.Application.return_value = mock_app
            mock_web.AppRunner.return_value = mock_runner
            mock_web.TCPSite.return_value = mock_site
            
            await self.web_server.start()
            
            # Verify setup sequence
            assert self.web_server.app == mock_app
            assert self.web_server.runner == mock_runner
            assert self.web_server.site == mock_site
            
            # Verify routes were added
            assert mock_app.router.add_get.call_count == 3
            assert mock_app.router.add_static.call_count == 1
            
            # Verify runner and site setup
            mock_runner.setup.assert_called_once()
            mock_site.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_failure_cleanup(self):
        """Test that start() cleans up on failure."""
        with patch('quench.web_server.web') as mock_web:
            mock_app = Mock()
            mock_runner = AsyncMock()
            mock_runner.setup.side_effect = Exception("Setup failed")
            
            mock_web.Application.return_value = mock_app
            mock_web.AppRunner.return_value = mock_runner
            
            with patch.object(self.web_server, 'stop', new_callable=AsyncMock) as mock_stop:
                with pytest.raises(Exception, match="Setup failed"):
                    await self.web_server.start()
                
                # Verify cleanup was called
                mock_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_success(self):
        """Test successful server shutdown."""
        # Mock active connections
        mock_ws1 = AsyncMock()
        mock_ws1.closed = False
        mock_ws1.close = AsyncMock()
        
        mock_ws2 = AsyncMock()
        mock_ws2.closed = True
        
        self.web_server.active_connections = {
            "kernel1": {mock_ws1, mock_ws2}
        }
        
        # Mock server components
        mock_site = AsyncMock()
        mock_runner = AsyncMock()
        
        self.web_server.site = mock_site
        self.web_server.runner = mock_runner
        
        await self.web_server.stop()
        
        # Verify WebSocket connections were closed
        mock_ws1.close.assert_called_once()
        
        # Verify active connections cleared
        assert self.web_server.active_connections == {}
        
        # Verify site and runner cleanup
        mock_site.stop.assert_called_once()
        mock_runner.cleanup.assert_called_once()
        
        # Verify components reset
        assert self.web_server.site is None
        assert self.web_server.runner is None
        assert self.web_server.app is None
    
    @pytest.mark.asyncio
    async def test_stop_no_components(self):
        """Test stopping when no server components exist."""
        # Should not raise exception
        await self.web_server.stop()
    
    @pytest.mark.asyncio
    async def test_handle_index_with_existing_file(self):
        """Test handling index request with existing index.html."""
        mock_request = Mock()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as tmp_file:
            tmp_file.write("<html><body>Test Content</body></html>")
            tmp_file_path = tmp_file.name
        
        try:
            with patch.object(self.web_server, '_get_frontend_path') as mock_path:
                mock_path.return_value = str(Path(tmp_file_path).parent)
                
                with patch('quench.web_server.web') as mock_web:
                    mock_response = Mock()
                    mock_web.Response.return_value = mock_response
                    
                    # Rename temp file to index.html for the test
                    index_path = Path(tmp_file_path).parent / 'index.html'
                    Path(tmp_file_path).rename(index_path)
                    
                    result = await self.web_server._handle_index(mock_request)
                    
                    # Verify Response was called with correct parameters
                    mock_web.Response.assert_called_once()
                    call_args = mock_web.Response.call_args
                    assert call_args[1]['content_type'] == 'text/html'
                    assert 'Test Content' in call_args[1]['text']
                    
                    # Clean up
                    index_path.unlink()
        except FileNotFoundError:
            pass  # File already cleaned up
    
    @pytest.mark.asyncio
    async def test_handle_index_no_file_default_content(self):
        """Test handling index request with no index.html file."""
        mock_request = Mock()
        
        with patch.object(self.web_server, '_get_frontend_path') as mock_path:
            mock_path.return_value = "/nonexistent/path"
            
            with patch('quench.web_server.web') as mock_web:
                mock_response = Mock()
                mock_web.Response.return_value = mock_response
                
                result = await self.web_server._handle_index(mock_request)
                
                # Verify default HTML content was served
                mock_web.Response.assert_called_once()
                call_args = mock_web.Response.call_args
                assert call_args[1]['content_type'] == 'text/html'
                assert 'Quench' in call_args[1]['text']
                assert 'Neovim IPython Integration' in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_handle_index_error(self):
        """Test handling index request when an error occurs."""
        mock_request = Mock()
        
        with patch.object(self.web_server, '_get_frontend_path', side_effect=Exception("Path error")):
            with patch('quench.web_server.web') as mock_web:
                mock_response = Mock()
                mock_web.Response.return_value = mock_response
                
                result = await self.web_server._handle_index(mock_request)
                
                # Verify error response
                mock_web.Response.assert_called_once_with(text="Internal Server Error", status=500)
    
    @pytest.mark.asyncio
    async def test_handle_sessions_api_success(self):
        """Test successful sessions API request."""
        mock_request = Mock()
        
        # Mock kernel manager sessions
        self.mock_kernel_manager.list_sessions.return_value = [
            {"kernel_id": "kernel1", "buffer_name": "test1.py"},
            {"kernel_id": "kernel2", "buffer_name": "test2.py"}
        ]
        
        with patch('quench.web_server.web') as mock_web:
            mock_response = Mock()
            mock_web.json_response.return_value = mock_response
            
            result = await self.web_server._handle_sessions_api(mock_request)
            
            # Verify response
            mock_web.json_response.assert_called_once()
            call_args = mock_web.json_response.call_args[0][0]
            assert call_args["count"] == 2
            assert len(call_args["sessions"]) == 2
    
    @pytest.mark.asyncio
    async def test_handle_sessions_api_no_kernel_manager(self):
        """Test sessions API request when no kernel manager is available."""
        mock_request = Mock()
        self.web_server.kernel_manager = None
        
        with patch('quench.web_server.web') as mock_web:
            mock_response = Mock()
            mock_web.json_response.return_value = mock_response
            
            result = await self.web_server._handle_sessions_api(mock_request)
            
            # Verify error response
            mock_web.json_response.assert_called_once()
            call_args = mock_web.json_response.call_args
            assert call_args[0][0]["error"] == "No kernel manager available"
            assert call_args[1]["status"] == 500
    
    @pytest.mark.asyncio
    async def test_handle_sessions_api_error(self):
        """Test sessions API request when an error occurs."""
        mock_request = Mock()
        
        self.mock_kernel_manager.list_sessions.side_effect = Exception("List sessions failed")
        
        with patch('quench.web_server.web') as mock_web:
            mock_response = Mock()
            mock_web.json_response.return_value = mock_response
            
            result = await self.web_server._handle_sessions_api(mock_request)
            
            # Verify error response
            mock_web.json_response.assert_called_once()
            call_args = mock_web.json_response.call_args
            assert "List sessions failed" in call_args[0][0]["error"]
            assert call_args[1]["status"] == 500
    
    @pytest.mark.asyncio
    async def test_handle_websocket_missing_kernel_id(self):
        """Test WebSocket handler with missing kernel_id."""
        mock_request = Mock()
        mock_request.match_info.get.return_value = None
        
        with patch('quench.web_server.web') as mock_web:
            mock_response = Mock()
            mock_web.Response.return_value = mock_response
            
            result = await self.web_server._handle_websocket(mock_request)
            
            # Verify error response
            mock_web.Response.assert_called_once_with(text="Missing kernel_id", status=400)
    
    @pytest.mark.asyncio
    async def test_handle_websocket_no_kernel_manager(self):
        """Test WebSocket handler with no kernel manager."""
        mock_request = Mock()
        mock_request.match_info.get.return_value = "kernel123"
        
        self.web_server.kernel_manager = None
        
        with patch('quench.web_server.web') as mock_web:
            mock_response = Mock()
            mock_web.Response.return_value = mock_response
            
            result = await self.web_server._handle_websocket(mock_request)
            
            # Verify error response
            mock_web.Response.assert_called_once_with(text="Kernel manager not available", status=500)
    
    @pytest.mark.asyncio
    async def test_handle_websocket_kernel_not_found(self):
        """Test WebSocket handler when kernel session is not found."""
        mock_request = Mock()
        mock_request.match_info.get.return_value = "nonexistent_kernel"
        
        # Mock kernel manager with no matching sessions
        self.mock_kernel_manager.sessions = {}
        
        with patch('quench.web_server.web') as mock_web:
            mock_response = Mock()
            mock_web.Response.return_value = mock_response
            
            result = await self.web_server._handle_websocket(mock_request)
            
            # Verify error response
            mock_web.Response.assert_called_once()
            call_args = mock_web.Response.call_args
            assert "not found" in call_args[1]["text"]
            assert call_args[1]["status"] == 404
    
    @pytest.mark.asyncio
    async def test_handle_websocket_success(self):
        """Test successful WebSocket connection."""
        mock_request = Mock()
        mock_request.match_info.get.return_value = "kernel123"
        
        # Mock kernel session
        mock_session = Mock()
        mock_session.output_cache = [
            {"msg_type": "stream", "content": {"text": "Hello"}},
            {"msg_type": "execute_result", "content": {"data": {"text/plain": "42"}}}
        ]
        
        self.mock_kernel_manager.sessions = {"kernel123": mock_session}
        
        with patch('quench.web_server.web') as mock_web, \
             patch('quench.web_server.WSMsgType') as mock_msg_type:
            
            # Mock WebSocket
            mock_ws = AsyncMock()
            mock_web.WebSocketResponse.return_value = mock_ws
            
            # Mock message iteration (empty - immediate close)
            mock_ws.__aiter__.return_value = []
            
            result = await self.web_server._handle_websocket(mock_request)
            
            # Verify WebSocket setup
            mock_ws.prepare.assert_called_once_with(mock_request)
            
            # Verify cached messages were sent
            assert mock_ws.send_str.call_count == 2
            
            # Verify connection was cleaned up after disconnection
            # Since the async iterator is empty, the connection gets added and then removed
            assert "kernel123" not in self.web_server.active_connections
    
    @pytest.mark.asyncio
    async def test_broadcast_message_no_connections(self):
        """Test broadcasting when no connections exist for kernel."""
        # Should not raise exception
        await self.web_server.broadcast_message("nonexistent_kernel", {"msg": "test"})
    
    @pytest.mark.asyncio
    async def test_broadcast_message_success(self):
        """Test successful message broadcasting."""
        # Mock WebSocket connections
        mock_ws1 = AsyncMock()
        mock_ws1.closed = False
        mock_ws1.send_str = AsyncMock()
        
        mock_ws2 = AsyncMock()
        mock_ws2.closed = False
        mock_ws2.send_str = AsyncMock()
        
        self.web_server.active_connections = {
            "kernel123": {mock_ws1, mock_ws2}
        }
        
        test_message = {"msg_type": "stream", "content": {"text": "broadcast test"}}
        
        await self.web_server.broadcast_message("kernel123", test_message)
        
        # Verify message was sent to both connections
        mock_ws1.send_str.assert_called_once()
        mock_ws2.send_str.assert_called_once()
        
        # Verify JSON encoding was used
        sent_data1 = mock_ws1.send_str.call_args[0][0]
        sent_data2 = mock_ws2.send_str.call_args[0][0]
        
        assert json.loads(sent_data1) == test_message
        assert json.loads(sent_data2) == test_message
    
    @pytest.mark.asyncio
    async def test_broadcast_message_closed_connection_removal(self):
        """Test that closed connections are removed during broadcast."""
        # Mock WebSocket - one open, one closed
        mock_ws_open = AsyncMock()
        mock_ws_open.closed = False
        mock_ws_open.send_str = AsyncMock()
        
        mock_ws_closed = AsyncMock()
        mock_ws_closed.closed = True
        
        self.web_server.active_connections = {
            "kernel123": {mock_ws_open, mock_ws_closed}
        }
        
        test_message = {"msg": "test"}
        
        await self.web_server.broadcast_message("kernel123", test_message)
        
        # Verify closed connection was removed
        assert mock_ws_closed not in self.web_server.active_connections["kernel123"]
        assert mock_ws_open in self.web_server.active_connections["kernel123"]
        
        # Verify message was sent only to open connection
        mock_ws_open.send_str.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_broadcast_message_error_handling(self):
        """Test broadcasting with connection that raises an error."""
        # Mock WebSocket that raises exception
        mock_ws_error = AsyncMock()
        mock_ws_error.closed = False
        mock_ws_error.send_str = AsyncMock(side_effect=Exception("Connection error"))
        mock_ws_error.close = AsyncMock()
        
        self.web_server.active_connections = {
            "kernel123": {mock_ws_error}
        }
        
        test_message = {"msg": "test"}
        
        await self.web_server.broadcast_message("kernel123", test_message)
        
        # Verify problematic connection was removed
        assert mock_ws_error not in self.web_server.active_connections.get("kernel123", set())
        
        # Verify connection was attempted to be closed
        mock_ws_error.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_broadcast_message_empty_connections_cleanup(self):
        """Test that empty connection sets are cleaned up."""
        mock_ws = AsyncMock()
        mock_ws.closed = True
        
        self.web_server.active_connections = {
            "kernel123": {mock_ws}
        }
        
        await self.web_server.broadcast_message("kernel123", {"msg": "test"})
        
        # Verify empty kernel connection set was removed
        assert "kernel123" not in self.web_server.active_connections
    
    def test_get_connection_count(self):
        """Test getting connection count for a kernel."""
        mock_ws1 = Mock()
        mock_ws2 = Mock()
        
        self.web_server.active_connections = {
            "kernel123": {mock_ws1, mock_ws2},
            "kernel456": {mock_ws1}
        }
        
        # Test existing kernel
        assert self.web_server.get_connection_count("kernel123") == 2
        assert self.web_server.get_connection_count("kernel456") == 1
        
        # Test nonexistent kernel
        assert self.web_server.get_connection_count("nonexistent") == 0
    
    def test_get_all_connection_counts(self):
        """Test getting connection counts for all kernels."""
        mock_ws1 = Mock()
        mock_ws2 = Mock()
        mock_ws3 = Mock()
        
        self.web_server.active_connections = {
            "kernel123": {mock_ws1, mock_ws2},
            "kernel456": {mock_ws3},
            "kernel789": set()  # Empty set
        }
        
        result = self.web_server.get_all_connection_counts()
        
        expected = {
            "kernel123": 2,
            "kernel456": 1,
            "kernel789": 0
        }
        
        assert result == expected
    
    def test_get_all_connection_counts_empty(self):
        """Test getting connection counts when no connections exist."""
        assert self.web_server.get_all_connection_counts() == {}


if __name__ == '__main__':
    pytest.main([__file__])