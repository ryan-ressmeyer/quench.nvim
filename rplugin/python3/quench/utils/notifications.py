"""
User notification utilities for the Quench plugin.

This module contains utility functions for notifying users and getting their input
in a standardized way across the plugin.
"""
from typing import List, Dict, Optional, Any


def notify_user(nvim: Any, message: str, level: str = 'info') -> None:
    """
    Send a single-line notification to the user.

    Args:
        nvim: The pynvim.Nvim instance for interacting with Neovim
        message: The message to display to the user
        level: The notification level ('info' or 'error')
    """
    if level == 'info':
        nvim.out_write(message + '\n')
    elif level == 'error':
        nvim.err_write(message + '\n')


def notify_error_after_input(nvim: Any, message: str) -> None:
    """
    Display an error message after an input() dialog without requiring enter press.

    This function clears the command line with redraw and displays a red error
    message using echohl ErrorMsg, avoiding the "Press ENTER" prompt that
    nvim.err_write() would trigger after input().

    Args:
        nvim: The pynvim.Nvim instance for interacting with Neovim
        message: The error message to display
    """
    nvim.command('redraw')
    # Escape single quotes for vim command
    escaped = message.replace("'", "''")
    nvim.command(f"echohl ErrorMsg | echo '{escaped}' | echohl None")


def select_from_choices_sync(nvim: Any, choices: List[Dict[str, str]], prompt_title: str) -> Optional[Dict[str, str]]:
    """
    Helper method to present choices to user and get their selection.

    Args:
        nvim: The pynvim.Nvim instance for interacting with Neovim
        choices: List of choice dictionaries with 'display_name' and 'value' keys
        prompt_title: Title to display to the user

    Returns:
        The selected choice dictionary or None if cancelled/failed
    """
    import logging
    logger = logging.getLogger('quench.notifications')

    logger.info(f"select_from_choices_sync called with {len(choices) if choices else 0} choices")
    logger.info(f"prompt_title: {prompt_title}")

    if not choices:
        logger.error("No choices provided")
        notify_user(nvim, "No choices available", level='error')
        return None

    if len(choices) == 1:
        logger.info("Only one choice available, returning it directly")
        return choices[0]

    # Create display choices with numbers
    display_choices = [f"{i+1}. {choice['display_name']}" for i, choice in enumerate(choices)]
    logger.info(f"Created display_choices: {display_choices}")

    # Try to display choices to user - may fail in headless/test environments
    display_success = False
    try:
        nvim.out_write(f"{prompt_title}:\n" + "\n".join(display_choices) + "\n")
        display_success = True
    except Exception as e:
        # Log the specific error for debugging
        import logging
        logger = logging.getLogger('quench.notifications')
        logger.error(f"nvim.out_write failed: {e}")

        # Try alternative display method
        try:
            # Fallback to echo command
            nvim.command(f'echo "{prompt_title}"')
            for choice in display_choices:
                nvim.command(f'echo "{choice}"')
            display_success = True
            logger.info("Fallback echo method succeeded")
        except Exception as e2:
            # If both methods fail, log the error but continue
            logger.error(f"Fallback echo method also failed: {e2}")

    if not display_success:
        # Last resort: try redraw and message
        try:
            nvim.command('redraw')
            nvim.command(f'echom "{prompt_title}"')
            for choice in display_choices:
                nvim.command(f'echom "{choice}"')
        except Exception as e3:
            import logging
            logger = logging.getLogger('quench.notifications')
            logger.error(f"All display methods failed: {e3}")

    # Get user input - may also fail in headless environments
    logger.info("About to call nvim.call('input', 'Enter selection number: ')")
    try:
        choice_input = nvim.call('input', 'Enter selection number: ')
        logger.info(f"Got input from user: {repr(choice_input)} (type: {type(choice_input)})")
    except Exception as e:
        # In test environments, nvim.call('input') may also fail due to pynvim internal state
        logger.error(f"nvim.call('input') failed: {e}")
        return None

    # Handle None input (can happen in test environments or certain contexts)
    if choice_input is None:
        logger.error("Received None input")
        notify_error_after_input(nvim, "No input received. Selection cancelled.")
        return None

    # Handle empty string input
    if isinstance(choice_input, str) and choice_input.strip() == '':
        logger.error("Received empty string input")
        notify_error_after_input(nvim, "Empty input. Selection cancelled.")
        return None

    logger.info(f"Processing input: {repr(choice_input)}")
    try:
        choice_idx = int(choice_input) - 1
        logger.info(f"Converted to index: {choice_idx}")
        if 0 <= choice_idx < len(choices):
            selected_choice = choices[choice_idx]
            logger.info(f"Selected choice: {selected_choice}")
            return selected_choice
        else:
            logger.error(f"Invalid selection index {choice_idx}, must be between 0 and {len(choices)-1}")
            notify_error_after_input(nvim, f"Invalid selection: number out of range (1-{len(choices)}). No kernel selected.")
            return None
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to convert input '{choice_input}' to integer: {e}")
        notify_error_after_input(nvim, f"Invalid input '{choice_input}'. Selection cancelled.")
        return None