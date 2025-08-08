"""
Unit tests for Quench plugin components.
"""
import pytest
import asyncio
from unittest.mock import Mock, MagicMock

# Import the UI manager
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rplugin', 'python3'))

from quench.ui_manager import NvimUIManager


class MockBuffer:
    """Mock buffer for testing UI manager functionality."""
    
    def __init__(self, lines, number=1):
        self.lines = lines
        self.number = number
    
    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.lines[key]
        return self.lines[key]
    
    def __setitem__(self, key, value):
        if isinstance(key, slice):
            if key.start is None and key.stop is None:
                # Replace entire buffer
                self.lines[:] = value
            else:
                self.lines[key] = value
        else:
            self.lines[key] = value


class MockNvim:
    """Mock Neovim instance for testing."""
    
    def __init__(self, buffers=None):
        self.buffers = buffers or []
        self.current = Mock()
        self.current.buffer = Mock()
        self.current.buffer.number = 1
    
    def command(self, cmd):
        pass
    
    def call(self, func, *args):
        if func == 'input':
            return '1'  # Default choice
        return None


class TestNvimUIManager:
    """Test cases for the NvimUIManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.nvim = MockNvim()
        self.ui_manager = NvimUIManager(self.nvim)
    
    @pytest.mark.asyncio
    async def test_get_current_bnum(self):
        """Test getting the current buffer number."""
        self.nvim.current.buffer.number = 5
        result = await self.ui_manager.get_current_bnum()
        assert result == 5
    
    @pytest.mark.asyncio
    async def test_get_cell_code_single_cell_beginning(self):
        """Test extracting cell code when the entire file is one cell."""
        lines = [
            'import numpy as np',
            '',
            'x = np.array([1, 2, 3])',
            'print(x)'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 1)
        expected = 'import numpy as np\n\nx = np.array([1, 2, 3])\nprint(x)'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_first_cell_with_delimiter(self):
        """Test extracting the first cell when file has multiple cells."""
        lines = [
            'import numpy as np',
            'print("First cell")',
            '#%%',
            'print("Second cell")',
            'x = 42'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 1)
        expected = 'import numpy as np\nprint("First cell")'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_middle_cell(self):
        """Test extracting a cell in the middle of the file."""
        lines = [
            'print("First cell")',
            '#%%',
            'import matplotlib.pyplot as plt',
            'plt.plot([1, 2, 3])',
            'plt.show()',
            '#%%',
            'print("Third cell")'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 3)  # Line 3 is in middle cell
        expected = 'import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.show()'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_last_cell(self):
        """Test extracting the last cell in the file."""
        lines = [
            'print("First cell")',
            '#%%',
            'print("Second cell")',
            '#%%',
            'import pandas as pd',
            'df = pd.DataFrame({"a": [1, 2, 3]})',
            'print(df)'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 6)  # Line 6 is in last cell
        expected = 'import pandas as pd\ndf = pd.DataFrame({"a": [1, 2, 3]})\nprint(df)'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_cursor_on_delimiter(self):
        """Test extracting cell code when cursor is on the delimiter line."""
        lines = [
            'print("First cell")',
            '#%%',
            'print("Second cell")',
            'x = 1'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 2)  # Line 2 is the delimiter
        expected = 'print("Second cell")\nx = 1'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_empty_cell(self):
        """Test extracting code from an empty cell."""
        lines = [
            'print("First cell")',
            '#%%',
            '',
            '#%%',
            'print("Third cell")'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 3)  # Line 3 is in empty cell
        expected = ''
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_cell_with_empty_lines(self):
        """Test extracting cell code that has empty lines at beginning and end."""
        lines = [
            '#%%',
            '',
            '',
            'x = 1',
            'print(x)',
            '',
            '',
            '#%%',
            'print("Next cell")'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 4)  # Line 4 is in the cell
        expected = 'x = 1\nprint(x)'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_nonexistent_buffer(self):
        """Test handling of nonexistent buffer."""
        result = await self.ui_manager.get_cell_code(999, 1)
        assert result == ''
    
    @pytest.mark.asyncio
    async def test_get_cell_code_empty_buffer(self):
        """Test handling of empty buffer."""
        buffer = MockBuffer([])
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 1)
        assert result == ''
    
    @pytest.mark.asyncio
    async def test_get_cell_code_line_out_of_bounds(self):
        """Test handling of line number beyond buffer length."""
        lines = ['print("Hello")']
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 100)  # Line way beyond buffer
        expected = 'print("Hello")'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_get_cell_code_multiple_consecutive_delimiters(self):
        """Test handling of multiple consecutive cell delimiters."""
        lines = [
            'print("First cell")',
            '#%%',
            '#%%',
            '#%%',
            'print("After multiple delimiters")'
        ]
        buffer = MockBuffer(lines)
        self.nvim.buffers = [buffer]
        
        result = await self.ui_manager.get_cell_code(1, 5)  # After the delimiters
        expected = 'print("After multiple delimiters")'
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_create_output_buffer(self):
        """Test creating an output buffer."""
        mock_buffer = Mock()
        mock_buffer.number = 42
        self.nvim.current.buffer = mock_buffer
        
        result = await self.ui_manager.create_output_buffer()
        assert result == 42
    
    @pytest.mark.asyncio
    async def test_write_to_buffer(self):
        """Test writing lines to a buffer."""
        buffer = MockBuffer(['old line'])
        buffer.number = 1
        self.nvim.buffers = [buffer]
        
        test_lines = ['new line 1', 'new line 2']
        await self.ui_manager.write_to_buffer(1, test_lines)
        
        # Buffer should be updated with new content
        assert buffer.lines == test_lines
    
    @pytest.mark.asyncio
    async def test_write_to_nonexistent_buffer(self):
        """Test writing to a nonexistent buffer (should not crash)."""
        # This should not raise an exception
        await self.ui_manager.write_to_buffer(999, ['test'])
    
    @pytest.mark.asyncio
    async def test_get_user_choice_single_item(self):
        """Test user choice with single item."""
        result = await self.ui_manager.get_user_choice(['only option'])
        assert result == 'only option'
    
    @pytest.mark.asyncio
    async def test_get_user_choice_empty_list(self):
        """Test user choice with empty list."""
        result = await self.ui_manager.get_user_choice([])
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_user_choice_multiple_items(self):
        """Test user choice with multiple items."""
        self.nvim.call = Mock(return_value='2')  # User selects option 2
        
        items = ['option1', 'option2', 'option3']
        result = await self.ui_manager.get_user_choice(items)
        assert result == 'option2'
    
    @pytest.mark.asyncio
    async def test_get_user_choice_invalid_input(self):
        """Test user choice with invalid input."""
        self.nvim.call = Mock(return_value='invalid')  # Invalid input
        
        items = ['option1', 'option2']
        result = await self.ui_manager.get_user_choice(items)
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__])