# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Quench is a Neovim plugin for interactive Python development that enables cell-based execution similar to VS Code's Jupyter extension. The plugin manages IPython kernels and routes output to both terminal and web browser for rich media display.

**Key Architecture**: Asyncio-based Python application using pynvim, consisting of:
- **Kernel Session Manager**: Manages IPython kernel lifecycles
- **Web Server**: aiohttp server that relays kernel output via WebSockets  
- **Neovim UI Manager**: Handles Neovim API interactions

This is a fully implemented and production-ready plugin with comprehensive testing and complete functionality.

## Development Commands

### Testing
- `pytest tests/` - Run the full test suite
- `pytest tests/unit/` - Run unit tests only
- `pytest tests/e2e/` - Run end-to-end integration tests
- `pytest tests/unit/test_quench_plugin.py` - Run main plugin tests
- `pytest tests/e2e/test_quench_run_cell.py` - Run cell execution tests
- `pytest -v` - Run tests with verbose output
- `pytest -k "test_name"` - Run specific test by name
- The project uses pytest with async support and dependency detection

### Code Formatting
- `stylua --color always --check lua` - Check Lua code formatting
- `stylua lua` - Format Lua code (uses .stylua.toml configuration with 120 column width)
- `black rplugin/python3/quench/` - Format Python code
- `flake8 rplugin/python3/quench/` - Check Python code style

### Plugin Development
- Plugin files are in `rplugin/python3/quench/`
- Main plugin class is in `rplugin/python3/quench/__init__.py`
- Uses pynvim decorators: `@pynvim.plugin`, `@pynvim.command`, `@pynvim.function`
- The Python environment for testing is managed by uv: `/home/ryanress/code/ubuntu-config/nvim/pynvim-env/.venv/bin/python`

## Code Architecture

### Current State
- **FULLY IMPLEMENTED** - All core Quench functionality is complete and working
- Main plugin class in `rplugin/python3/quench/__init__.py` with async commands:
  - `QuenchRunCell` - Execute Python cells with `#%%` delimiters
  - `QuenchStatus` - Display plugin status and active sessions
  - `QuenchStop` - Stop all plugin components
- Complete kernel session management with IPython integration
- Web server with WebSocket relay for rich media output
- UI manager for Neovim API interactions
- Frontend HTML/JS application for browser-based output display

### Additional Commands Available

**Execution Commands:**
- `QuenchRunCellAdvance` - Execute cell and move cursor to next cell
- `QuenchRunSelection` - Execute selected text as Python code
- `QuenchRunLine` - Execute current line
- `QuenchRunAbove` - Execute all cells above current position
- `QuenchRunBelow` - Execute all cells below current position
- `QuenchRunAll` - Execute all cells in buffer

**Kernel Management Commands:**
- `QuenchInterruptKernel` - Send interrupt signal to the kernel (similar to Ctrl+C)
- `QuenchResetKernel` - Restart kernel and clear its state
- `QuenchStartKernel` - Start a new kernel not attached to any buffer
- `QuenchShutdownKernel` - Shutdown a running kernel
- `QuenchSelectKernel` - Select/attach kernel for current buffer
- `QuenchDebug` - Show diagnostic information for debugging

### Key Design Patterns
- Asyncio-based architecture for non-blocking operations
- Central message queue (asyncio.Queue) for component communication
- Cell-based execution using `#%%` delimiters in Python files
- Web browser integration for rich media (plots, audio, etc.)
- Automatic kernel death detection and recovery for robust execution

### Kernel Lifecycle Management

The plugin implements three distinct kernel restart/recovery mechanisms:

1. **Manual Restart** (`restart()` method in `kernel_session.py`)
   - Triggered by: User via `QuenchResetKernel` command
   - Behavior: Restarts the kernel process using `km.restart_kernel()`
   - Message sent: `kernel_restarted`
   - Output cache: Preserved (outputs remain visible)
   - Use case: User wants to clear kernel namespace while keeping outputs

2. **Death Detection** (`_monitor_process()` method in `kernel_session.py`)
   - Triggered by: Background monitoring loop (checks every 2 seconds)
   - Detection: Kernel process dies unexpectedly (OOM, crash, external SIGKILL)
   - Behavior: Sets `is_dead` flag, sends `kernel_died` message, cleans up resources
   - Message sent: `kernel_died`
   - Use case: Kernel crashes or is terminated by OS

3. **Auto-Restart on Execution** (`execute()` method in `kernel_session.py`)
   - Triggered by: Attempting to execute code when `is_dead == True`
   - Behavior: Automatically calls `start()` to restart kernel, clears `is_dead` flag, proceeds with execution
   - Message sent: `kernel_auto_restarted`
   - Output cache: Preserved (previous outputs remain visible)
   - Use case: Seamless recovery from kernel death without user intervention

**Complete Death-to-Recovery Flow:**
1. Kernel process dies (OOM, crash, SIGKILL)
2. Monitoring loop detects death within ~2 seconds
3. `is_dead` flag set to `True`, user notified
4. User runs next cell
5. Plugin automatically restarts kernel
6. Cell executes successfully on restarted kernel
7. Previous outputs remain visible in frontend

### Modular Architecture
The plugin is organized into distinct modules for maintainability:
- **commands/** - Command implementation functions separated from pynvim decorators
  - Enables easier testing and reuse of command logic
  - Separates execution commands from debug/management commands
- **core/** - Core utilities and shared functionality
  - Centralized async execution patterns
  - Reusable cell parsing utilities
  - Configuration management
- **utils/** - Shared utility functions
  - User notification helpers
  - Common helper functions

### Codebase Structure
```
Core Plugin:
rplugin/python3/quench/
├── __init__.py          # Main plugin class and pynvim integration
├── kernel_session.py    # IPython kernel management
├── web_server.py        # Web server and WebSocket handling
├── ui_manager.py        # Neovim API wrapper
├── commands/            # Command implementations
│   ├── execution.py     # Execution commands (RunCell, RunAll, etc.)
│   └── debug.py         # Debug and status commands
├── core/                # Core utilities
│   ├── async_executor.py  # Async execution patterns
│   ├── cell_parser.py     # Cell parsing utilities
│   └── config.py          # Configuration management
├── utils/               # Utility modules
│   └── notifications.py   # User notification utilities
└── frontend/            # Web frontend files
    ├── index.html       # Browser interface layout
    └── main.js          # WebSocket client and output rendering

Test Suite:
tests/
├── conftest.py          # Test configuration and fixtures
├── unit/                # Unit tests
│   ├── test_kernel_session.py  # Kernel session tests
│   ├── test_quench_plugin.py   # Main plugin tests
│   ├── test_ui_manager.py      # UI manager tests
│   └── test_web_server.py      # Web server tests
└── e2e/                 # End-to-end integration tests
    ├── test_neovim_instance.py        # Neovim integration tests
    ├── test_quench_interrupt_kernel.py # Kernel interrupt tests
    ├── test_quench_kernel_death.py    # Kernel death detection and auto-restart tests
    ├── test_quench_kernel_start.py    # Kernel start tests
    ├── test_quench_reset_kernel.py    # Kernel reset tests
    ├── test_quench_run_cell.py        # Cell execution tests
    └── test_quench_stop.py            # Plugin stop tests

Examples:
example/
├── example-usage.py     # Comprehensive demonstration
├── quick-start.py       # Simple validation examples
├── nvim-config-example.lua # Complete Neovim configuration
└── README.md           # User getting started guide

Configuration:
lua/quench/init.lua      # Basic Lua module setup
```

## Testing Strategy

**138 tests implemented** with comprehensive coverage:
- **Unit tests** (`tests/unit/`) - Component-level testing
  - `test_kernel_session.py` - Kernel session management tests (35 tests)
    - Manual restart testing
    - Death detection testing via monitoring loop
    - Auto-restart on execution testing
    - Complete death-to-recovery flow coverage
  - `test_quench_plugin.py` - Main plugin class tests
  - `test_ui_manager.py` - UI manager functionality tests
  - `test_web_server.py` - Web server tests
- **End-to-end tests** (`tests/e2e/`) - Full integration testing
  - `test_neovim_instance.py` - Neovim integration tests
  - `test_quench_interrupt_kernel.py` - Kernel interrupt functionality
  - `test_quench_kernel_start.py` - Kernel startup tests
  - `test_quench_reset_kernel.py` - Kernel reset tests
  - `test_quench_run_cell.py` - Cell execution tests
  - `test_quench_stop.py` - Plugin shutdown tests
  - `test_quench_kernel_death.py` - Kernel death detection and auto-restart integration tests
- **Test configuration** (`tests/conftest.py`) - Shared fixtures and dependency detection
- **Dependency detection** - Tests auto-skip when optional dependencies missing
- **Async support** - Full pytest-asyncio integration for testing async functionality
- **Mock-based testing** - Comprehensive mocking for kernel management without real processes
- **Custom markers** - `@pytest.mark.integration`, `@pytest.mark.requires_nvim`, `@pytest.mark.requires_jupyter`

## Dependencies

**Required dependencies:**
- `pynvim` - Neovim integration (required for plugin functionality)
- `jupyter_client` - IPython kernel management (required for code execution)

**Optional dependencies** (graceful fallback if not available):
- `aiohttp` - Web server and WebSocket functionality
- `websockets` - Enhanced WebSocket support
- `matplotlib`, `pandas`, `IPython` - Enhanced rich output support

**Development dependencies:**
- `pytest>=7.0.0` - Test framework  
- `pytest-asyncio>=0.21.0` - Async test support
- `pytest-mock>=3.10.0` - Advanced mocking capabilities
- `pytest-cov>=4.0.0` - Coverage reporting
- `black>=22.0.0` - Code formatting
- `flake8>=5.0.0` - Code style checking

## Key Implementation Details

### Logging
- Logs written to `/tmp/quench.log` with DEBUG level for development
- Component-specific loggers: `quench.main`, `quench.kernel.{kernel_id}`, `quench.web_server`, `quench.kernel_manager`

### Error Handling
- Graceful degradation when optional dependencies missing
- Comprehensive exception handling with logging
- Resource cleanup on plugin shutdown via `VimLeave` autocmd
- Robust async task management with proper cancellation

### **CRITICAL: Synchronous UI Requirements**
**User interface operations MUST be executed synchronously to preserve pynvim context.**

#### UI Operations That MUST Be Synchronous:
- All `nvim` object interactions (`nvim.out_write()`, `nvim.command()`, `nvim.call()`)
- User input collection and choice presentation
- Error notifications to user
- Buffer and cursor operations

#### Backend Operations That CAN Be Asynchronous:
- Kernel process management and startup
- IPython kernel communication
- Web server operations
- File I/O and network requests
- Long-running computations

### Web Server Integration  
- Default server: `http://127.0.0.1:8765`
- WebSocket endpoints: `/ws/{kernel_id}` for real-time output
- Static file serving for frontend assets
- Cell-based output correlation using Jupyter message IDs
- Connection management with automatic cleanup on disconnect

### Configuration and Setup
- **Python Environment**: Uses uv-managed environment at `/home/ryanress/code/ubuntu-config/nvim/pynvim-env/.venv/bin/python`
- **Testing Commands**: Always use the full Python path when running pytest for this plugin
- **Plugin Installation**: Requires `:UpdateRemotePlugins` after installation
- **Example Configuration**: Complete Lua configuration provided in `example/nvim-config-example.lua`
