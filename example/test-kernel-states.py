#!/usr/bin/env python3
"""
Test script for Quench Reactive Kernel Status Indicator
Demonstrates all kernel states: Disconnected, Connecting, Starting, Idle, Busy, Error, Dead

Usage:
    1. Open this file in Neovim with Quench installed
    2. Open the Quench frontend in your browser (http://127.0.0.1:8765)
    3. Run each cell sequentially using :QuenchRunCell or your keybinding
    4. Watch the kernel status indicator change colors and animations

Expected State Transitions:
    ⬡ Grey (Disconnected) → When not connected
    ⬢ Yellow pulsing (Connecting/Starting) → On first cell execution
    ⬢ Blue (Idle) → When ready for input
    ⬢ Green pulsing (Busy) → During code execution
    ! Red with glow (Error) → After exception (3 sec persistence)
    ✕ Orange (Dead) → After kernel crash (Cell 5)
"""

# %% Cell 1: Test Idle → Busy → Idle transition
print("Testing Idle → Busy → Idle")
print("Watch the indicator: Blue → Green (pulsing) → Blue")
import time
for i in range(3):
    print(f"Working... {i+1}/3")
    time.sleep(1)
print("✓ Completed - Should return to Idle (Blue)")

# %% Cell 2: Test Busy state with longer computation
print("Testing longer Busy state (Green pulsing hexagon)")
print("The indicator should pulse green for ~5 seconds")
import time
total = 0
for i in range(5):
    total += i
    print(f"Computing... {i+1}/5 (total={total})")
    time.sleep(1)
print(f"✓ Final result: {total}")
print("Should return to Idle (Blue)")

# %% Cell 3: Test Error state (Red exclamation mark)
print("Testing Error state")
print("Watch the indicator: Blue → Green → Red (!) → Blue after 3 seconds")
print("About to raise an exception...")
raise ValueError("This is a test error - indicator should show red '!' with glow")
# The indicator should:
# 1. Turn red with '!' icon immediately
# 2. Stay red for 3 seconds (persistence)
# 3. Return to blue 'idle' state

# %% Cell 4: Test Error with immediate recovery
print("Testing Error → Idle transition")
print("First, let's cause an error:")
try:
    result = 1 / 0  # This will error
except ZeroDivisionError as e:
    print(f"Caught error: {e}")
    print("Indicator should show red '!' briefly")

print("\nNow running valid code immediately:")
print("Indicator should go: Red (!) → Blue (idle)")
for i in range(2):
    print(f"Valid code running... {i+1}/2")
print("✓ Recovered - back to Idle")

# %% Cell 5: Test kernel death and auto-restart
print("⚠️  Testing Kernel Death state (Orange X)")
print("WARNING: This will crash the kernel on purpose!")
print("Expected behavior:")
print("  1. Indicator shows Orange '✕' (dead)")
print("  2. Frontend shows '💀 Kernel Died' notification")
print("  3. Running next cell auto-restarts kernel")
print("  4. Frontend shows '🔄 Kernel Auto-Restarted' notification")
print("\nCrashing kernel in 3 seconds...")
import time
time.sleep(3)
import os
import signal
os.kill(os.getpid(), signal.SIGKILL)  # Force crash

# %% Cell 6: Test auto-restart (run AFTER Cell 5 crashes)
print("Testing Auto-Restart")
print("If you're seeing this, the kernel auto-restarted successfully!")
print("The indicator should be:")
print("  - Blue (Idle) after the restart")
print("  - Green (Busy) while this cell runs")
print("✓ Auto-restart successful!")

# %% Cell 7: Simulate multiple rapid executions
print("Testing rapid Busy → Idle transitions")
for i in range(5):
    print(f"Quick operation {i+1}/5")
print("Indicator should have pulsed green briefly")

# %% Cell 8: Test with progress bar simulation
print("Testing Busy state with simulated progress bar")
print("Watch the green pulsing indicator during execution:")
import time
steps = 10
for i in range(steps):
    progress = (i + 1) / steps * 100
    bar = "█" * (i + 1) + "░" * (steps - i - 1)
    print(f"\r[{bar}] {progress:.0f}%", end="", flush=True)
    time.sleep(0.5)
print("\n✓ Progress complete - back to Idle")

# %% Cell 9: Final state summary
print("=" * 60)
print("Kernel State Test Summary")
print("=" * 60)
print("States tested:")
print("  ⬡ Grey    = Disconnected (initial state)")
print("  ⬢ Yellow  = Connecting/Starting (pulsing)")
print("  ⬢ Blue    = Idle (ready)")
print("  ⬢ Green   = Busy (pulsing during execution)")
print("  ! Red     = Error (with glow, 3s persistence)")
print("  ✕ Orange  = Dead (after crash)")
print("\nAll state transitions tested successfully! ✓")
