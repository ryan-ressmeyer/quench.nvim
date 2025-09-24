"""
Cell parsing utilities for the Quench plugin.

This module contains functions for extracting and parsing Python code cells
from Neovim buffers using cell delimiter patterns.
"""
import re
from typing import List, Tuple


def extract_cell(lines: List[str], lnum: int, delimiter_pattern: str) -> Tuple[str, int, int]:
    """
    Extract a code cell.

    Args:
        lines: List of buffer lines
        lnum: Current line number (1-indexed)
        delimiter_pattern: Regex pattern for cell delimiters

    Returns:
        tuple: (cell_code, cell_start_line, cell_end_line) where lines are 1-indexed
    """
    if not lines:
        return "", 0, 0

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

    return '\n'.join(cell_lines), cell_start + 1, cell_end


def extract_cells_above(lines: List[str], current_line: int, delimiter_pattern: str) -> List[str]:
    """
    Extract all cell codes from the top of buffer up to (but not including) current cell.

    Args:
        lines: List of buffer lines
        current_line: Current cursor line (1-indexed)
        delimiter_pattern: Regex pattern for cell delimiters

    Returns:
        list: List of cell code strings
    """
    if not lines:
        return []

    # Convert to 0-indexed
    current_line_idx = current_line - 1
    if current_line_idx >= len(lines):
        current_line_idx = len(lines) - 1

    # Find start of current cell
    current_cell_start = 0
    for i in range(current_line_idx, -1, -1):
        line = lines[i].strip()
        if re.match(delimiter_pattern, line):
            if i == current_line_idx:
                # If we're on a delimiter, current cell starts at next line
                current_cell_start = i + 1
            else:
                # Found previous delimiter, current cell starts after it
                current_cell_start = i + 1
            break

    # Find all cell delimiters before current cell
    cell_starts = [0]  # Buffer always starts a cell
    for i in range(current_cell_start):
        line = lines[i].strip()
        if re.match(delimiter_pattern, line):
            cell_starts.append(i + 1)  # Cell starts after delimiter

    # Extract cells
    cells = []
    for i in range(len(cell_starts)):
        start = cell_starts[i]
        end = cell_starts[i + 1] - 1 if i + 1 < len(cell_starts) else current_cell_start

        if start < end:
            cell_lines = lines[start:end]
            # Remove empty lines at beginning and end
            while cell_lines and not cell_lines[0].strip():
                cell_lines.pop(0)
            while cell_lines and not cell_lines[-1].strip():
                cell_lines.pop()

            if cell_lines:
                cells.append('\n'.join(cell_lines))

    return cells


def extract_cells_below(lines: List[str], current_line: int, delimiter_pattern: str) -> List[str]:
    """
    Extract all cell codes from current cell to end of buffer.

    Args:
        lines: List of buffer lines
        current_line: Current cursor line (1-indexed)
        delimiter_pattern: Regex pattern for cell delimiters

    Returns:
        list: List of cell code strings
    """
    if not lines:
        return []

    # Convert to 0-indexed
    current_line_idx = current_line - 1
    if current_line_idx >= len(lines):
        current_line_idx = len(lines) - 1

    # Find start of current cell
    current_cell_start = 0
    for i in range(current_line_idx, -1, -1):
        line = lines[i].strip()
        if re.match(delimiter_pattern, line):
            if i == current_line_idx:
                # If we're on a delimiter, current cell starts at next line
                current_cell_start = i + 1
            else:
                # Found previous delimiter, current cell starts after it
                current_cell_start = i + 1
            break

    # Find all cell delimiters from current position to end
    cell_starts = [current_cell_start]
    for i in range(current_cell_start, len(lines)):
        line = lines[i].strip()
        if re.match(delimiter_pattern, line):
            cell_starts.append(i + 1)  # Cell starts after delimiter

    # Extract cells
    cells = []
    for i in range(len(cell_starts)):
        start = cell_starts[i]
        end = cell_starts[i + 1] - 1 if i + 1 < len(cell_starts) else len(lines)

        if start < end:
            cell_lines = lines[start:end]
            # Remove empty lines at beginning and end
            while cell_lines and not cell_lines[0].strip():
                cell_lines.pop(0)
            while cell_lines and not cell_lines[-1].strip():
                cell_lines.pop()

            if cell_lines:
                cells.append('\n'.join(cell_lines))

    return cells


def extract_all_cells(lines: List[str], delimiter_pattern: str) -> List[str]:
    """
    Extract all cell codes from the entire buffer.

    Args:
        lines: List of buffer lines
        delimiter_pattern: Regex pattern for cell delimiters

    Returns:
        list: List of cell code strings
    """
    if not lines:
        return []

    # Find all cell delimiters
    cell_starts = [0]  # Buffer always starts a cell
    for i, line in enumerate(lines):
        if re.match(delimiter_pattern, line.strip()):
            cell_starts.append(i + 1)  # Cell starts after delimiter

    # Extract cells
    cells = []
    for i in range(len(cell_starts)):
        start = cell_starts[i]
        end = cell_starts[i + 1] - 1 if i + 1 < len(cell_starts) else len(lines)

        if start < end:
            cell_lines = lines[start:end]
            # Remove empty lines at beginning and end
            while cell_lines and not cell_lines[0].strip():
                cell_lines.pop(0)
            while cell_lines and not cell_lines[-1].strip():
                cell_lines.pop()

            if cell_lines:
                cells.append('\n'.join(cell_lines))

    return cells
