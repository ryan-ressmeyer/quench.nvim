# quench.nvim

Quench is a Neovim plugin for interactive Python development that enables cell-based execution similar to VS Code's Jupyter extension. The plugin manages IPython kernels and routes output to both terminal and web browser for rich media display.

## Features

- ✅ **Cell-based execution** using `#%%` delimiters in Python files
- ✅ **Rich media output** via web browser (plots, HTML, LaTeX, images)
- ✅ **Text output** in Neovim for immediate feedback
- ✅ **IPython kernel management** with automatic lifecycle handling
- ✅ **WebSocket communication** for real-time output streaming
- ✅ **Multiple buffer support** with independent kernel sessions
- ✅ **Comprehensive error handling** with graceful degradation

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install pynvim jupyter-client aiohttp websockets
   ```

2. **Install plugin** using your preferred plugin manager

3. **Update remote plugins:**
   ```vim
   :UpdateRemotePlugins
   ```

4. **Try the example:**
   ```bash
   nvim example/quick-start.py
   # Execute cells with :call QuenchRunCell()
   # Open browser at displayed URL for rich output
   ```

## Project Structure

This section describes the complete architecture and file specifications of the Quench plugin.

# Quench: A Detailed Plugin Specification

1. Core Philosophy & Architecture

**Philosophy**: Quench enables an interactive Python workflow within Neovim, inspired by the cell-based execution found in tools like VS Code's Jupyter extension. Its primary goal is to solve the challenge of handling rich media output in a terminal environment.

The plugin allows users to define and execute code cells (demarcated by #%%) within standard .py files. Rather than attempting to render complex output like plots or audio directly in the terminal, Quench launches a local web server and relays all output from the managed IPython kernel to a web browser via WebSockets. This architecture ensures that all media is rendered correctly and fully, providing a robust solution for data science and visualization tasks.

The plugin prioritizes stability, resource safety, and a non-blocking user interface by leveraging modern asynchronous Python (asyncio) for all background processes and communication.

**Core Architecture:** The plugin is an asyncio-based Python application managed by pynvim. It consists of three main, long-running components that are managed by a central Quench class:

Kernel Session Manager (KernelSessionManager): A singleton that manages the lifecycle of all active IPython kernels.

Web Server (WebServer): A singleton aiohttp application that serves the frontend and relays kernel output via WebSockets.

Neovim UI Manager (NvimUIManager): Handles all interactions with the Neovim API, such as creating buffers, setting text, and handling user commands.

These components communicate asynchronously using a central asyncio.Queue for safe, decoupled message passing.

2. Kernel Session Management (kernel_session.py)
This is the heart of the plugin, responsible for all kernel-related tasks.

KernelSession Class:
Represents a single, running IPython kernel and its associated state.

Attributes:

kernel_id (str): A unique identifier (e.g., a UUID).

km (jupyter_client.asynciomanager.AsyncKernelManager): The Jupyter manager for the kernel subprocess.

client (jupyter_client.AsyncKernelClient): The client for communicating with the kernel.

output_cache (list): A list of all raw IOPub messages received from this kernel.

relay_queue (asyncio.Queue): A reference to the central queue for broadcasting messages.

associated_buffers (set): A set of Neovim buffer numbers (bnum) attached to this session.

listener_task (asyncio.Task): The task that continuously listens to the kernel's IOPub channel.

Methods:

async def start(self):

Starts the kernel using self.km.start_kernel().

Creates the client: self.client = self.km.client().

Starts the client's channels: self.client.start_channels().

Waits for the client to be fully ready using await self.client.wait_for_ready().

Creates and starts the _listen_iopub task.

async def shutdown(self):

Safely cancels the listener_task.

Stops the client channels.

Shuts down the kernel gracefully using await self.km.shutdown_kernel().

async def execute(self, code: str):

Sends code to the kernel's shell channel via self.client.execute(code).

async def _listen_iopub(self):

Wraps the main loop in a try...finally block to ensure cleanup.

Enters an infinite while True loop.

Awaits messages from self.client.get_iopub_msg().

Appends the raw message to self.output_cache.

Puts a tuple (self.kernel_id, message) onto the central self.relay_queue.

Error Handling: Catches asyncio.CancelledError to exit gracefully. Catches other potential exceptions (e.g., from a dead kernel) and logs an error message.

KernelSessionManager Class:
A singleton that manages all active KernelSession instances.

Attributes:

sessions (dict): A dictionary mapping kernel_id to KernelSession objects.

buffer_to_kernel_map (dict): A mapping of bnum to kernel_id.

Methods:

async def get_or_create_session(self, bnum: int, relay_queue: asyncio.Queue) -> KernelSession:

Checks buffer_to_kernel_map for an existing session for the buffer.

If it exists, return the session from self.sessions.

If not, create a new KernelSession, passing it the relay_queue. Start it, and store it.

Map the bnum to the new kernel_id.

Return the new session.

async def attach_buffer_to_session(self, bnum: int, kernel_id: str):

Finds the session by kernel_id.

Adds bnum to the session's associated_buffers.

Updates the buffer_to_kernel_map.

async def get_session_for_buffer(self, bnum: int) -> KernelSession | None:

Looks up and returns the session associated with the buffer.

async def shutdown_all_sessions(self):

Iterates through all sessions and calls their shutdown() method concurrently using asyncio.gather.

3. Web Server & WebSocket Relay (web_server.py)
This component is responsible for the rich media output.

WebServer Class:

Attributes:

host (str): e.g., "127.0.0.1".

port (int): e.g., 8765.

app (aiohttp.web.Application): The main web application instance.

active_connections (dict): Maps kernel_id to a set of aiohttp.web.WebSocketResponse objects.

kernel_manager (KernelSessionManager): A reference to the kernel manager.

Methods:

async def start(self):

Initializes the aiohttp.web.Application.

Adds routes: / for index.html and /ws/{kernel_id} for the WebSocket endpoint.

Creates and starts the aiohttp.web.AppRunner and TCPSite.

async def stop(self):

Cleans up and stops the AppRunner.

async def _handle_websocket(self, request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:

Extracts kernel_id from the request URL.

Finds the corresponding KernelSession. If not found, return an error.

Prepares a new WebSocket response.

Send Cache: Immediately sends all messages from the session's output_cache to the new client.

Adds the new connection to self.active_connections[kernel_id].

Enters a loop to handle potential incoming messages and to detect client disconnection.

On disconnect, remove the client from active_connections.

async def broadcast_message(self, kernel_id: str, message: dict):

Iterates through a copy of all WebSocket clients connected to the given kernel_id.

Error Handling: Wraps the ws.send_json(message) call in a try...except block to gracefully handle clients that have disconnected without being properly removed.

Sends the JSON-serialized message to each client.

4. Frontend Client (frontend/)
A simple, single-page web application.

index.html:

Basic HTML structure.

A container div (e.g., <div id="output-area"></div>).

Includes the JavaScript file.

main.js:

WebSocket Connection:

Extracts the kernel_id from the URL.

Establishes a WebSocket connection to ws://127.0.0.1:8765/ws/{kernel_id}.

Message Handling:

Sets the ws.onmessage handler.

Parses the incoming JSON event data.

Rendering Logic:

This logic will correlate inputs with outputs using the message headers.

When an execute_input message arrives, create a new "cell" container div with a unique ID based on the message's header.msg_id. Render the code inside a "code input" div.

When any other message arrives (stream, display_data, execute_result, error), find the cell container div whose ID matches the message's parent_header.msg_id.

Render the output content inside that cell's "output" div using a library like render-mime or a custom function.

This ensures that the code appears instantly, and its corresponding output appears underneath it when ready.

5. Neovim Integration (__init__.py)
This is the main plugin file that ties everything together.

NvimUIManager Class (ui_manager.py):

A class that wraps all Neovim API calls.

__init__(self, nvim)

async def get_current_bnum(self)

async def get_cell_code(self, bnum, lnum): Implements the #%% finding logic.

async def create_output_buffer(self)

async def write_to_buffer(self, bnum, lines)

async def get_user_choice(self, items): Uses nvim.input to present a list.

Quench Class (@pynvim.plugin):

Attributes:

nvim (pynvim.Nvim): The Neovim API object.

kernel_manager (KernelSessionManager)

web_server (WebServer)

ui_manager (NvimUIManager)

relay_queue (asyncio.Queue): The central message queue.

message_relay_task (asyncio.Task)

__init__(self, nvim):

Initializes nvim and all manager singletons.

Instantiates the central relay_queue.

@pynvim.autocmd("VimLeave", sync=True):

Calls a separate async def _cleanup() method via asyncio.run().

_cleanup will shut down the web server and all kernel sessions.

@pynvim.function("QuenchRunCell", sync=False):

Uses ui_manager to get the current buffer and line number.

Uses ui_manager to find and get the code for the current cell.

Gets the session: session = await self.kernel_manager.get_or_create_session(bnum, self.relay_queue).

If the message_relay_task is not running, start it.

Executes the code: await session.execute(code).

Helper Methods:

async def _message_relay_loop(self):

Continuously gets messages (kernel_id, message) from the central self.relay_queue.

Forwards messages to self.web_server.broadcast_message(kernel_id, message).

Forwards text-based messages to self.ui_manager to be written to the Neovim output buffer.

6. Testing Strategy
Unit Tests (pytest):

Test the ui_manager.get_cell_code logic with various edge cases.

Test the KernelSessionManager's logic for creating and mapping sessions without actually starting processes (using mocks).

Integration Tests (pytest with pynvim):

Write tests that embed a Neovim instance (nvim --embed).

Start the full plugin.

Programmatically send commands (nvim.command("QuenchRunCell")).

Assert the contents of the Neovim output buffer.

Use a separate Python script with a WebSocket client to connect to the test server and assert that it receives both the execute_input and execute_result messages in the correct order.

---

## File Structure & Specifications

### Core Plugin Files

#### `rplugin/python3/quench/__init__.py`
**Main plugin class and pynvim integration**

- **Purpose**: Central coordinator that integrates all components
- **Key Components**:
  - `Quench` class decorated with `@pynvim.plugin`
  - Manages KernelSessionManager, WebServer, and NvimUIManager instances
  - Handles pynvim commands and functions
  - Central message relay queue for async communication
- **Commands Provided**:
  - `QuenchRunCell()` - Execute current Python cell (async)
  - `QuenchStatus` - Display plugin status and active sessions
  - `QuenchStop` - Stop all plugin components
  - `HelloWorld` - Basic connectivity test
- **Architecture**: Asyncio-based with proper resource cleanup and error handling

#### `rplugin/python3/quench/kernel_session.py`
**IPython kernel lifecycle management**

- **Purpose**: Manages IPython kernel processes and communication
- **Key Classes**:
  - `KernelSession`: Individual kernel wrapper with async communication
  - `KernelSessionManager`: Singleton managing all kernel sessions
- **Features**:
  - Automatic kernel startup using `jupyter_client.AsyncKernelManager`
  - IOPub message listening and caching
  - Buffer-to-kernel mapping for multi-file support
  - Graceful shutdown with resource cleanup
- **Dependencies**: `jupyter_client`, `asyncio`, `uuid`

#### `rplugin/python3/quench/web_server.py`
**HTTP server and WebSocket relay**

- **Purpose**: Serves frontend and relays kernel output to browsers
- **Key Features**:
  - aiohttp-based async web server (default: `127.0.0.1:8765`)
  - WebSocket endpoints at `/ws/{kernel_id}`
  - Static file serving for frontend assets
  - Real-time message broadcasting to connected clients
  - Connection management with automatic cleanup
- **Routes**:
  - `GET /` - Serve index.html
  - `GET /ws/{kernel_id}` - WebSocket connection
  - `GET /static/*` - Frontend assets
- **Dependencies**: `aiohttp`, graceful fallback if not available

#### `rplugin/python3/quench/ui_manager.py`
**Neovim API interaction layer**

- **Purpose**: Wraps all Neovim API calls for the plugin
- **Key Functions**:
  - `get_cell_code()` - Parse `#%%` delimited cells from buffers
  - `get_current_bnum()` - Get active buffer number
  - `create_output_buffer()` / `write_to_buffer()` - Buffer management
  - `get_user_choice()` - Interactive user input
- **Cell Parsing Logic**:
  - Searches backward/forward for `#%%` delimiters
  - Handles edge cases (cursor on delimiter, empty cells)
  - Strips empty lines from cell boundaries
- **Dependencies**: `pynvim`, `asyncio`

### Frontend Files

#### `rplugin/python3/quench/frontend/index.html`
**Browser interface layout**

- **Purpose**: Single-page web application for rich output display
- **Features**:
  - Dark theme matching modern code editors
  - Header with kernel information and connection status
  - Main output area for cell execution results
  - Responsive design with proper typography
- **Structure**: Semantic HTML5 with embedded CSS styling

#### `rplugin/python3/quench/frontend/main.js`
**Client-side JavaScript application**

- **Purpose**: Manages WebSocket communication and output rendering
- **Key Features**:
  - Automatic kernel ID extraction from URL parameters
  - WebSocket connection with auto-reconnect
  - Cell-based output organization using message correlation
  - MIME type rendering (HTML, images, LaTeX, JSON, plain text)
  - Real-time message processing and display
- **Architecture**: ES6 class-based with proper error handling

### Test Suite

#### `tests/test_unit.py`
**Unit tests for individual components**

- **Coverage**: 19 tests for NvimUIManager functionality
- **Focus Areas**:
  - Cell code extraction with various file layouts
  - Buffer operations and edge cases
  - User interaction functions
  - Error handling scenarios
- **Test Strategy**: Mock-based isolation testing

#### `tests/test_quench_main.py`
**Integration tests for main plugin class**

- **Coverage**: 18 tests for complete plugin functionality
- **Focus Areas**:
  - Plugin initialization and component setup
  - QuenchRunCell execution flow
  - Message relay loop functionality
  - Resource cleanup and lifecycle management
- **Test Strategy**: Comprehensive mocking with async test support

#### `tests/test_integration.py`
**End-to-end integration tests**

- **Coverage**: Integration scenarios with real components
- **Focus Areas**:
  - Embedded Neovim instance testing
  - WebSocket client/server communication
  - Component interaction validation
  - Dependency handling and graceful degradation
- **Test Strategy**: Real component testing where possible

#### `tests/conftest.py`
**Pytest configuration and shared fixtures**

- **Features**:
  - Automatic dependency detection and test skipping
  - Shared fixtures for test setup
  - Custom pytest markers for test categorization
  - Test report headers with dependency information

### Documentation & Examples

#### `example/README.md`
**User getting started guide**

- **Content**: Complete tutorial for new users
- **Sections**: Prerequisites, step-by-step usage, troubleshooting
- **Focus**: Practical workflow examples and configuration

#### `example/example-usage.py`
**Comprehensive functionality demonstration**

- **Structure**: 11 cells showcasing all plugin features
- **Coverage**: Basic execution, rich media, error handling, best practices
- **Purpose**: Complete learning experience for new users

#### `example/quick-start.py`
**Simple functionality validation**

- **Purpose**: Quick plugin test and validation
- **Structure**: 4 cells with basic functionality tests
- **Usage**: Immediate verification of plugin installation

#### `example/nvim-config-example.lua`
**Complete Neovim configuration template**

- **Content**: Production-ready configuration example
- **Features**: Key mappings, autocommands, statusline integration
- **Advanced**: Telescope integration, Which-key support, cell highlighting

### Configuration Files

#### `CLAUDE.md`
**Development context for AI assistance**

- **Purpose**: Provides development context and architecture overview
- **Content**: Project structure, development commands, architectural patterns
- **Usage**: Guides future development and AI-assisted modifications

#### `requirements-test.txt`
**Test dependencies specification**

- **Content**: Comprehensive test dependency list with versions
- **Structure**: Core dependencies, optional dependencies, development tools
- **Purpose**: Reproducible test environment setup

## Dependencies

### Required Dependencies
- `pynvim` - Neovim Python integration
- `jupyter_client` - IPython kernel management

### Optional Dependencies  
- `aiohttp` - Web server functionality (graceful fallback)
- `websockets` - Enhanced WebSocket support
- `matplotlib` - Rich plotting output
- `pandas` - Data analysis and tabular display
- `IPython` - Enhanced rich output support

### Development Dependencies
- `pytest` - Test framework
- `pytest-asyncio` - Async test support  
- `pytest-mock` - Advanced mocking capabilities

## Testing Status

✅ **43 tests passing** with comprehensive coverage:
- 19 unit tests for UI manager
- 18 integration tests for main plugin
- 6 integration tests for component interaction
- Full async functionality validation
- WebSocket communication testing
- Error handling and edge case coverage

The plugin is production-ready with robust testing and comprehensive documentation.
