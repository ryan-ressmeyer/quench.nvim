"""
Code execution commands for the Quench plugin.

This module contains command implementation functions for:
- Single cell execution
- Cell execution with cursor advancement
- Selection execution
- Line execution
- Batch execution (above, below, all cells)

These are implementation functions only - decorators are in the main plugin class.
"""

from ..core.config import get_cell_delimiter
from ..core.cell_parser import (
    extract_cell,
    extract_cells_above,
    extract_cells_below,
    extract_all_cells
)
from ..utils.notifications import notify_user, select_from_choices_sync


def _prepare_buffer_data(plugin):
    """Helper to get buffer data synchronously."""
    try:
        current_bnum = plugin.nvim.current.buffer.number
        current_line = plugin.nvim.current.window.cursor[0]  # 1-indexed
        buffer = plugin.nvim.current.buffer
        lines = buffer[:]
        plugin._logger.info(f"Got buffer data: {current_bnum}, line {current_line}, {len(lines)} lines")
        return current_bnum, current_line, lines
    except Exception as e:
        plugin._logger.error(f"Error getting buffer data: {e}")
        notify_user(plugin.nvim, f"Error accessing buffer: {e}", level='error')
        return None, None, None


def run_cell_impl(plugin):
    """
    Execute the current cell in IPython kernel (sync wrapper for async implementation).

    This function handles all synchronous UI operations first, then delegates
    to the async implementation.
    """
    plugin._logger.info("QuenchRunCell called - starting execution")

    # Get all the synchronous Neovim data we need first
    current_bnum, current_line, lines = _prepare_buffer_data(plugin)
    if current_bnum is None:
        return

    # Extract cell code synchronously
    try:
        delimiter_pattern = get_cell_delimiter(plugin.nvim, plugin._logger)
        cell_code, cell_start_line, cell_end_line = extract_cell(lines, current_line, delimiter_pattern)
        if not cell_code.strip():
            notify_user(plugin.nvim, "No code found in current cell")
            return

        plugin._logger.debug(f"Cell code extracted: {len(cell_code)} characters")
        notify_user(plugin.nvim, f"Quench: Executing cell (lines {cell_start_line}-{cell_end_line})")

    except Exception as e:
        plugin._logger.error(f"Error extracting cell code: {e}")
        notify_user(plugin.nvim, f"Error extracting cell: {e}", level='error')
        return

    # Get or select kernel synchronously
    kernel_choice = plugin._get_or_select_kernel_sync(current_bnum)
    if not kernel_choice:
        return

    # Return the async coroutine
    return plugin._run_cell_async(current_bnum, cell_code, kernel_choice)


def run_cell_advance_impl(plugin):
    """
    Execute the current cell and advance cursor to the line following the end of that cell.
    """
    plugin._logger.info("QuenchRunCellAdvance called - starting execution")

    # Get all the synchronous Neovim data we need first
    current_bnum, current_line, lines = _prepare_buffer_data(plugin)
    if current_bnum is None:
        return

    # Extract cell code and get end line
    try:
        delimiter_pattern = get_cell_delimiter(plugin.nvim, plugin._logger)
        cell_code, cell_start_line, cell_end_line = extract_cell(lines, current_line, delimiter_pattern)
        if not cell_code.strip():
            notify_user(plugin.nvim, "No code found in current cell")
            return

        plugin._logger.debug(f"Cell code extracted: {len(cell_code)} characters, ends at line {cell_end_line}")
        notify_user(plugin.nvim, f"Quench: Executing cell (lines {cell_start_line}-{cell_end_line})")

    except Exception as e:
        plugin._logger.error(f"Error extracting cell code: {e}")
        notify_user(plugin.nvim, f"Error extracting cell: {e}", level='error')
        return

    # Immediately advance the cursor
    try:
        advance_line = min(cell_end_line + 1, len(lines))
        plugin.nvim.current.window.cursor = (advance_line, 0)
        plugin._logger.debug(f"Advanced cursor to line {advance_line}")
    except Exception as e:
        plugin._logger.error(f"Error advancing cursor: {e}")
        # Don't fail execution if cursor advance fails

    # Get or select kernel synchronously
    kernel_choice = plugin._get_or_select_kernel_sync(current_bnum)
    if not kernel_choice:
        return

    # Return the async coroutine
    return plugin._run_cell_async(current_bnum, cell_code, kernel_choice)


def run_selection_impl(plugin, range_info):
    """
    Execute the current selection in IPython kernel.
    """
    plugin._logger.info("QuenchRunSelection called - starting execution")

    # Get current buffer data
    current_bnum, _, _ = _prepare_buffer_data(plugin)
    if current_bnum is None:
        return

    # Get the selected text
    try:
        if range_info == [0, 0] or range_info is None:
            # No range provided, get visual selection
            selected_lines = plugin.nvim.eval('getline("\'<", "\'>")')
        else:
            # Range provided (e.g., from command line)
            start_line, end_line = range_info
            selected_lines = plugin.nvim.current.buffer[start_line-1:end_line]

        if not selected_lines:
            notify_user(plugin.nvim, "No selection found")
            return

        selected_code = '\n'.join(selected_lines)
        if not selected_code.strip():
            notify_user(plugin.nvim, "Selected text is empty")
            return

        plugin._logger.debug(f"Selected code extracted: {len(selected_code)} characters")
        notify_user(plugin.nvim, f"Quench: Executing selection ({len(selected_lines)} lines)")

    except Exception as e:
        plugin._logger.error(f"Error extracting selection: {e}")
        notify_user(plugin.nvim, f"Error extracting selection: {e}", level='error')
        return

    # Get or select kernel synchronously
    kernel_choice = plugin._get_or_select_kernel_sync(current_bnum)
    if not kernel_choice:
        return

    # Return the async coroutine
    return plugin._run_cell_async(current_bnum, selected_code, kernel_choice)


def run_line_impl(plugin):
    """
    Execute the current line in IPython kernel.
    """
    plugin._logger.info("QuenchRunLine called - starting execution")

    # Get current buffer data
    current_bnum, current_line, _ = _prepare_buffer_data(plugin)
    if current_bnum is None:
        return

    # Get the current line content
    try:
        line_content = plugin.nvim.current.line
        if not line_content.strip():
            notify_user(plugin.nvim, "Current line is empty")
            return

        plugin._logger.debug(f"Line content: {line_content}")
        notify_user(plugin.nvim, f"Quench: Executing line {current_line}")

    except Exception as e:
        plugin._logger.error(f"Error getting line content: {e}")
        notify_user(plugin.nvim, f"Error getting line content: {e}", level='error')
        return

    # Get or select kernel synchronously
    kernel_choice = plugin._get_or_select_kernel_sync(current_bnum)
    if not kernel_choice:
        return

    # Return the async coroutine
    return plugin._run_cell_async(current_bnum, line_content, kernel_choice)


def run_above_impl(plugin):
    """
    Execute all cells above the current cursor position in IPython kernel.
    """
    plugin._logger.info("QuenchRunAbove called - starting execution")

    # Get current buffer data
    current_bnum, current_line, lines = _prepare_buffer_data(plugin)
    if current_bnum is None:
        return

    # Extract all cells above current position
    try:
        delimiter_pattern = get_cell_delimiter(plugin.nvim, plugin._logger)
        cells_above = extract_cells_above(lines, current_line, delimiter_pattern)

        if not cells_above:
            notify_user(plugin.nvim, "No cells found above current position")
            return

        # Combine all cells above into one execution
        combined_code = '\n\n'.join(cells_above)
        plugin._logger.debug(f"Combined code from {len(cells_above)} cells: {len(combined_code)} characters")
        notify_user(plugin.nvim, f"Quench: Executing {len(cells_above)} cells above current position")

    except Exception as e:
        plugin._logger.error(f"Error extracting cells above: {e}")
        notify_user(plugin.nvim, f"Error extracting cells above: {e}", level='error')
        return

    # Get or select kernel synchronously
    kernel_choice = plugin._get_or_select_kernel_sync(current_bnum)
    if not kernel_choice:
        return

    # Return the async coroutine
    return plugin._run_cell_async(current_bnum, combined_code, kernel_choice)


def run_below_impl(plugin):
    """
    Execute all cells below the current cursor position in IPython kernel.
    """
    plugin._logger.info("QuenchRunBelow called - starting execution")

    # Get current buffer data
    current_bnum, current_line, lines = _prepare_buffer_data(plugin)
    if current_bnum is None:
        return

    # Extract all cells below current position
    try:
        delimiter_pattern = get_cell_delimiter(plugin.nvim, plugin._logger)
        cells_below = extract_cells_below(lines, current_line, delimiter_pattern)

        if not cells_below:
            notify_user(plugin.nvim, "No cells found below current position")
            return

        # Combine all cells below into one execution
        combined_code = '\n\n'.join(cells_below)
        plugin._logger.debug(f"Combined code from {len(cells_below)} cells: {len(combined_code)} characters")
        notify_user(plugin.nvim, f"Quench: Executing {len(cells_below)} cells below current position")

    except Exception as e:
        plugin._logger.error(f"Error extracting cells below: {e}")
        notify_user(plugin.nvim, f"Error extracting cells below: {e}", level='error')
        return

    # Get or select kernel synchronously
    kernel_choice = plugin._get_or_select_kernel_sync(current_bnum)
    if not kernel_choice:
        return

    # Return the async coroutine
    return plugin._run_cell_async(current_bnum, combined_code, kernel_choice)


def run_all_impl(plugin):
    """
    Execute all cells in the current buffer in IPython kernel.
    """
    plugin._logger.info("QuenchRunAll called - starting execution")

    # Get current buffer data
    current_bnum, _, lines = _prepare_buffer_data(plugin)
    if current_bnum is None:
        return

    # Extract all cells in buffer
    try:
        delimiter_pattern = get_cell_delimiter(plugin.nvim, plugin._logger)
        all_cells = extract_all_cells(lines, delimiter_pattern)

        if not all_cells:
            notify_user(plugin.nvim, "No cells found in buffer")
            return

        # Combine all cells into one execution
        combined_code = '\n\n'.join(all_cells)
        plugin._logger.debug(f"Combined code from {len(all_cells)} cells: {len(combined_code)} characters")
        notify_user(plugin.nvim, f"Quench: Executing all {len(all_cells)} cells in buffer")

    except Exception as e:
        plugin._logger.error(f"Error extracting all cells: {e}")
        notify_user(plugin.nvim, f"Error extracting all cells: {e}", level='error')
        return

    # Get or select kernel synchronously
    kernel_choice = plugin._get_or_select_kernel_sync(current_bnum)
    if not kernel_choice:
        return

    # Return the async coroutine
    return plugin._run_cell_async(current_bnum, combined_code, kernel_choice)
