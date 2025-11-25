#!/usr/bin/env python3
"""
Quick Kernel Status Indicator Test
Run cells 1-4 in sequence to see the main state transitions.
"""

# %% Cell 1: Idle → Busy → Idle (Green pulsing)
import time

print("State: Idle (Blue) → Busy (Green pulsing) → Idle (Blue)")
for i in range(3):
    print(f"Working... {i+1}/3")
    time.sleep(1)
print("✓ Back to Idle")

# %% Cell 2: Error state (Red exclamation with glow)
print("State: Idle → Busy → Error (Red '!' with glow)")
raise ValueError("Test error - watch indicator turn red!")

# %% Cell 3: Recover from error
print("State: Error → Idle (after 3 seconds)")
print("Recovered! Back to Idle state")

# %% Cell 4: Kill kernel to test Dead → Auto-restart
print("State: About to crash kernel → Dead (Orange X)")
print("After this, run Cell 5 to test auto-restart")
import os, signal, time

time.sleep(2)
os.kill(os.getpid(), signal.SIGKILL)

# %% Cell 5: Auto-restart test
print("State: Dead → Auto-Restarting → Idle")
print("If you see this, auto-restart worked! ✓")
