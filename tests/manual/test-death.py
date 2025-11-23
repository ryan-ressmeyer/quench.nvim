# %%
# Cell 1: Verify Life
# Run this cell first to make sure everything is normal.
import os
import time
import sys

pid = os.getpid()
print(f"✅ Kernel is ALIVE.")
print(f"   PID: {pid}")
print(f"   Python: {sys.version.split()[0]}")
print("Proceed to the next cell to simulate a crash.")

# %%
# Cell 2: Simulate Kernel Death (Process Suicide)
# WARNING: This will kill the kernel process immediately!

import os
import signal
import time

print("💀 Initiating kernel process suicide in 3 seconds...")
print("   Watch the frontend status indicator!")

# Give you a moment to switch focus to the browser if needed
time.sleep(3)

# Kill the current process with SIGKILL (kill -9)
# This simulates an OOM killer or external termination
os.kill(os.getpid(), signal.SIGKILL)

# This code will never be reached
print("❌ If you see this, the kernel failed to die.")

# %%
# Cell 3: Test Auto-Restart
# After running Cell 2 (which kills the kernel), run this cell.
# It should automatically restart the kernel and execute successfully!

import os
import sys

print("🔄 AUTO-RESTART SUCCESS!")
print(f"   New Kernel PID: {os.getpid()}")
print(f"   Python: {sys.version.split()[0]}")
print("")
print("✅ The kernel was automatically restarted when you ran this cell.")
print("   Previous outputs should still be visible in the frontend.")
print("   Check the frontend for a yellow 'Kernel Auto-Restarted' notification.")
