"""
Comprehensive E2E test for QuenchStartKernel command with server verification.

This test is designed to catch the server startup issue where the web server
and message relay don't start when a kernel is initialized for the first time.
"""

import asyncio
import pytest
import time
import re
from pathlib import Path
from .test_neovim_instance import TestNeovimInstance


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_kernel_startup_complete():
    """
    Test complete system startup when executing QuenchStartKernel.

    This test verifies that when QuenchStartKernel is executed:
    1. Kernel session starts successfully
    2. Web server starts and is accessible
    3. Message relay queue is initialized
    4. All components show as active in QuenchStatus
    5. No errors or warnings are present in logs

    This should catch the issue where server/relay don't start with first kernel.
    """
    test_config_path = Path(__file__).parent / "test_nvim_config.lua"
    nvim_instance = TestNeovimInstance(config_file=str(test_config_path))

    try:
        # Step 1: Launch Neovim and load Quench plugin
        await nvim_instance.start(timeout=30)

        # Step 2: Create test buffer with Python cells
        test_content = [
            "# %%",
            "print('Hello from test cell')",
            "import sys",
            "print(f'Python version: {sys.version_info}')",
            "",
            "# %%",
            "x = 42",
            "print(f'Value of x: {x}')",
        ]

        test_file = await nvim_instance.create_test_buffer(test_content, "test_kernel_start.py")

        # Step 3: Queue commands for execution
        print("Queueing commands for execution...")

        # Queue input first, then execute command
        nvim_instance.add_command('call feedkeys("1\\<CR>", "t")')  # Just "t" flag to queue input
        nvim_instance.add_command("QuenchStartKernel")
        nvim_instance.add_command("sleep 8")  # Allow time for kernel startup and server initialization
        nvim_instance.add_command("QuenchStatus")

        # Step 4: Execute all commands and wait for completion
        print("Executing all commands...")
        execution_result = await nvim_instance.wait_for_completion()
        print(f"Execution completed with result: {execution_result['success']}")

        # Step 5: Get and analyze QuenchStatus output
        # Try multiple sources for QuenchStatus output
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
        for i, msg in enumerate(all_messages[-20:], max(0, len(all_messages) - 20)):  # Show last 20 messages
            print(f"  {i}: {msg}")

        # Step 6: Analyze system components from status output
        system_analysis = analyze_quench_status(status_output)

        # Step 7: Run comprehensive error/warning checks
        error_check = nvim_instance.check_for_errors_and_warnings()

        # Step 8: Generate detailed test results
        test_results = {
            "kernel_active": system_analysis["kernel_active"],
            "server_running": system_analysis["server_running"],
            "relay_initialized": system_analysis["relay_initialized"],
            "has_errors": error_check["has_errors"],
            "has_warnings": error_check["has_warnings"],
            "status_output": status_output,
            "error_summary": error_check["summary"],
            "log_content": nvim_instance.get_log_tail(),
            "all_messages": nvim_instance.get_all_messages(),
        }

        # Step 9: Report results and determine pass/fail
        print(f"\n=== COMPLETE SYSTEM STARTUP TEST RESULTS ===")
        print(f"Kernel Active: {test_results['kernel_active']}")
        print(f"Server Running: {test_results['server_running']}")
        print(f"Relay Initialized: {test_results['relay_initialized']}")
        print(f"Has Errors: {test_results['has_errors']}")
        print(f"Has Warnings: {test_results['has_warnings']}")
        print(f"Error Summary: {test_results['error_summary']}")

        # Primary success criteria: All components should be active
        components_ok = (
            test_results["kernel_active"] and test_results["server_running"] and test_results["relay_initialized"]
        )

        if test_results["has_errors"]:
            pytest.fail(
                f"""
❌ KERNEL STARTUP TEST FAILED - ERRORS DETECTED

The QuenchStartKernel command completed but errors were found:

{test_results['error_summary']}

=== Component Status ===
Kernel Active: {test_results['kernel_active']}
Server Running: {test_results['server_running']}
Relay Initialized: {test_results['relay_initialized']}

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
            # This is the main issue we're trying to catch
            pytest.fail(
                f"""
🐛 SERVER STARTUP ISSUE DETECTED!

QuenchStartKernel executed without errors, but not all system components started:

=== Component Status ===
Kernel Active: {test_results['kernel_active']} {'✅' if test_results['kernel_active'] else '❌'}
Server Running: {test_results['server_running']} {'✅' if test_results['server_running'] else '❌'}
Relay Initialized: {test_results['relay_initialized']} {'✅' if test_results['relay_initialized'] else '❌'}

This matches the reported issue: "web server and message relay are not starting
when a kernel is started for the first time."

=== QuenchStatus Output ===
{test_results['status_output']}

=== Log Content ===
{test_results['log_content']}

=== All Neovim Messages ===
{chr(10).join(test_results['all_messages'])}
"""
            )

        else:
            print(
                f"""
✅ COMPLETE SYSTEM STARTUP TEST PASSED

All components started successfully:
- Kernel session is active
- Web server is running
- Message relay is initialized
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
    #   Web Server: running (http://127.0.0.1:8765)
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


if __name__ == "__main__":
    # Allow running directly for debugging
    asyncio.run(test_kernel_startup_complete())
