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
- `pytest tests/test_unit.py` - Run unit tests only
- `pytest tests/test_quench_main.py` - Run main plugin integration tests
- `pytest tests/test_integration.py` - Run integration tests
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
- Main plugin class is in `rplugin/python3/quench/__init__.py` (1171 lines)
- Uses pynvim decorators: `@pynvim.plugin`, `@pynvim.command`, `@pynvim.function`
- The Python environment for testing is managed by uv: `/home/ryanress/code/ubuntu-config/nvim/pynvim-env/.venv/bin/python`

## Code Architecture

### Current State
- **FULLY IMPLEMENTED** - All core Quench functionality is complete and working
- Main plugin class in `rplugin/python3/quench/__init__.py` with async commands:
  - `QuenchRunCell` - Execute Python cells with `#%%` delimiters
  - `QuenchStatus` - Display plugin status and active sessions
  - `QuenchStop` - Stop all plugin components
  - `HelloWorld` - Basic connectivity test (kept for backward compatibility)
- Complete kernel session management with IPython integration
- Web server with WebSocket relay for rich media output
- UI manager for Neovim API interactions
- Frontend HTML/JS application for browser-based output display

### Additional Commands Available
- `QuenchRunCellAdvance` - Execute cell and move cursor to next cell
- `QuenchRunSelection` - Execute selected text as Python code  
- `QuenchRunLine` - Execute current line
- `QuenchRunAbove` - Execute all cells above current position
- `QuenchRunBelow` - Execute all cells below current position
- `QuenchRunAll` - Execute all cells in buffer

### Key Design Patterns
- Asyncio-based architecture for non-blocking operations
- Central message queue (asyncio.Queue) for component communication
- Cell-based execution using `#%%` delimiters in Python files
- Web browser integration for rich media (plots, audio, etc.)

### Codebase Structure
```
Total: 3,806 lines of Python code

Core Plugin:
rplugin/python3/quench/
├── __init__.py          # Main plugin class and pynvim integration (1171 lines)
├── kernel_session.py    # IPython kernel management (348 lines)
├── web_server.py        # Web server and WebSocket handling (339 lines)
├── ui_manager.py        # Neovim API wrapper (197 lines)
└── frontend/            # Web frontend files
    ├── index.html       # Browser interface layout
    └── main.js          # WebSocket client and output rendering

Test Suite:
tests/
├── conftest.py          # Test configuration and fixtures (122 lines)
├── test_integration.py  # Integration tests (327 lines)
├── test_quench_main.py  # Main plugin tests (684 lines)
└── test_unit.py         # Unit tests (300 lines)

Examples:
example/
├── example-usage.py     # Comprehensive demonstration (269 lines)
├── quick-start.py       # Simple validation examples
├── nvim-config-example.lua # Complete Neovim configuration
└── README.md           # User getting started guide

Configuration:
lua/quench/init.lua      # Basic Lua module setup
```

## Testing Strategy

**57 tests implemented** across 3,800+ lines of test code with comprehensive coverage:
- **Unit tests** (`tests/test_unit.py`) - NvimUIManager functionality (300 lines)
- **Plugin integration tests** (`tests/test_quench_main.py`) - Main plugin class testing (684 lines)
- **Integration tests** (`tests/test_integration.py`) - Component interaction testing (327 lines)
- **Test configuration** (`tests/conftest.py`) - Shared fixtures and dependency detection (122 lines)
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
