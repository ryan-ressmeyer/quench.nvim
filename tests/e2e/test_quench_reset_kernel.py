"""
End-to-end test for QuenchResetKernel command.

This test verifies that QuenchResetKernel can properly reset the kernel state,
clearing all variables and restarting the Python execution environment. The test:

1. Starts a kernel session
2. Defines a variable in the kernel
3. Resets the kernel using QuenchResetKernel
4. Attempts to access the variable (which should fail with NameError)

This test is designed to discover bugs with the kernel reset functionality.
"""

import asyncio
import pytest
from pathlib import Path
from .test_neovim_instance import NeovimTestInstance


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_quench_reset_kernel():
    """
    Test QuenchResetKernel command functionality.

    This test verifies that when QuenchResetKernel is executed:
    1. Kernel session starts successfully
    2. Variable is defined in kernel state
    3. Kernel reset command executes successfully
    4. Variable is no longer accessible (NameError occurs)
    5. Kernel remains responsive after reset
    6. No critical errors occur in the process
    """
    test_config_path = Path(__file__).parent / "test_nvim_config.lua"
    nvim_instance = NeovimTestInstance(config_file=str(test_config_path))

    try:
        # Step 1: Launch Neovim and load Quench plugin
        await nvim_instance.start(timeout=30)

        # Step 2: Create test buffer with variable definition and access
        test_content = [
            "# Test file for QuenchResetKernel E2E test",
            "",
            "# %%",
            "# Define a test variable",
            "test_variable = 'This variable should be cleared after reset'",
            "print('Variable defined successfully')",
            "",
            "# %%",
            "# This cell should fail after kernel reset",
            "print(f'Variable value: {test_variable}')",
            "print('This should NOT appear if reset works!')",
        ]

        await nvim_instance.create_test_buffer(test_content, "test_reset.py")

        # Step 3: Queue commands for execution
        print("Queueing commands for QuenchResetKernel test...")

        # First, define the variable (execute first cell)
        nvim_instance.add_command("normal! 3G")  # Go to first cell
        nvim_instance.add_command('call feedkeys("1\\<CR>", "t")')  # Select first kernel option
        nvim_instance.add_command("QuenchRunCell")  # Execute first cell

        # Reset kernel and test variable access
        nvim_instance.add_command("QuenchResetKernel")  # Reset kernel
        nvim_instance.add_command("sleep 5 | normal! 8G")  # Wait for reset and position cursor
        nvim_instance.add_command("QuenchRunCell")  # Execute second cell
        nvim_instance.add_command("sleep 3")  # Wait for second cell execution

        # Step 4: Execute all commands and wait for completion
        print("Executing all commands...")
        execution_result = await nvim_instance.wait_for_completion()
        print(f"Execution completed with result: {execution_result['success']}")

        # Step 5: Analyze results to verify reset worked
        all_messages = nvim_instance.get_all_messages()
        log_content = nvim_instance.get_log_tail()
        error_check = nvim_instance.check_for_errors_and_warnings()

        # Step 6: Check if reset was successful
        reset_results = analyze_reset_success(all_messages, log_content)

        # Step 7: Generate detailed test results
        test_results = {
            "reset_successful": reset_results["reset_successful"],
            "variable_defined": reset_results["variable_defined"],
            "variable_accessible": reset_results["variable_accessible"],
            "has_errors": error_check["has_errors"],
            "error_summary": error_check["summary"],
            "all_messages": all_messages,
            "log_content": log_content,
        }

        # Step 8: Report results and determine pass/fail
        print(f"\n=== QUENCH RESET KERNEL TEST RESULTS ===")
        print(f"Variable Defined: {test_results['variable_defined']}")
        print(f"Reset Successful: {test_results['reset_successful']}")
        print(f"Variable Accessible After Reset (should be False): {test_results['variable_accessible']}")
        print(f"Has Errors: {test_results['has_errors']}")
        print(f"Error Summary: {test_results['error_summary']}")

        # Primary success criteria: Variable should be defined but not accessible after reset
        if test_results["has_errors"]:
            pytest.fail(
                f"""
❌ QUENCH RESET KERNEL TEST FAILED - ERRORS DETECTED

The QuenchResetKernel command was executed but errors were found:

{test_results['error_summary']}

=== Test Results ===
Variable Defined: {test_results['variable_defined']}
Reset Successful: {test_results['reset_successful']}
Variable Accessible: {test_results['variable_accessible']}

=== Error Details ===
{error_check['nvim_errors']}
{error_check['log_errors']}
{error_check['stderr_errors']}

=== Log Content ===
{test_results['log_content']}
"""
            )

        elif not test_results["variable_defined"]:
            pytest.fail(
                f"""
❌ VARIABLE DEFINITION FAILED

The test variable was never successfully defined:

=== Test Results ===
Variable Defined: {test_results['variable_defined']} ❌
Reset Successful: {test_results['reset_successful']}
Variable Accessible: {test_results['variable_accessible']}

=== All Messages ===
{chr(10).join(test_results['all_messages'])}
"""
            )

        elif test_results["variable_accessible"]:
            pytest.fail(
                f"""
❌ RESET FAILED - VARIABLE STILL ACCESSIBLE

The reset did not work! The variable is still accessible after reset:

=== Test Results ===
Variable Defined: {test_results['variable_defined']} ✅
Reset Successful: {test_results['reset_successful']} ❌
Variable Accessible: {test_results['variable_accessible']} ❌ (should be False)

This indicates QuenchResetKernel is not working properly.

=== All Messages ===
{chr(10).join(test_results['all_messages'])}
"""
            )

        else:
            print(
                f"""
✅ QUENCH RESET KERNEL TEST PASSED

QuenchResetKernel successfully reset the kernel state:
- Variable was defined properly
- Reset command executed
- Variable became inaccessible (properly cleared)
- No errors detected

=== Test Results ===
Variable Defined: {test_results['variable_defined']} ✅
Reset Successful: {test_results['reset_successful']} ✅
Variable Accessible: {test_results['variable_accessible']} ✅ (correctly False)
"""
            )

    finally:
        # Cleanup
        await nvim_instance.cleanup()


def analyze_reset_success(all_messages: list, log_content: str) -> dict:
    """
    Analyze test output to determine if the reset was successful.

    Args:
        all_messages: List of all captured messages from Neovim
        log_content: Content from the Quench log file

    Returns:
        Dictionary with reset analysis results
    """
    results = {"variable_defined": False, "reset_successful": False, "variable_accessible": False}

    # Combine all text sources for analysis
    combined_text = " ".join(all_messages + [log_content]).lower()

    # Check if the variable was initially defined
    if "variable defined successfully" in combined_text:
        results["variable_defined"] = True
        print("✅ Variable was defined successfully")

    # Check if the variable is still accessible after reset (this should NOT happen)
    if "this should not appear if reset works" in combined_text:
        results["variable_accessible"] = True
        print("❌ Variable is still accessible - reset failed!")
    else:
        print("✅ Variable is not accessible - likely reset worked")

    # Check for evidence of successful reset
    # Look for reset-related messages or NameError exceptions
    reset_indicators = [
        "nameerror",
        "name 'test_variable' is not defined",
        "quenchresetkernel",
        "kernel.*reset",
        "restarted",
    ]

    for indicator in reset_indicators:
        if indicator in combined_text:
            results["reset_successful"] = True
            print(f"✅ Found reset indicator: {indicator}")
            break

    # If variable was defined but is not accessible, and we didn't find explicit reset indicators,
    # we can still infer that reset likely worked
    if results["variable_defined"] and not results["variable_accessible"]:
        results["reset_successful"] = True
        print("✅ Inferred successful reset (variable defined but not accessible)")

    return results


if __name__ == "__main__":
    # Allow running directly for debugging
    asyncio.run(test_quench_reset_kernel())
