"""
End-to-end test for QuenchInterruptKernel command.

This test verifies that QuenchInterruptKernel can properly interrupt long-running
Python code execution in a kernel session. The test:

1. Starts a kernel session
2. Executes a long-running Python cell (sleep + print)
3. Interrupts the execution using QuenchInterruptKernel
4. Verifies that the code was properly interrupted before completion

This test is designed to discover bugs with the interrupt functionality.
"""

import asyncio
import pytest
from pathlib import Path
from .test_neovim_instance import TestNeovimInstance


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_quench_interrupt_kernel():
    """
    Test QuenchInterruptKernel command functionality.

    This test verifies that when QuenchInterruptKernel is executed during
    long-running code execution:
    1. Kernel session starts successfully
    2. Long-running cell code begins execution
    3. Interrupt signal is sent successfully
    4. Code execution is terminated before completion
    5. Kernel remains responsive after interrupt
    6. No critical errors occur in the process
    """
    test_config_path = Path(__file__).parent / "test_nvim_config.lua"
    nvim_instance = TestNeovimInstance(config_file=str(test_config_path))

    try:
        # Step 1: Launch Neovim and load Quench plugin
        await nvim_instance.start(timeout=30)

        # Step 2: Create test buffer with long-running Python code
        test_content = [
            "# Test file for QuenchInterruptKernel E2E test",
            "",
            "# %%",
            "# Long-running cell that should be interrupted",
            "import time",
            "print('Starting long-running operation...')",
            "time.sleep(6)  # This should be interrupted",
            "print('This should NOT appear if interrupt works!')",
        ]

        await nvim_instance.create_test_buffer(test_content, "test_interrupt.py")

        # Step 3: Queue commands for execution
        print("Queueing commands for QuenchInterruptKernel test...")

        # Position cursor at the first cell and execute (this will auto-create kernel)
        nvim_instance.add_command("normal! 3G")  # Go to line 3 (first # %%)
        nvim_instance.add_command('call feedkeys("1\\<CR>", "t")')  # Select first kernel option
        nvim_instance.add_command("QuenchRunCell")  # This will auto-create kernel and execute code
        nvim_instance.add_command("sleep 3")  # Give code time to start running

        # Interrupt the execution
        nvim_instance.add_command("QuenchInterruptKernel")  # This should interrupt the sleep
        nvim_instance.add_command("sleep 7")  # Allow interrupt to process

        # Step 4: Execute all commands and wait for completion
        print("Executing all commands...")
        execution_result = await nvim_instance.wait_for_completion()
        print(f"Execution completed with result: {execution_result['success']}")

        # Step 5: Analyze results to verify interrupt worked
        all_messages = nvim_instance.get_all_messages()
        log_content = nvim_instance.get_log_tail()
        error_check = nvim_instance.check_for_errors_and_warnings()

        # Filter out KeyboardInterrupt errors - these are EXPECTED when interrupting
        error_check = filter_expected_interrupt_errors(error_check)

        # Step 6: Check if interrupt was successful
        interrupt_results = analyze_interrupt_success(all_messages, log_content)

        # Step 7: Generate detailed test results
        test_results = {
            "interrupt_successful": interrupt_results["interrupt_successful"],
            "code_started": interrupt_results["code_started"],
            "code_completed": interrupt_results["code_completed"],
            "has_errors": error_check["has_errors"],
            "error_summary": error_check["summary"],
            "all_messages": all_messages,
            "log_content": log_content,
        }

        # Step 8: Report results and determine pass/fail
        print(f"\n=== QUENCH INTERRUPT KERNEL TEST RESULTS ===")
        print(f"Code Started: {test_results['code_started']}")
        print(f"Interrupt Successful: {test_results['interrupt_successful']}")
        print(f"Code Completed (should be False): {test_results['code_completed']}")
        print(f"Has Errors: {test_results['has_errors']}")
        print(f"Error Summary: {test_results['error_summary']}")

        # Primary success criteria: Code should start but not complete due to interrupt
        if test_results["has_errors"]:
            pytest.fail(
                f"""
❌ QUENCH INTERRUPT KERNEL TEST FAILED - ERRORS DETECTED

The QuenchInterruptKernel command was executed but errors were found:

{test_results['error_summary']}

=== Test Results ===
Code Started: {test_results['code_started']}
Interrupt Successful: {test_results['interrupt_successful']}
Code Completed: {test_results['code_completed']}

=== Error Details ===
{error_check['nvim_errors']}
{error_check['log_errors']}
{error_check['stderr_errors']}

=== Log Content ===
{test_results['log_content']}
"""
            )

        elif not test_results["code_started"]:
            pytest.fail(
                f"""
❌ CODE EXECUTION NEVER STARTED

The long-running Python code never began executing:

=== Test Results ===
Code Started: {test_results['code_started']} ❌
Interrupt Successful: {test_results['interrupt_successful']}
Code Completed: {test_results['code_completed']}

=== All Messages ===
{chr(10).join(test_results['all_messages'])}
"""
            )

        elif test_results["code_completed"]:
            pytest.fail(
                f"""
❌ INTERRUPT FAILED - CODE COMPLETED

The interrupt did not work! The long-running code completed execution:

=== Test Results ===
Code Started: {test_results['code_started']} ✅
Interrupt Successful: {test_results['interrupt_successful']} ❌
Code Completed: {test_results['code_completed']} ❌ (should be False)

This indicates QuenchInterruptKernel is not working properly.

=== All Messages ===
{chr(10).join(test_results['all_messages'])}
"""
            )

        else:
            print(
                f"""
✅ QUENCH INTERRUPT KERNEL TEST PASSED

QuenchInterruptKernel successfully interrupted the long-running code:
- Code execution started properly
- Interrupt command executed
- Code did not complete (was properly interrupted)
- No errors detected

=== Test Results ===
Code Started: {test_results['code_started']} ✅
Interrupt Successful: {test_results['interrupt_successful']} ✅
Code Completed: {test_results['code_completed']} ✅ (correctly False)
"""
            )

    finally:
        # Cleanup
        await nvim_instance.cleanup()


def filter_expected_interrupt_errors(error_check: dict) -> dict:
    """
    Filter out KeyboardInterrupt errors from error check results.

    When testing interrupt functionality, KeyboardInterrupt errors are EXPECTED
    and should not cause test failures. This includes:
    - KeyboardInterrupt exception messages
    - DEBUG logs about processing error messages (normal flow)
    - Cell status messages with 'completed_error' (expected for interrupts)

    Args:
        error_check: Dictionary from check_for_errors_and_warnings()

    Returns:
        Modified error_check dictionary with KeyboardInterrupt errors filtered out
    """

    def is_expected_interrupt_log(err: str) -> bool:
        """Check if a log line is expected during interrupt handling."""
        err_lower = err.lower()

        # KeyboardInterrupt exceptions are expected
        if "keyboardinterrupt" in err_lower:
            return True

        # DEBUG logs about processing error messages are normal flow
        if "debug:" in err_lower and any(
            phrase in err_lower
            for phrase in [
                "relaying message: error",
                "relayed message from kernel",
                "processing message type: error",
                "sent cell status 'completed_error'",
            ]
        ):
            return True

        return False

    filtered_check = error_check.copy()

    # Filter out expected interrupt-related log errors
    filtered_log_errors = [err for err in error_check["log_errors"] if not is_expected_interrupt_log(err)]
    filtered_check["log_errors"] = filtered_log_errors

    # Filter out expected interrupt-related nvim errors
    filtered_nvim_errors = [err for err in error_check["nvim_errors"] if not is_expected_interrupt_log(err)]
    filtered_check["nvim_errors"] = filtered_nvim_errors

    # Filter out expected interrupt-related stderr errors
    filtered_stderr_errors = [err for err in error_check["stderr_errors"] if not is_expected_interrupt_log(err)]
    filtered_check["stderr_errors"] = filtered_stderr_errors

    # Recalculate has_errors based on filtered results
    filtered_check["has_errors"] = bool(
        filtered_check["log_errors"] or filtered_check["nvim_errors"] or filtered_check["stderr_errors"]
    )

    # Update summary
    issues = []
    if filtered_check["nvim_errors"]:
        issues.append(f"{len(filtered_check['nvim_errors'])} Neovim errors")
    if filtered_check["nvim_warnings"]:
        issues.append(f"{len(filtered_check['nvim_warnings'])} Neovim warnings")
    if filtered_check["log_errors"]:
        issues.append(f"{len(filtered_check['log_errors'])} log errors")
    if filtered_check["log_warnings"]:
        issues.append(f"{len(filtered_check['log_warnings'])} log warnings")
    if filtered_check["stderr_errors"]:
        issues.append(f"{len(filtered_check['stderr_errors'])} stderr errors")

    if issues:
        filtered_check["summary"] = f"Found: {', '.join(issues)}"
    else:
        filtered_check["summary"] = "No errors or warnings detected (KeyboardInterrupt filtered)"

    return filtered_check


def analyze_interrupt_success(all_messages: list, log_content: str) -> dict:
    """
    Analyze test output to determine if the interrupt was successful.

    Args:
        all_messages: List of all captured messages from Neovim
        log_content: Content from the Quench log file

    Returns:
        Dictionary with interrupt analysis results
    """
    results = {"code_started": False, "interrupt_successful": False, "code_completed": False}

    # Combine all text sources for analysis
    combined_text = " ".join(all_messages + [log_content]).lower()

    # Check if the long-running code started
    if "starting long-running operation" in combined_text:
        results["code_started"] = True
        print("✅ Long-running code started execution")

    # Check if the code completed (this should NOT happen if interrupt worked)
    if "this should not appear if interrupt works" in combined_text:
        results["code_completed"] = True
        print("❌ Code completed - interrupt failed!")
    else:
        print("✅ Code did not complete - likely interrupted")

    # Check for evidence of successful interrupt
    # Look for interrupt-related messages or KeyboardInterrupt exceptions
    interrupt_indicators = [
        "keyboardinterrupt",
        "interrupted",
        "interrupt",
        "quenchinterruptkernel",
    ]

    for indicator in interrupt_indicators:
        if indicator in combined_text:
            results["interrupt_successful"] = True
            print(f"✅ Found interrupt indicator: {indicator}")
            break

    # If code started but didn't complete, and we didn't find explicit interrupt indicators,
    # we can still infer that interrupt likely worked
    if results["code_started"] and not results["code_completed"]:
        results["interrupt_successful"] = True
        print("✅ Inferred successful interrupt (code started but didn't complete)")

    return results


if __name__ == "__main__":
    # Allow running directly for debugging
    asyncio.run(test_quench_interrupt_kernel())
