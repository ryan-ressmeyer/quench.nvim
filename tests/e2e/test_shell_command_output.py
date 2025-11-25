"""
End-to-end test for IPython shell commands (! prefixed).

This test verifies that shell commands executed with the ! prefix
properly display their output in the Quench frontend. This reproduces
a bug where CRLF line endings from PTY output are incorrectly handled
by the \r overwrite logic, causing shell command output to disappear.
"""

import asyncio
import pytest
import time
from pathlib import Path
from .test_neovim_instance import TestNeovimInstance


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_shell_command_output():
    """
    Test that shell commands (! prefixed) show their output correctly.

    This test verifies that when a cell contains shell commands like:
        ! echo "Hello"

    The output "Hello" is properly displayed in the frontend and not
    erased by the carriage return handling logic.

    Bug: Shell commands output \r\n (CRLF) which triggers the \r overwrite
    logic in handleStream, causing the actual output to be deleted.
    """
    test_config_path = Path(__file__).parent / "test_nvim_config.lua"
    nvim_instance = TestNeovimInstance(config_file=str(test_config_path))

    try:
        # Step 1: Launch Neovim and load Quench plugin
        await nvim_instance.start(timeout=30)

        # Step 2: Create test buffer with shell command cell
        test_content = [
            "# Test file for shell command output",
            "",
            "# %%",
            '! echo "Hello from shell"',
        ]

        test_file = await nvim_instance.create_test_buffer(test_content, "test_shell_commands.py")

        # Step 3: Queue commands for execution
        print("Queueing commands for shell command test...")

        # Position cursor at the first cell and execute
        nvim_instance.add_command("normal! 3G")  # Go to line 3 (first # %%)
        nvim_instance.add_command('call feedkeys("1\\<CR>", "t")')  # Select first kernel
        nvim_instance.add_command("QuenchRunCell")  # Execute first cell
        nvim_instance.add_command("sleep 8")  # Allow time for execution
        nvim_instance.add_command("QuenchStatus")  # Check system status

        # Step 4: Execute all commands and wait for completion
        print("Executing all commands...")
        execution_result = await nvim_instance.wait_for_completion()
        print(f"Execution completed with result: {execution_result['success']}")

        # Step 5: Check the Quench log for shell command output
        log_content = nvim_instance.get_log_tail()
        all_messages = nvim_instance.get_all_messages()

        # Step 6: Verify shell command outputs are present
        test_results = check_shell_outputs(log_content, all_messages)

        # Step 7: Report results
        print(f"\n=== SHELL COMMAND OUTPUT TEST RESULTS ===")
        print(f"Found 'Hello from shell': {test_results['found_hello']}")

        # Determine pass/fail
        all_found = test_results["found_hello"]

        if not all_found:
            # Print diagnostic information
            print("\n=== DIAGNOSTIC INFO ===")
            print("Log content (last 50 lines):")
            log_lines = log_content.split("\n")
            for line in log_lines[-50:]:
                print(f"  {line}")

            pytest.fail(
                f"""
❌ SHELL COMMAND OUTPUT TEST FAILED

Shell command output 'Hello from shell' was not found in the Quench logs or messages.
This indicates the bug where CRLF line endings cause output to disappear.

=== Log Tail ===
{log_content[-1000:] if log_content else '(empty)'}

=== All Messages ===
{chr(10).join(all_messages[-20:]) if all_messages else '(empty)'}
"""
            )

        else:
            print(
                f"""
✅ SHELL COMMAND OUTPUT TEST PASSED

Shell command output 'Hello from shell' was found successfully!
"""
            )

    finally:
        # Cleanup
        await nvim_instance.cleanup()


def check_shell_outputs(log_content: str, all_messages: list) -> dict:
    """
    Check if shell command output is present in logs or messages.

    Args:
        log_content: Content from Quench log file
        all_messages: All captured messages from Neovim

    Returns:
        Dictionary with boolean flag for expected output
    """
    combined_text = log_content + " " + " ".join(all_messages)

    results = {
        "found_hello": "Hello from shell" in combined_text,
    }

    return results


if __name__ == "__main__":
    # Allow running directly for debugging
    asyncio.run(test_shell_command_output())
