"""
End-to-end test for QuenchRunCell command without pre-starting kernel.

This test verifies that QuenchRunCell can properly trigger kernel selection
and initialize all components (kernel, web server, message relay) when called
on a buffer that isn't already connected to a kernel.

This test is designed to reproduce the "no switch() in NoneType" error
that occurs when QuenchRunCell is called without first running QuenchStartKernel.
"""

import asyncio
import pytest
import time
import re
from pathlib import Path
from .test_neovim_instance import TestNeovimInstance


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_quench_run_cell_auto_start():
    """
    Test QuenchRunCell command with automatic kernel startup.

    This test verifies that when QuenchRunCell is executed on a buffer
    without an active kernel connection:
    1. Kernel selection dialog appears and is handled
    2. Kernel session starts successfully
    3. Cell code is executed properly
    4. Web server starts and is accessible
    5. Message relay queue is initialized
    6. All components show as active in QuenchStatus
    7. No errors or warnings are present in logs

    This should reproduce the "no switch() in NoneType" error if present.
    """
    test_config_path = Path(__file__).parent / "test_nvim_config.lua"
    nvim_instance = TestNeovimInstance(config_file=str(test_config_path))

    try:
        # Step 1: Launch Neovim and load Quench plugin
        await nvim_instance.start(timeout=30)

        # Step 2: Create test buffer with Python cell
        test_content = [
            "# Test file for QuenchRunCell E2E test",
            "",
            "# %%",
            "print('Hello from QuenchRunCell test!')",
            "import sys",
            "print(f'Python version: {sys.version_info.major}.{sys.version_info.minor}')",
            "test_var = 'QuenchRunCell works!'",
            "print(test_var)",
            "",
            "# %%",
            "# Second cell for testing",
            "x = 42",
            "print(f'The answer is {x}')",
        ]

        test_file = await nvim_instance.create_test_buffer(test_content, "test_run_cell.py")

        # Step 3: Queue commands for execution
        print("Queueing commands for QuenchRunCell test...")

        # Position cursor at the first cell and execute QuenchRunCell
        # This should trigger kernel selection dialog automatically
        nvim_instance.add_command("normal! 3G")  # Go to line 3 (first # %%)
        nvim_instance.add_command('call feedkeys("1\\<CR>", "t")')  # Select first kernel option
        nvim_instance.add_command("QuenchRunCell")  # This should auto-start kernel selection
        nvim_instance.add_command("sleep 10")  # Allow time for kernel startup and execution
        nvim_instance.add_command("QuenchStatus")  # Check system status

        # Step 4: Execute all commands and wait for completion
        print("Executing all commands...")
        execution_result = await nvim_instance.wait_for_completion()
        print(f"Execution completed with result: {execution_result['success']}")

        # Step 5: Get and analyze QuenchStatus output
        status_messages = nvim_instance.get_new_messages()
        all_messages = nvim_instance.get_all_messages()

        # Look for QuenchStatus output in all messages
        status_output = "\n".join(status_messages)

        # If status_output is empty, try to find Quench Status in all messages
        if not status_output.strip():
            quench_lines = []
            in_status_section = False
            for msg in all_messages:
                if "quench status:" in msg.lower():
                    in_status_section = True
                    quench_lines.append(msg)
                elif in_status_section and (
                    "web server:" in msg.lower()
                    or "kernel sessions:" in msg.lower()
                    or "message relay:" in msg.lower()
                    or "active sessions:" in msg.lower()
                ):
                    # Status component lines - collect these
                    quench_lines.append(msg)
                elif in_status_section and msg.strip() and msg.strip().endswith(": buffers [], cache size: 0"):
                    # Session detail lines - collect these too
                    quench_lines.append(msg)
                elif (
                    in_status_section
                    and msg.strip()
                    and not any(
                        keyword in msg.lower()
                        for keyword in [
                            "web server:",
                            "kernel sessions:",
                            "message relay:",
                            "active sessions:",
                            ": buffers",
                        ]
                    )
                ):
                    # End of status section - found a non-status message
                    break

            if quench_lines:
                status_output = "\n".join(quench_lines)

        print(f"QuenchStatus output:\n{status_output}")
        print(f"All captured messages ({len(all_messages)}):")
        for i, msg in enumerate(all_messages[-25:], max(0, len(all_messages) - 25)):  # Show last 25 messages
            print(f"  {i}: {msg}")

        # Step 6: Analyze system components from status output
        system_analysis = analyze_quench_status(status_output)

        # Step 7: Run comprehensive error/warning checks
        error_check = nvim_instance.check_for_errors_and_warnings()

        # Step 8: Look for specific execution output to verify cell ran
        cell_executed = check_cell_execution(all_messages)

        # Step 9: Generate detailed test results
        test_results = {
            "kernel_active": system_analysis["kernel_active"],
            "server_running": system_analysis["server_running"],
            "relay_initialized": system_analysis["relay_initialized"],
            "cell_executed": cell_executed,
            "has_errors": error_check["has_errors"],
            "has_warnings": error_check["has_warnings"],
            "status_output": status_output,
            "error_summary": error_check["summary"],
            "log_content": nvim_instance.get_log_tail(),
            "all_messages": nvim_instance.get_all_messages(),
        }

        # Step 10: Report results and determine pass/fail
        print(f"\n=== QUENCH RUN CELL TEST RESULTS ===")
        print(f"Kernel Active: {test_results['kernel_active']}")
        print(f"Server Running: {test_results['server_running']}")
        print(f"Relay Initialized: {test_results['relay_initialized']}")
        print(f"Cell Executed: {test_results['cell_executed']}")
        print(f"Has Errors: {test_results['has_errors']}")
        print(f"Has Warnings: {test_results['has_warnings']}")
        print(f"Error Summary: {test_results['error_summary']}")

        # Check for the specific NoneType error we're trying to reproduce
        nonetype_error = check_for_nonetype_error(error_check, all_messages)
        if nonetype_error:
            print(f"\n🐛 REPRODUCED NONETYPE BUG: {nonetype_error}")

        # Primary success criteria: All components should be active and cell should execute
        components_ok = (
            test_results["kernel_active"] and test_results["server_running"] and test_results["relay_initialized"]
        )

        if test_results["has_errors"]:
            pytest.fail(
                f"""
❌ QUENCH RUN CELL TEST FAILED - ERRORS DETECTED

The QuenchRunCell command was executed but errors were found:

{test_results['error_summary']}

=== Component Status ===
Kernel Active: {test_results['kernel_active']}
Server Running: {test_results['server_running']}
Relay Initialized: {test_results['relay_initialized']}
Cell Executed: {test_results['cell_executed']}

=== QuenchStatus Output ===
{test_results['status_output']}

=== Error Details ===
Neovim Errors: {error_check['nvim_errors']}
Log Errors: {error_check['log_errors']}
Stderr Errors: {error_check['stderr_errors']}

=== Full Log Content ===
{test_results['log_content']}
"""
            )

        elif not components_ok:
            pytest.fail(
                f"""
🐛 COMPONENT STARTUP ISSUE DETECTED!

QuenchRunCell executed but not all system components started properly:

=== Component Status ===
Kernel Active: {test_results['kernel_active']} {'✅' if test_results['kernel_active'] else '❌'}
Server Running: {test_results['server_running']} {'✅' if test_results['server_running'] else '❌'}
Relay Initialized: {test_results['relay_initialized']} {'✅' if test_results['relay_initialized'] else '❌'}
Cell Executed: {test_results['cell_executed']} {'✅' if test_results['cell_executed'] else '❌'}

=== QuenchStatus Output ===
{test_results['status_output']}

=== Log Content ===
{test_results['log_content']}

=== All Neovim Messages ===
{chr(10).join(test_results['all_messages'])}
"""
            )

        elif not test_results["cell_executed"]:
            pytest.fail(
                f"""
❌ CELL EXECUTION FAILED!

QuenchRunCell command executed and components started, but the Python cell did not execute properly:

=== Component Status ===
Kernel Active: {test_results['kernel_active']} ✅
Server Running: {test_results['server_running']} ✅
Relay Initialized: {test_results['relay_initialized']} ✅
Cell Executed: {test_results['cell_executed']} ❌

=== QuenchStatus Output ===
{test_results['status_output']}

=== All Messages ===
{chr(10).join(test_results['all_messages'])}
"""
            )

        else:
            print(
                f"""
✅ QUENCH RUN CELL TEST PASSED

QuenchRunCell successfully triggered automatic kernel startup and executed the cell:
- Kernel session is active
- Web server is running
- Message relay is initialized
- Python cell executed successfully
- No errors detected

=== QuenchStatus Output ===
{test_results['status_output']}
"""
            )

    finally:
        # Cleanup
        await nvim_instance.cleanup()


def analyze_quench_status(status_output: str) -> dict:
    """
    Analyze QuenchStatus output to determine component states.

    Args:
        status_output: Raw output from QuenchStatus command

    Returns:
        Dictionary with component status booleans
    """
    analysis = {"kernel_active": False, "server_running": False, "relay_initialized": False}

    if not status_output or not status_output.strip():
        return analysis

    status_lower = status_output.lower()

    # Look for patterns matching the actual QuenchStatus output format:
    # Quench Status:
    #   Web Server: running (http://127.0.0.1:8766)
    #   Kernel Sessions: 1 active
    #   Message Relay: running

    # Check for active kernel sessions - look for "kernel sessions: X active" where X > 0
    kernel_match = re.search(r"kernel sessions:\s*(\d+)\s*active", status_lower)
    if kernel_match:
        session_count = int(kernel_match.group(1))
        analysis["kernel_active"] = session_count > 0

    # Check for running web server - look for "web server: running"
    if re.search(r"web server:\s*running", status_lower):
        analysis["server_running"] = True

    # Check for message relay - look for "message relay: running"
    if re.search(r"message relay:\s*running", status_lower):
        analysis["relay_initialized"] = True

    return analysis


def check_cell_execution(all_messages: list) -> bool:
    """
    Check if the Python cell actually executed by looking for expected output.

    Args:
        all_messages: List of all captured messages from Neovim

    Returns:
        True if cell execution evidence found, False otherwise
    """
    # Look for the specific output we expect from our test cell
    expected_outputs = ["Hello from QuenchRunCell test!", "Python version:", "QuenchRunCell works!"]

    # Check both the messages and also get the log content to search there too
    messages_text = " ".join(all_messages).lower()

    # Also check the Quench logs since that's where cell output is typically logged
    log_file_path = "/tmp/quench.log"
    log_content = ""
    try:
        with open(log_file_path, "r") as f:
            log_content = f.read().lower()
    except:
        pass  # Log file might not exist

    combined_text = messages_text + " " + log_content

    # Check if we can find evidence of cell execution
    found_outputs = 0
    for expected in expected_outputs:
        if expected.lower() in combined_text:
            found_outputs += 1
            print(f"Found expected output: {expected}")

    print(f"Cell execution check: found {found_outputs}/3 expected outputs")
    # All three outputs must be found for proper cell execution
    return found_outputs == 3


def check_for_nonetype_error(error_check: dict, all_messages: list) -> str:
    """
    Check specifically for the "no switch() in NoneType" error we're trying to reproduce.

    Args:
        error_check: Error check results from TestNeovimInstance
        all_messages: All captured messages

    Returns:
        Error message if NoneType error found, empty string otherwise
    """
    # Check all error sources for NoneType-related errors
    all_error_text = " ".join(
        [
            " ".join(error_check["nvim_errors"]),
            " ".join(error_check["log_errors"]),
            " ".join(error_check["stderr_errors"]),
            " ".join(all_messages),
        ]
    ).lower()

    # Look for various forms of the NoneType error
    nonetype_patterns = [
        "no switch() in nonetype",
        "nonetype.*switch",
        "attributeerror.*nonetype.*switch",
        "switch.*nonetype",
    ]

    for pattern in nonetype_patterns:
        if re.search(pattern, all_error_text):
            return f"Found NoneType error matching pattern: {pattern}"

    return ""


if __name__ == "__main__":
    # Allow running directly for debugging
    asyncio.run(test_quench_run_cell_auto_start())
