"""
End-to-end test for Kernel Death Detection.

This test verifies that Quench properly detects and handles cases where
the underlying kernel process disappears (e.g., OOM kill or manual kill).

Steps:
1. Start a kernel
2. Retrieve the kernel's PID via a Python cell
3. Externally kill the kernel process (SIGKILL)
4. Verify Quench detects the death and updates state
"""
import asyncio
import pytest
import os
import signal
import re
from pathlib import Path
from .test_neovim_instance import TestNeovimInstance


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_quench_kernel_death_detection():
    """
    Test that the plugin detects when a kernel process is killed.
    """
    test_config_path = Path(__file__).parent / 'test_nvim_config.lua'
    nvim_instance = TestNeovimInstance(config_file=str(test_config_path))

    try:
        # Step 1: Launch Neovim and load Quench plugin
        await nvim_instance.start(timeout=30)
        print("✅ Neovim started")

        # Step 2: Create a buffer that simulates kernel death and auto-restart
        # This approach keeps everything in a single Neovim session
        test_content = [
            "# Test Kernel Death Detection and Auto-Restart",
            "# %%",
            "# Cell 1: Kill the kernel process (simulates OOM/crash)",
            "import os",
            "import signal",
            "print(f'Kernel PID: {os.getpid()}')",
            "print('Killing kernel in 2 seconds...')",
            "import time",
            "time.sleep(2)",
            "os.kill(os.getpid(), signal.SIGKILL)",
            "print('This should never print')",
            "# %%",
            "# Cell 2: This should trigger auto-restart and execute successfully",
            "print('AUTO_RESTART_SUCCESS: Kernel auto-restarted and executed this cell!')",
            "print(f'New Kernel PID: {os.getpid()}')"
        ]

        await nvim_instance.create_test_buffer(test_content, 'test_kernel_death.py')

        # Step 3: Execute all commands in a SINGLE Neovim session
        print("🚀 Starting kernel and triggering death...")
        nvim_instance.add_command('normal! 3G')  # Go to first cell
        nvim_instance.add_command('call feedkeys("1\\<CR>", "t")')  # Select first kernel option
        nvim_instance.add_command('QuenchRunCell')  # Run cell that kills the kernel

        # Wait for:
        # - Kernel startup (~3 seconds)
        # - Cell execution delay (2 seconds)
        # - Kernel death
        # - Monitor loop detection (2 second poll interval + some buffer)
        nvim_instance.add_command('sleep 10')

        # Try to run the second cell - this should trigger auto-restart
        print("🔄 Running second cell to trigger auto-restart...")
        nvim_instance.add_command('normal! 11G')  # Go to second cell
        nvim_instance.add_command('QuenchRunCell')

        # Wait for:
        # - Auto-restart detection and new kernel startup (can take up to 30 seconds - wait_for_ready timeout)
        # - Cell execution and output logging
        nvim_instance.add_command('sleep 30')

        # Check status
        nvim_instance.add_command('QuenchStatus')

        # Step 4: Execute all commands in one shot
        print("⏳ Executing test sequence...")
        # Use 60 second timeout to account for: kernel startup (~3s) + sleep 10 + sleep 30 + execution time
        result = await nvim_instance.run_commands(timeout=60)

        # Step 5: Verify Detection in logs
        log_tail = nvim_instance.get_log_tail()
        all_messages = nvim_instance.get_all_messages()

        print("🔍 Checking for kernel death detection...")

        # Check for the specific log message
        expected_log = "process died unexpectedly"
        if expected_log not in log_tail.lower():
            print(f"⚠️ Expected log message not found")
            print(f"DEBUG: Log tail:\n{log_tail[-2000:]}")  # Last 2000 chars
            pytest.fail("❌ Quench did not detect kernel death")
        else:
            print("✅ Quench successfully logged the kernel death.")

        # Step 6: Verify Auto-Restart
        print("🔍 Checking for auto-restart...")

        # Check for auto-restart log message
        auto_restart_log = "auto-restarting before execution"
        if auto_restart_log not in log_tail.lower():
            print(f"⚠️ Auto-restart log message not found")
            print(f"DEBUG: Log tail:\n{log_tail[-2000:]}")
            pytest.fail("❌ Kernel did not auto-restart")
        else:
            print("✅ Kernel auto-restart was triggered.")

        # Step 7: Verify Cell Execution After Auto-Restart
        print("🔍 Checking for successful cell execution after auto-restart...")

        # Check for the success message in logs
        success_marker = "AUTO_RESTART_SUCCESS"
        if success_marker not in log_tail:
            print(f"⚠️ Success marker not found in logs")
            print(f"DEBUG: Log tail:\n{log_tail[-2000:]}")
            pytest.fail("❌ Cell did not execute successfully after auto-restart")
        else:
            print("✅ Cell executed successfully after auto-restart!")

        # Step 8: Verify Test Completed Without Timeout
        if result.get('timeout'):
            pytest.fail("❌ Test timed out")

        print("✅ All auto-restart tests passed!")

    finally:
        await nvim_instance.cleanup()


if __name__ == "__main__":
    asyncio.run(test_quench_kernel_death_detection())
