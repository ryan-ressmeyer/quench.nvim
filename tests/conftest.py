"""
Pytest configuration and shared fixtures for Quench tests.
"""
import pytest
import sys
import os
from pathlib import Path

# Add the plugin to Python path
plugin_path = Path(__file__).parent.parent / 'rplugin' / 'python3'
sys.path.insert(0, str(plugin_path))


@pytest.fixture(scope="session")
def plugin_dir():
    """Path to the plugin directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session") 
def has_pynvim():
    """Check if pynvim is available."""
    try:
        import pynvim
        return True
    except ImportError:
        return False


@pytest.fixture(scope="session")
def has_aiohttp():
    """Check if aiohttp is available."""
    try:
        import aiohttp
        return True
    except ImportError:
        return False


@pytest.fixture(scope="session")
def has_websockets():
    """Check if websockets is available."""
    try:
        import websockets
        return True
    except ImportError:
        return False


@pytest.fixture(scope="session")
def has_jupyter_client():
    """Check if jupyter_client is available."""
    try:
        import jupyter_client
        return True
    except ImportError:
        return False


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "requires_nvim: mark test as requiring Neovim"
    )
    config.addinivalue_line(
        "markers", "requires_jupyter: mark test as requiring Jupyter"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add skip markers based on dependencies."""
    for item in items:
        # Auto-skip tests based on available dependencies
        if "test_integration.py" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            
        # Add skip conditions based on test requirements
        if hasattr(item, 'get_closest_marker'):
            if item.get_closest_marker('requires_nvim'):
                try:
                    import pynvim
                except ImportError:
                    item.add_marker(pytest.mark.skip(reason="pynvim not available"))
            
            if item.get_closest_marker('requires_jupyter'):
                try:
                    import jupyter_client
                except ImportError:
                    item.add_marker(pytest.mark.skip(reason="jupyter_client not available"))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end (deselect with '-m \"not e2e\"')"
    )


def pytest_report_header(config):
    """Add information about available dependencies to test report header."""
    deps = []
    
    try:
        import pynvim
        deps.append(f"pynvim-{pynvim.__version__}")
    except ImportError:
        deps.append("pynvim-MISSING")
    
    try:
        import aiohttp
        deps.append(f"aiohttp-{aiohttp.__version__}")
    except ImportError:
        deps.append("aiohttp-MISSING")
        
    try:
        import jupyter_client
        deps.append(f"jupyter_client-{jupyter_client.__version__}")
    except ImportError:
        deps.append("jupyter_client-MISSING")
        
    try:
        import websockets
        deps.append(f"websockets-{websockets.__version__}")
    except ImportError:
        deps.append("websockets-MISSING")
    
    return f"dependencies: {', '.join(deps)}"