# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Quench is a Neovim plugin for interactive Python development that enables cell-based execution similar to VS Code's Jupyter extension. The plugin manages IPython kernels and routes output to both terminal and web browser for rich media display.

**Key Architecture**: Asyncio-based Python application using pynvim, consisting of:
- **Kernel Session Manager**: Manages IPython kernel lifecycles
- **Web Server**: aiohttp server that relays kernel output via WebSockets  
- **Neovim UI Manager**: Handles Neovim API interactions

The current repository contains a basic template structure with a simple "HelloWorld" plugin implementation. The detailed specification in README.md outlines the full vision for the plugin.

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
- Plugin files go in `rplugin/python3/quench/`
- Main plugin class is in `rplugin/python3/quench/__init__.py`
- Use pynvim decorators: `@pynvim.plugin`, `@pynvim.command`, `@pynvim.function`

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

### Planned Architecture (from specification)
- **KernelSession**: Individual IPython kernel management with asyncio
- **KernelSessionManager**: Singleton managing all kernel sessions
- **WebServer**: aiohttp application serving frontend and WebSocket relay
- **NvimUIManager**: Wraps Neovim API calls
- **Frontend**: Single-page web app for rich media output display

### Key Design Patterns
- Asyncio-based architecture for non-blocking operations
- Central message queue (asyncio.Queue) for component communication
- Cell-based execution using `#%%` delimiters in Python files
- Web browser integration for rich media (plots, audio, etc.)

### Plugin Structure
```
rplugin/python3/quench/
├── __init__.py          # Main plugin class and pynvim integration (343 lines)
├── kernel_session.py    # IPython kernel management (285 lines)
├── web_server.py        # Web server and WebSocket handling (304 lines) 
├── ui_manager.py        # Neovim API wrapper (174 lines)
└── frontend/            # Web frontend files
    ├── index.html       # Browser interface layout
    └── main.js          # WebSocket client and output rendering
```

## Testing Strategy

**43 tests implemented** with comprehensive coverage:
- **Unit tests** (`tests/test_unit.py`) - 19 tests for NvimUIManager functionality
- **Plugin integration tests** (`tests/test_quench_main.py`) - 18 tests for main plugin class  
- **Integration tests** (`tests/test_integration.py`) - 6 tests for component interaction
- **Dependency detection** - Tests auto-skip when optional dependencies missing
- **Async support** - Full pytest-asyncio integration for testing async functionality
- **Mock-based testing** - Comprehensive mocking for kernel management without processes
- **Custom markers** - `@pytest.mark.integration`, `@pytest.mark.requires_nvim`, etc.

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
- Logs written to `/tmp/quench.log` with INFO level
- Component-specific loggers: `quench.main`, `quench.kernel.{kernel_id}`, `quench.web_server`, `quench.kernel_manager`

### Error Handling
- Graceful degradation when optional dependencies missing
- Comprehensive exception handling with logging
- Resource cleanup on plugin shutdown via `VimLeave` autocmd

### Web Server Integration  
- Default server: `http://127.0.0.1:8765`
- WebSocket endpoints: `/ws/{kernel_id}` for real-time output
- Static file serving for frontend assets
- Cell-based output correlation using Jupyter message IDs