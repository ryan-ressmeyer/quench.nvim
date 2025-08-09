import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Dict, Set, Optional
from pathlib import Path

try:
    from aiohttp import web, WSMsgType
    from aiohttp.web_ws import WebSocketResponse
except ImportError:
    # Graceful fallback if aiohttp is not installed
    web = None
    WSMsgType = None
    WebSocketResponse = None


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class WebServer:
    """
    Web server component responsible for serving the frontend and handling WebSocket connections
    for relaying kernel output to browsers.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, nvim=None, kernel_manager=None):
        """
        Initialize the web server.

        Args:
            host: Host address to bind the server to
            port: Port number to bind the server to
            nvim: Neovim instance reference (for potential future use)
            kernel_manager: KernelSessionManager instance for accessing kernel sessions
        """
        self.host = host
        self.port = port
        self.nvim = nvim
        self.kernel_manager = kernel_manager
        self.app = None
        self.runner = None
        self.site = None
        self.active_connections: Dict[str, Set] = {}
        self._logger = logging.getLogger("quench.web_server")

    async def start(self):
        """
        Start the aiohttp web server.
        """
        if web is None:
            raise RuntimeError("aiohttp is not installed. Please install it to use the web server functionality.")

        try:
            # Initialize the aiohttp application
            self.app = web.Application()
            
            # Add routes
            self.app.router.add_get('/', self._handle_index)
            self.app.router.add_get('/api/sessions', self._handle_sessions_api)
            self.app.router.add_get('/ws/{kernel_id}', self._handle_websocket)
            self.app.router.add_static('/static/', path=self._get_frontend_path(), name='static')

            # Create and start the app runner
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            # Create and start the TCP site
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()

            self._logger.info(f"Web server started on http://{self.host}:{self.port}")

        except Exception as e:
            self._logger.error(f"Failed to start web server: {e}")
            await self.stop()
            raise

    async def stop(self):
        """
        Stop the web server and clean up resources.
        """
        self._logger.info("Stopping web server")

        # Close all active WebSocket connections
        for kernel_id, connections in self.active_connections.items():
            for ws in list(connections):
                if not ws.closed:
                    await ws.close()

        self.active_connections.clear()

        # Stop the site
        if self.site:
            await self.site.stop()
            self.site = None

        # Clean up the runner
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

        self.app = None
        self._logger.info("Web server stopped")

    def _get_frontend_path(self) -> str:
        """
        Get the path to the frontend directory.
        
        Returns:
            str: Path to the frontend directory
        """
        current_dir = Path(__file__).parent
        frontend_path = current_dir / 'frontend'
        return str(frontend_path)

    async def _handle_index(self, request):
        """
        Handle requests to the root path by serving the index.html file.
        
        Args:
            request: The aiohttp request object
            
        Returns:
            web.Response: The response containing the index.html content
        """
        try:
            frontend_path = Path(self._get_frontend_path())
            index_path = frontend_path / 'index.html'
            
            if index_path.exists():
                with open(index_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return web.Response(text=content, content_type='text/html')
            else:
                # Return a simple default page if index.html doesn't exist
                default_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Quench - Neovim IPython Integration</title>
                </head>
                <body>
                    <h1>Quench</h1>
                    <p>Neovim IPython Integration Server</p>
                    <p>WebSocket endpoint: <code>/ws/{kernel_id}</code></p>
                </body>
                </html>
                """
                return web.Response(text=default_html, content_type='text/html')
                
        except Exception as e:
            self._logger.error(f"Error serving index page: {e}")
            return web.Response(text="Internal Server Error", status=500)

    async def _handle_sessions_api(self, request):
        """
        Handle API requests for listing available kernel sessions.
        
        Returns:
            web.Response: JSON response with session information
        """
        try:
            if not self.kernel_manager:
                return web.json_response({"error": "No kernel manager available"}, status=500)
            
            sessions = self.kernel_manager.list_sessions()
            return web.json_response({
                "sessions": sessions,
                "count": len(sessions)
            })
            
        except Exception as e:
            self._logger.error(f"Error in sessions API: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_websocket(self, request):
        """
        Handle WebSocket connections for relaying kernel output.
        
        This method:
        1. Extracts kernel_id from the URL
        2. Finds the corresponding KernelSession
        3. Sends the entire output_cache to the new client
        4. Adds the client to active_connections
        5. Handles client disconnection gracefully
        
        Args:
            request: The aiohttp request object containing the WebSocket upgrade
            
        Returns:
            WebSocketResponse: The WebSocket response object
        """
        # Extract kernel_id from the URL
        kernel_id = request.match_info.get('kernel_id')
        if not kernel_id:
            self._logger.warning("WebSocket connection attempted without kernel_id")
            return web.Response(text="Missing kernel_id", status=400)

        # Find the corresponding KernelSession
        if not self.kernel_manager:
            self._logger.error("No kernel manager available")
            return web.Response(text="Kernel manager not available", status=500)

        # Look for the session by kernel_id
        session = None
        available_sessions = list(self.kernel_manager.sessions.keys())
        self._logger.debug(f"Looking for kernel_id '{kernel_id}', available sessions: {available_sessions}")
        
        for session_id, kernel_session in self.kernel_manager.sessions.items():
            if session_id == kernel_id:
                session = kernel_session
                break

        if not session:
            self._logger.warning(f"No kernel session found for kernel_id: {kernel_id} (available: {available_sessions})")
            return web.Response(text=f"Kernel session {kernel_id} not found", status=404)

        # Prepare the WebSocket response
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        try:
            self._logger.info(f"WebSocket client connected to kernel {kernel_id[:8]}")

            # Send the entire output_cache to the new client
            for message in session.output_cache:
                try:
                    await ws.send_str(json.dumps(message, cls=DateTimeEncoder))
                except Exception as e:
                    self._logger.warning(f"Failed to send cached message to client: {e}")
                    break

            # Add the new connection to active_connections
            if kernel_id not in self.active_connections:
                self.active_connections[kernel_id] = set()
            self.active_connections[kernel_id].add(ws)

            # Handle incoming messages and detect disconnection
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # Handle potential incoming messages from client
                    try:
                        data = json.loads(msg.data)
                        self._logger.debug(f"Received message from WebSocket client: {data}")
                        # For now, we just log incoming messages
                        # Future implementation could handle client commands
                    except json.JSONDecodeError:
                        self._logger.warning(f"Invalid JSON received from WebSocket client: {msg.data}")
                        
                elif msg.type == WSMsgType.ERROR:
                    self._logger.error(f'WebSocket error: {ws.exception()}')
                    break
                elif msg.type == WSMsgType.CLOSE:
                    self._logger.info(f"WebSocket client disconnected from kernel {kernel_id[:8]}")
                    break

        except Exception as e:
            self._logger.error(f"Error in WebSocket handler for kernel {kernel_id[:8]}: {e}")
        finally:
            # Remove the connection from active_connections on disconnect
            if kernel_id in self.active_connections:
                self.active_connections[kernel_id].discard(ws)
                if not self.active_connections[kernel_id]:
                    # Remove empty sets to keep the dictionary clean
                    del self.active_connections[kernel_id]

            self._logger.info(f"WebSocket client disconnected from kernel {kernel_id[:8]}")

        return ws

    async def broadcast_message(self, kernel_id: str, message: dict):
        """
        Send a message to all WebSocket clients connected to a specific kernel.
        
        Args:
            kernel_id: The kernel ID to broadcast to
            message: The message dictionary to send
        """
        if kernel_id not in self.active_connections:
            return

        # Work with a copy of the connections set to avoid modification during iteration
        connections = self.active_connections[kernel_id].copy()
        
        for ws in connections:
            try:
                if ws.closed:
                    # Remove closed connections
                    self.active_connections[kernel_id].discard(ws)
                    continue
                    
                await ws.send_str(json.dumps(message, cls=DateTimeEncoder))
                self._logger.debug(f"Broadcasted message to WebSocket client for kernel {kernel_id[:8]}")
                
            except Exception as e:
                # Handle disconnected clients gracefully
                self._logger.warning(f"Failed to send message to WebSocket client for kernel {kernel_id[:8]}: {e}")
                # Remove the problematic connection
                self.active_connections[kernel_id].discard(ws)
                
                # Try to close the connection if it's not already closed
                if not ws.closed:
                    try:
                        await ws.close()
                    except Exception:
                        pass  # Ignore errors when closing

        # Clean up empty connection sets
        if kernel_id in self.active_connections and not self.active_connections[kernel_id]:
            del self.active_connections[kernel_id]

    def get_connection_count(self, kernel_id: str) -> int:
        """
        Get the number of active WebSocket connections for a kernel.
        
        Args:
            kernel_id: The kernel ID to check
            
        Returns:
            int: Number of active connections
        """
        return len(self.active_connections.get(kernel_id, set()))

    def get_all_connection_counts(self) -> Dict[str, int]:
        """
        Get connection counts for all kernels.
        
        Returns:
            Dict[str, int]: Mapping of kernel_id to connection count
        """
        return {kernel_id: len(connections) for kernel_id, connections in self.active_connections.items()}