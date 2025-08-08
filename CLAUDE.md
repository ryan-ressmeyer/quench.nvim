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
- `make test` - Run the full test suite (configured in CI)
- The project uses plenary.nvim and busted for testing framework

### Code Formatting
- `stylua --color always --check lua` - Check Lua code formatting
- `stylua lua` - Format Lua code (use .stylua.toml configuration)

### Plugin Development
- Plugin files go in `rplugin/python3/quench/`
- Main plugin class is in `rplugin/python3/quench/__init__.py`
- Use pynvim decorators: `@pynvim.plugin`, `@pynvim.command`, `@pynvim.function`

## Code Architecture

### Current State
- Basic pynvim plugin template with HelloWorld command
- Template structure from ellisonleao/nvim-plugin-template
- No implementation of the core quench functionality yet

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
├── __init__.py          # Main plugin class and pynvim integration
├── kernel_session.py    # (planned) Kernel management
├── web_server.py        # (planned) Web server and WebSocket handling
├── ui_manager.py        # (planned) Neovim API wrapper
└── frontend/            # (planned) Web frontend files
```

## Testing Strategy

The specification outlines a comprehensive testing approach:
- Unit tests with pytest for individual components
- Integration tests with embedded Neovim instances
- WebSocket client tests for server communication
- Mock-based testing for kernel management without processes

## Dependencies

Current dependencies:
- pynvim for Neovim integration
- Standard library asyncio for async operations

Planned dependencies (from specification):
- jupyter-client for IPython kernel management
- aiohttp for web server
- Various frontend libraries for rich media rendering