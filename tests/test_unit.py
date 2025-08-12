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

    @pytest.mark.asyncio
    async def test_get_user_choice_single_dict_item(self):
        """Test user choice with single dictionary item."""
        item = {'display_name': 'Python 3.9', 'value': 'python39'}
        result = await self.ui_manager.get_user_choice([item])
        assert result == 'python39'
    
    @pytest.mark.asyncio
    async def test_get_user_choice_single_dict_no_value(self):
        """Test user choice with single dictionary item without value key."""
        item = {'display_name': 'Python 3.9'}
        result = await self.ui_manager.get_user_choice([item])
        assert result == item  # Should return the whole dict if no value key
    
    @pytest.mark.asyncio
    async def test_get_user_choice_multiple_dict_items(self):
        """Test user choice with multiple dictionary items."""
        self.nvim.call = Mock(return_value='2')  # User selects option 2
        
        items = [
            {'display_name': 'Python 3.9', 'value': 'python39'},
            {'display_name': 'Python 3.10', 'value': 'python310'},
            {'display_name': 'Conda Environment', 'value': 'conda_env'}
        ]
        result = await self.ui_manager.get_user_choice(items)
        assert result == 'python310'
    
    @pytest.mark.asyncio
    async def test_get_user_choice_dict_without_display_name(self):
        """Test user choice with dictionary items without display_name."""
        self.nvim.call = Mock(return_value='1')  # User selects option 1
        
        items = [
            {'value': 'python39'},
            {'value': 'python310'}
        ]
        result = await self.ui_manager.get_user_choice(items)
        assert result == 'python39'
    
    @pytest.mark.asyncio
    async def test_get_user_choice_mixed_items(self):
        """Test user choice with mixed string and dictionary items."""
        self.nvim.call = Mock(return_value='3')  # User selects option 3
        
        items = [
            'string_option',
            {'display_name': 'Python 3.9', 'value': 'python39'},
            {'display_name': 'Python 3.10', 'value': 'python310'}
        ]
        result = await self.ui_manager.get_user_choice(items)
        assert result == 'python310'
    
    @pytest.mark.asyncio
    async def test_get_user_choice_dict_fallback_display(self):
        """Test user choice with dictionary using fallback display logic."""
        self.nvim.call = Mock(return_value='1')  # User selects option 1
        
        items = [
            {'some_key': 'some_value'},  # No display_name or value, should use str representation
        ]
        result = await self.ui_manager.get_user_choice(items)
        assert result == items[0]  # Should return the whole dict


class TestKernelSessionManager:
    """Test KernelSessionManager methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Reset singleton instance for testing
        from quench.kernel_session import KernelSessionManager
        KernelSessionManager._instance = None
        KernelSessionManager._initialized = False
        self.manager = KernelSessionManager()
    
    @pytest.mark.asyncio
    async def test_discover_kernelspecs_success(self):
        """Test successful discovery of kernel specifications."""
        from unittest.mock import patch, mock_open
        import json
        
        # Mock jupyter kernelspec command output
        mock_kernelspec_data = {
            "kernelspecs": {
                "python3": {
                    "resource_dir": "/usr/local/share/jupyter/kernels/python3",
                    "spec": {
                        "argv": [
                            "python",
                            "-m",
                            "ipykernel_launcher",
                            "-f",
                            "{connection_file}"
                        ],
                        "env": {},
                        "display_name": "Python 3",
                        "language": "python",
                        "interrupt_mode": "signal",
                        "metadata": {}
                    }
                },
                "conda-base": {
                    "resource_dir": "/home/user/anaconda3/share/jupyter/kernels/python3",
                    "spec": {
                        "argv": [
                            "/home/user/anaconda3/bin/python",
                            "-m",
                            "ipykernel_launcher",
                            "-f",
                            "{connection_file}"
                        ],
                        "env": {},
                        "display_name": "Python 3 (conda-base)",
                        "language": "python",
                        "interrupt_mode": "signal",
                        "metadata": {}
                    }
                }
            }
        }
        
        mock_result = Mock()
        mock_result.stdout = json.dumps(mock_kernelspec_data)
        mock_result.returncode = 0
        
        with patch('subprocess.run', return_value=mock_result) as mock_run, \
             patch('sys.executable', '/usr/bin/python3'):
            
            kernelspecs = await self.manager.discover_kernelspecs()
            
            # Verify subprocess.run was called with correct arguments
            mock_run.assert_called_once_with(
                ['jupyter', 'kernelspec', 'list', '--json'],
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            
            # Verify results
            assert len(kernelspecs) == 3  # Neovim's Python + 2 discovered
            
            # Check Neovim's Python kernel (should be first)
            neovim_kernel = kernelspecs[0]
            assert neovim_kernel['name'] == 'neovim_python'
            assert neovim_kernel['display_name'] == "Neovim's Python"
            assert neovim_kernel['argv'] == ['/usr/bin/python3', '-m', 'ipykernel_launcher', '-f', '{connection_file}']
            
            # Check discovered kernels
            python3_kernel = next((k for k in kernelspecs if k['name'] == 'python3'), None)
            assert python3_kernel is not None
            assert python3_kernel['display_name'] == 'Python 3'
            assert python3_kernel['argv'] == ['python', '-m', 'ipykernel_launcher', '-f', '{connection_file}']
            
            conda_kernel = next((k for k in kernelspecs if k['name'] == 'conda-base'), None)
            assert conda_kernel is not None
            assert conda_kernel['display_name'] == 'Python 3 (conda-base)'
            assert conda_kernel['argv'] == ['/home/user/anaconda3/bin/python', '-m', 'ipykernel_launcher', '-f', '{connection_file}']
    
    @pytest.mark.asyncio
    async def test_discover_kernelspecs_jupyter_not_found(self):
        """Test discovery when jupyter command is not found."""
        from unittest.mock import patch
        
        with patch('subprocess.run', side_effect=FileNotFoundError("jupyter not found")) as mock_run, \
             patch('sys.executable', '/usr/bin/python3'):
            
            kernelspecs = await self.manager.discover_kernelspecs()
            
            # Should still return Neovim's Python kernel
            assert len(kernelspecs) == 1
            assert kernelspecs[0]['name'] == 'neovim_python'
            assert kernelspecs[0]['display_name'] == "Neovim's Python"
    
    @pytest.mark.asyncio
    async def test_discover_kernelspecs_subprocess_error(self):
        """Test discovery when jupyter command fails."""
        from unittest.mock import patch
        import subprocess
        
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'jupyter')) as mock_run, \
             patch('sys.executable', '/usr/bin/python3'):
            
            kernelspecs = await self.manager.discover_kernelspecs()
            
            # Should still return Neovim's Python kernel
            assert len(kernelspecs) == 1
            assert kernelspecs[0]['name'] == 'neovim_python'
    
    @pytest.mark.asyncio
    async def test_discover_kernelspecs_invalid_json(self):
        """Test discovery with invalid JSON response."""
        from unittest.mock import patch
        
        mock_result = Mock()
        mock_result.stdout = "invalid json"
        mock_result.returncode = 0
        
        with patch('subprocess.run', return_value=mock_result) as mock_run, \
             patch('sys.executable', '/usr/bin/python3'):
            
            kernelspecs = await self.manager.discover_kernelspecs()
            
            # Should still return Neovim's Python kernel
            assert len(kernelspecs) == 1
            assert kernelspecs[0]['name'] == 'neovim_python'
    
    @pytest.mark.asyncio
    async def test_discover_kernelspecs_timeout(self):
        """Test discovery with subprocess timeout."""
        from unittest.mock import patch
        import subprocess
        
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('jupyter', 10)) as mock_run, \
             patch('sys.executable', '/usr/bin/python3'):
            
            kernelspecs = await self.manager.discover_kernelspecs()
            
            # Should still return Neovim's Python kernel
            assert len(kernelspecs) == 1
            assert kernelspecs[0]['name'] == 'neovim_python'
    
    @pytest.mark.asyncio
    async def test_kernel_session_with_custom_kernel_name(self):
        """Test creating a KernelSession with a custom kernel name."""
        from unittest.mock import Mock, AsyncMock, patch
        
        # Create a mock relay queue
        relay_queue = Mock()
        
        # Create session with custom kernel name
        session = self.manager.sessions.__class__.__dict__['__module__']
        from quench.kernel_session import KernelSession
        kernel_session = KernelSession(relay_queue, "test_buffer", "conda-env")
        
        # Verify the kernel name is set correctly
        assert kernel_session.kernel_name == "conda-env"
        assert kernel_session.buffer_name == "test_buffer"
    
    @pytest.mark.asyncio
    async def test_kernel_session_default_kernel_name(self):
        """Test creating a KernelSession with default kernel name."""
        from unittest.mock import Mock
        
        # Create a mock relay queue
        relay_queue = Mock()
        
        # Create session without kernel name (should default to 'python3')
        from quench.kernel_session import KernelSession
        kernel_session = KernelSession(relay_queue, "test_buffer")
        
        # Verify the kernel name defaults to 'python3'
        assert kernel_session.kernel_name == "python3"
    
    @pytest.mark.asyncio
    async def test_kernel_session_start_with_custom_kernel(self):
        """Test starting a kernel session with a custom kernel name."""
        from unittest.mock import Mock, AsyncMock, patch
        
        # Create a mock relay queue
        relay_queue = Mock()
        
        # Create session with custom kernel name
        from quench.kernel_session import KernelSession
        kernel_session = KernelSession(relay_queue, "test_buffer", "conda-env")
        
        # Mock the AsyncKernelManager and related components
        mock_km = AsyncMock()
        mock_client = AsyncMock()
        mock_km.client.return_value = mock_client
        
        with patch('quench.kernel_session.AsyncKernelManager', return_value=mock_km) as mock_km_class, \
             patch('quench.kernel_session.JUPYTER_CLIENT_AVAILABLE', True), \
             patch.object(kernel_session, '_listen_iopub', new_callable=AsyncMock) as mock_listen:
            
            await kernel_session.start()
            
            # Verify AsyncKernelManager was created with the correct kernel name
            mock_km_class.assert_called_once_with(kernel_name='conda-env')
            mock_km.start_kernel.assert_called_once()
            mock_client.start_channels.assert_called_once()
            mock_client.wait_for_ready.assert_called_once_with(timeout=30)
    
    @pytest.mark.asyncio
    async def test_kernel_session_start_with_override_kernel(self):
        """Test starting a kernel session with kernel name override."""
        from unittest.mock import Mock, AsyncMock, patch
        
        # Create a mock relay queue
        relay_queue = Mock()
        
        # Create session with one kernel name but override during start
        from quench.kernel_session import KernelSession
        kernel_session = KernelSession(relay_queue, "test_buffer", "python3")
        
        # Mock the AsyncKernelManager and related components
        mock_km = AsyncMock()
        mock_client = AsyncMock()
        mock_km.client.return_value = mock_client
        
        with patch('quench.kernel_session.AsyncKernelManager', return_value=mock_km) as mock_km_class, \
             patch('quench.kernel_session.JUPYTER_CLIENT_AVAILABLE', True), \
             patch.object(kernel_session, '_listen_iopub', new_callable=AsyncMock) as mock_listen:
            
            # Start with a different kernel name
            await kernel_session.start("julia-1.6")
            
            # Verify AsyncKernelManager was created with the override kernel name
            mock_km_class.assert_called_once_with(kernel_name='julia-1.6')
    
    @pytest.mark.asyncio
    async def test_get_or_create_session_with_kernel_name(self):
        """Test get_or_create_session with custom kernel name."""
        from unittest.mock import Mock, AsyncMock, patch
        
        # Create a mock relay queue
        relay_queue = AsyncMock()
        
        # Mock the KernelSession and its start method
        with patch('quench.kernel_session.KernelSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-id"
            mock_session.start = AsyncMock()
            mock_session_class.return_value = mock_session
            
            # Create session with custom kernel name
            session = await self.manager.get_or_create_session(
                bnum=1, 
                relay_queue=relay_queue, 
                buffer_name="test_buffer",
                kernel_name="conda-env"
            )
            
            # Verify KernelSession was created with the correct parameters
            mock_session_class.assert_called_once_with(relay_queue, "test_buffer", "conda-env")
            mock_session.start.assert_called_once()
            
            # Verify session is stored and mapped correctly
            assert session == mock_session
            assert "test-kernel-id" in self.manager.sessions
            assert 1 in self.manager.buffer_to_kernel_map
    
    @pytest.mark.asyncio
    async def test_get_or_create_session_default_kernel_name(self):
        """Test get_or_create_session with default kernel name."""
        from unittest.mock import Mock, AsyncMock, patch
        
        # Create a mock relay queue
        relay_queue = AsyncMock()
        
        # Mock the KernelSession and its start method
        with patch('quench.kernel_session.KernelSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.kernel_id = "test-kernel-id-2"
            mock_session.start = AsyncMock()
            mock_session_class.return_value = mock_session
            
            # Create session without kernel name (should pass None)
            session = await self.manager.get_or_create_session(
                bnum=2, 
                relay_queue=relay_queue, 
                buffer_name="test_buffer2"
            )
            
            # Verify KernelSession was created with None kernel_name (will default to 'python3')
            mock_session_class.assert_called_once_with(relay_queue, "test_buffer2", None)
            mock_session.start.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__])