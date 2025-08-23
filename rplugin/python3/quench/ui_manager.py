import asyncio
import re
import pynvim


class NvimUIManager:
    """
    A class that wraps all Neovim API calls for the Quench plugin.
    """

    def __init__(self, nvim):
        """
        Initialize the UI manager with a Neovim instance.

        Args:
            nvim: The pynvim.Nvim instance for interacting with Neovim.
        """
        self.nvim = nvim

    async def get_current_bnum(self):
        """
        Get the current buffer number.

        Returns:
            int: The current buffer number.
        """
        return self.nvim.current.buffer.number

    async def get_cell_code(self, bnum, lnum, delimiter_pattern=r'^#+\s*%%'):
        """
        Find the code cell containing the given line number and return its content.
        
        Code cells are delimited by configurable patterns or file boundaries.

        Args:
            bnum (int): Buffer number
            lnum (int): Line number (1-indexed)
            delimiter_pattern (str): Regex pattern for cell delimiters

        Returns:
            str: The code within the current cell
        """
        # Get the buffer by number
        buffer = None
        try:
            # Try to access buffers property
            if hasattr(self.nvim, 'buffers'):
                for buf in self.nvim.buffers:
                    if buf.number == bnum:
                        buffer = buf
                        break
            else:
                # If we can't find the specific buffer, use current buffer if it matches
                current_buf = self.nvim.current.buffer
                if current_buf.number == bnum:
                    buffer = current_buf
        except (AttributeError, TypeError, pynvim.api.NvimError):
            # Fallback to current buffer or return empty on error
            try:
                buffer = self.nvim.current.buffer
            except (AttributeError, pynvim.api.NvimError):
                return ""
        
        if buffer is None:
            return ""

        # Get all lines from the buffer
        try:
            lines = buffer[:]
            if not lines:
                return ""
        except (AttributeError, TypeError, pynvim.api.NvimError):
            return ""

        # Convert to 0-indexed for Python list access
        current_line_idx = lnum - 1
        if current_line_idx >= len(lines):
            current_line_idx = len(lines) - 1

        # Find the start of the current cell
        cell_start = 0
        for i in range(current_line_idx, -1, -1):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                if i == current_line_idx:
                    # If we're on a cell delimiter line, start from the next line
                    cell_start = i + 1
                else:
                    # Found a previous delimiter, start after it
                    cell_start = i + 1
                break

        # Find the end of the current cell
        cell_end = len(lines)
        for i in range(current_line_idx + 1, len(lines)):
            line = lines[i].strip()
            if re.match(delimiter_pattern, line):
                cell_end = i
                break

        # Extract the cell content
        cell_lines = lines[cell_start:cell_end]
        
        # Remove empty lines at the beginning and end
        while cell_lines and not cell_lines[0].strip():
            cell_lines.pop(0)
        while cell_lines and not cell_lines[-1].strip():
            cell_lines.pop()

        return '\n'.join(cell_lines)

    async def create_output_buffer(self):
        """
        Create a new buffer for displaying output.

        Returns:
            int: The buffer number of the created output buffer
        """
        # Create a new buffer
        self.nvim.command('new')
        output_buffer = self.nvim.current.buffer
        
        # Set buffer options for output display
        self.nvim.command('setlocal buftype=nofile')
        self.nvim.command('setlocal bufhidden=hide')
        self.nvim.command('setlocal noswapfile')
        self.nvim.command('setlocal nomodifiable')
        
        return output_buffer.number

    async def write_to_buffer(self, bnum, lines):
        """
        Write lines to the specified buffer.

        Args:
            bnum (int): Buffer number to write to
            lines (list): List of strings to write to the buffer
        """
        # Find the buffer by number
        buffer = None
        try:
            # Try to access buffers property
            if hasattr(self.nvim, 'buffers'):
                for buf in self.nvim.buffers:
                    if buf.number == bnum:
                        buffer = buf
                        break
            else:
                # If we can't find the specific buffer, use current buffer if it matches
                current_buf = self.nvim.current.buffer
                if current_buf.number == bnum:
                    buffer = current_buf
        except (AttributeError, TypeError, pynvim.api.NvimError):
            # Fallback to current buffer or return on error
            try:
                buffer = self.nvim.current.buffer
            except (AttributeError, pynvim.api.NvimError):
                return
        
        if buffer is None:
            return

        try:
            # Make buffer modifiable temporarily
            self.nvim.command(f'buffer {bnum}')
            self.nvim.command('setlocal modifiable')
            
            # Clear existing content and write new lines
            buffer[:] = lines if isinstance(lines, list) else [lines]
            
            # Make buffer non-modifiable again
            self.nvim.command('setlocal nomodifiable')
        except (AttributeError, TypeError, pynvim.api.NvimError):
            # If we can't write to the buffer, silently fail
            pass

    async def get_user_choice(self, items):
        """
        Present a list of items to the user and get their choice.

        Args:
            items (list): List of items to choose from. Can be:
                         - List of strings (for backward compatibility)
                         - List of dictionaries with 'display_name' and 'value' keys

        Returns:
            str/dict: The selected item's value if dictionary, or the item itself if string.
                     Returns None if cancelled.
        """
        if not items:
            return None

        if len(items) == 1:
            # For single item, return the value if it's a dict, otherwise return the item
            item = items[0]
            if isinstance(item, dict) and 'value' in item:
                return item['value']
            return item

        # Create a numbered list for display
        choices = []
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                # Use display_name if available, fallback to value or string representation
                display_text = item.get('display_name', item.get('value', str(item)))
            else:
                # Backward compatibility: treat as string
                display_text = str(item)
            choices.append(f"{i}. {display_text}")

        # Display choices and get user input
        choice_text = '\n'.join(choices)
        prompt = f"Choose an option:\n{choice_text}\nEnter number (1-{len(items)}): "
        
        try:
            response = self.nvim.call('input', prompt)
            if response is None or response == '':
                return None
            choice_num = int(response.strip())
            
            if 1 <= choice_num <= len(items):
                selected_item = items[choice_num - 1]
                # Return the value if it's a dict, otherwise return the item itself
                if isinstance(selected_item, dict) and 'value' in selected_item:
                    return selected_item['value']
                return selected_item
            else:
                return None
        except (ValueError, KeyboardInterrupt, AttributeError):
            return None