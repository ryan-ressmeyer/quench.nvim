"""
E2E test for QuenchStop command functionality.

This test verifies the complete QuenchStop workflow:
1. QuenchStartKernel - creates kernel and starts components
2. QuenchStop - stops all components
3. QuenchStatus - verifies clean shutdown

The test passes if QuenchStatus reports no running kernels and no errors.
"""

import asyncio
import pytest
import time
from pathlib import Path
from .test_neovim_instance import TestNeovimInstance


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_quench_stop():
    """
    Test the QuenchStop command functionality.

    Test workflow:
    1. QuenchStartKernel - Start kernel and all components
    2. QuenchStop - Stop all components
    3. QuenchStatus - Verify clean shutdown

    Test passes if:
    - No errors occur during the sequence
    - QuenchStatus reports no active kernels
    - All components are properly shut down
    """
    test_config_path = Path(__file__).parent / "test_nvim_config.lua"
    nvim_instance = TestNeovimInstance(config_file=str(test_config_path))

    try:
        # Step 1: Launch Neovim and load Quench plugin
        await nvim_instance.start(timeout=30)
        print("✅ Neovim started and Quench plugin loaded")

        # Step 2: Create test buffer with Python cells
        test_content = [
            "# %%",
            "print('Test cell for QuenchStop functionality')",
            "import sys",
            "print(f'Python version: {sys.version_info}')",
            "",
            "# %%",
            "x = 123",
            "print(f'Value of x: {x}')",
        ]

        test_file = await nvim_instance.create_test_buffer(test_content, "test_quench_stop.py")
        print("✅ Test buffer created with Python cells")

        # Step 3: Start kernel and components (QuenchStartKernel)
        print("🚀 Starting kernel and components with QuenchStartKernel...")
        nvim_instance.add_command('call feedkeys("1\\<CR>", "t")')  # Select kernel option 1
        nvim_instance.add_command("QuenchStartKernel")
        nvim_instance.add_command("sleep 8")  # Allow time for full startup

        # Get initial status to confirm startup
        nvim_instance.add_command("QuenchStatus")

        # Execute startup sequence
        startup_result = await nvim_instance.wait_for_completion()
        print(f"Startup sequence result: {startup_result['success']}")

        # Analyze startup status
        startup_messages = nvim_instance.get_new_messages()
        all_messages = nvim_instance.get_all_messages()
        startup_status = "\n".join(startup_messages)

        print(f"Startup QuenchStatus output:\n{startup_status}")
        print(f"All startup messages ({len(all_messages)}):")
        for i, msg in enumerate(all_messages):
            print(f"  {i}: {msg}")

        # Try to find QuenchStatus output in all messages if not found in new messages
        if not startup_status.strip():
            print("No startup status found in new messages, checking all messages...")
            quench_lines = []
            in_status_section = False
            for msg in all_messages:
                if "quench status:" in msg.lower():
                    in_status_section = True
                    quench_lines.append(msg)
                elif in_status_section and (
                    "web server:" in msg.lower() or "kernel sessions:" in msg.lower() or "message relay:" in msg.lower()
                ):
                    quench_lines.append(msg)
                elif (
                    in_status_section
                    and msg.strip()
                    and not any(
                        keyword in msg.lower() for keyword in ["web server:", "kernel sessions:", "message relay:"]
                    )
                ):
                    # End of status section
                    break

            if quench_lines:
                startup_status = "\n".join(quench_lines)
                print(f"Found QuenchStatus in all messages:\n{startup_status}")

        startup_analysis = analyze_quench_status(startup_status)
        print(f"Startup analysis: {startup_analysis}")

        if not all(startup_analysis.values()):
            # Don't fail immediately - let's see if components started but QuenchStatus parsing failed
            print(f"⚠️  Components may not have started properly: {startup_analysis}")
            print("Continuing test to see if QuenchStop works anyway...")
        else:
            print("✅ All components started successfully")

        # Step 4: Stop all components (QuenchStop)
        print("🛑 Stopping all components with QuenchStop...")
        nvim_instance.add_command("QuenchStop")
        nvim_instance.add_command("sleep 3")  # Allow time for shutdown

        # Execute stop command
        stop_result = await nvim_instance.wait_for_completion()
        print(f"Stop command result: {stop_result['success']}")

        # Step 5: Check status after stop (QuenchStatus) - this is where the bug occurs
        print("📊 Checking status after stop with QuenchStatus...")
        nvim_instance.add_command("QuenchStatus")

        # Execute final status check
        final_result = await nvim_instance.wait_for_completion()
        print(f"Final status check result: {final_result['success']}")

        # Step 6: Analyze results
        final_messages = nvim_instance.get_new_messages()
        all_messages = nvim_instance.get_all_messages()
        final_status_output = "\n".join(final_messages)

        print(f"Final QuenchStatus output:\n{final_status_output}")
        print(f"All messages captured ({len(all_messages)}):")
        for i, msg in enumerate(all_messages[-15:], max(0, len(all_messages) - 15)):  # Show last 15 messages
            print(f"  {i}: {msg}")

        # Check for errors during the sequence
        error_check = nvim_instance.check_for_errors_and_warnings()

        # Analyze final status
        final_analysis = analyze_quench_status(final_status_output)

        # Generate test results
        test_results = {
            "stop_command_success": stop_result["success"],
            "status_command_success": final_result["success"],
            "final_kernel_active": final_analysis["kernel_active"],
            "final_server_running": final_analysis["server_running"],
            "final_relay_initialized": final_analysis["relay_initialized"],
            "has_errors": error_check["has_errors"],
            "has_warnings": error_check["has_warnings"],
            "error_summary": error_check["summary"],
            "final_status_output": final_status_output,
            "log_content": nvim_instance.get_log_tail(),
        }

        # Step 7: Report results
        print(f"\n=== QUENCH STOP TEST RESULTS ===")
        print(f"Stop Command Success: {test_results['stop_command_success']}")
        print(f"Status Command Success: {test_results['status_command_success']}")
        print(f"Final Kernel Active: {test_results['final_kernel_active']}")
        print(f"Final Server Running: {test_results['final_server_running']}")
        print(f"Final Relay Initialized: {test_results['final_relay_initialized']}")
        print(f"Has Errors: {test_results['has_errors']}")
        print(f"Has Warnings: {test_results['has_warnings']}")
        print(f"Error Summary: {test_results['error_summary']}")

        # Check if QuenchStatus failed after QuenchStop
        if not test_results["status_command_success"]:
            pytest.fail(
                f"""
❌ QUENCH STATUS FAILED after QuenchStop

QuenchStatus command failed after running QuenchStop.

=== Test Results ===
Stop Command Success: {test_results['stop_command_success']}
Status Command Success: {test_results['status_command_success']} ❌

=== Error Details ===
{test_results['error_summary']}

=== Final QuenchStatus Output ===
{test_results['final_status_output']}

=== Log Content ===
{test_results['log_content']}
            """
            )

        # Check for any errors during execution
        if test_results["has_errors"]:
            pytest.fail(
                f"""
❌ ERRORS DETECTED during QuenchStop sequence

=== Error Summary ===
{test_results['error_summary']}

=== Final Status ===
Kernel Active: {test_results['final_kernel_active']}
Server Running: {test_results['final_server_running']}
Relay Initialized: {test_results['final_relay_initialized']}

=== QuenchStatus Output ===
{test_results['final_status_output']}

=== Log Content ===
{test_results['log_content']}
            """
            )

        # Success criteria: All components should be stopped and no errors
        components_stopped = (
            not test_results["final_kernel_active"]
            and not test_results["final_server_running"]
            and not test_results["final_relay_initialized"]
        )

        if not components_stopped:
            pytest.fail(
                f"""
❌ COMPONENTS NOT PROPERLY STOPPED

QuenchStop executed without errors, but components are still running:

=== Component Status After Stop ===
Kernel Active: {test_results['final_kernel_active']} {'❌' if test_results['final_kernel_active'] else '✅'}
Server Running: {test_results['final_server_running']} {'❌' if test_results['final_server_running'] else '✅'}
Relay Initialized: {test_results['final_relay_initialized']} {'❌' if test_results['final_relay_initialized'] else '✅'}

=== QuenchStatus Output ===
{test_results['final_status_output']}
            """
            )

        else:
            print(
                f"""
✅ QUENCH STOP TEST PASSED

All components were properly stopped and QuenchStatus executed without errors:

=== Final Component Status ===
- Kernel sessions: Stopped ✅
- Web server: Stopped ✅
- Message relay: Stopped ✅
- No errors detected ✅

=== Final QuenchStatus Output ===
{test_results['final_status_output']}
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
    import re

    analysis = {"kernel_active": False, "server_running": False, "relay_initialized": False}

    if not status_output or not status_output.strip():
        return analysis

    status_lower = status_output.lower()

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
    asyncio.run(test_quench_stop())
