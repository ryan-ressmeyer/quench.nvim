"""
Unit tests for configuration management.
"""

import pytest
import sys
import os
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "rplugin", "python3"))

from quench.core.config import (
    get_cell_delimiter,
    get_web_server_host,
    get_web_server_port,
    get_web_server_auto_select_port,
    get_autostart_server,
)


class TestConfiguration:
    """Test cases for configuration utilities."""

    def test_get_autostart_server_default(self):
        """Test get_autostart_server returns True by default."""
        mock_nvim = Mock()
        mock_nvim.vars.get = Mock(return_value=True)
        mock_logger = Mock()

        result = get_autostart_server(mock_nvim, mock_logger)

        assert result is True
        mock_nvim.vars.get.assert_called_once_with("quench_nvim_autostart_server", True)

    def test_get_autostart_server_disabled(self):
        """Test get_autostart_server respects False configuration."""
        mock_nvim = Mock()
        mock_nvim.vars.get = Mock(return_value=False)
        mock_logger = Mock()

        result = get_autostart_server(mock_nvim, mock_logger)

        assert result is False

    def test_get_autostart_server_error_fallback(self):
        """Test get_autostart_server falls back to True on error."""
        mock_nvim = Mock()
        mock_nvim.vars.get = Mock(side_effect=Exception("Test error"))
        mock_logger = Mock()

        result = get_autostart_server(mock_nvim, mock_logger)

        assert result is True  # Default fallback
        mock_logger.warning.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
