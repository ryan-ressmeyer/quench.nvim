#%%
# ==============================================================================
# SECTION 1: QUICK START
# ==============================================================================
# Cell 1: Simple "Hello World" test
# Execute this cell to test your plugin installation

print("🚀 Quench is working!")
print("This output appears in Neovim")
print("Position your cursor anywhere in this cell and run :call QuenchRunCell()")

#%%
# Cell 2: Shell command execution
# Demonstrates running system commands using ! prefix

print("Shell Command Execution:")
! echo "Commands run in the system shell"
! pwd

print("✅ Shell commands work!")

#%%
# Cell 3: Progress bar with color transitions
# Demonstrates ANSI color support and terminal output features

import time
import sys

print("Progress Bar Demo - Watch the colors change from red to green!\n")

for i in range(101):
    # Calculate color based on progress (red -> yellow -> green)
    if i < 33:
        color = '\033[91m'  # Red
    elif i < 66:
        color = '\033[93m'  # Yellow
    else:
        color = '\033[92m'  # Green

    # Create progress bar
    bar_length = 40
    filled = int(bar_length * i / 100)
    bar = '█' * filled + '░' * (bar_length - filled)

    # Print progress with color
    print(f'\r{color}[{bar}] {i}%\033[0m', end='', flush=True)
    time.sleep(0.05)

print("\n\n✅ Progress complete! ANSI colors work perfectly!")

#%%
# Cell 4: State persistence test
# This demonstrates that variables persist between cell executions

name = "Quench User"
numbers = [1, 2, 3, 4, 5]

print(f"Hello, {name}!")
print(f"Sum of numbers: {sum(numbers)}")
print("✅ Variables persist across cells - try accessing 'name' or 'numbers' in the next cell!")

#%%
# Cell 5: Basic plotting with matplotlib
# This demonstrates matplotlib integration and browser display

import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 2 * np.pi, 100)

plt.figure(figsize=(10, 5))
plt.plot(x, np.sin(x), 'b-', label='sin(x)', linewidth=2)
plt.plot(x, np.cos(x), 'r--', label='cos(x)', linewidth=2)
plt.xlabel('x')
plt.ylabel('y')
plt.title('Trigonometric Functions')
plt.legend()
plt.grid(True)
plt.show()

print("✅ Plot displayed in browser!")
print("📊 Plots appear at the URL shown in Neovim")

#%%
# Cell 6: HTML rendering
# Demonstrates styled HTML output in the browser

from IPython.display import HTML

html_content = """
<div style="background-color: #e8f4f8; padding: 10px; border-radius: 5px;">
    <h3 style="color: #2c5aa0;">HTML Rendering</h3>
    <p>Styled content with <strong>rich formatting</strong></p>
</div>
"""
display(HTML(html_content))

print("✅ HTML renders in browser!")

#%%
# Cell 7: Markdown support
# Demonstrates Markdown rendering

from IPython.display import Markdown

markdown_content = """
## Markdown Support
Quench renders **Markdown** with:
- *Formatting* and **emphasis**
- `Code snippets`
- [Links](https://github.com)
"""
display(Markdown(markdown_content))

print("✅ Markdown renders in browser!")

#%%
# Cell 8: LaTeX math
# Demonstrates mathematical equation rendering

from IPython.display import Math

display(Math(r'\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}'))

print("✅ LaTeX math renders in browser!")

#%%
# Cell 9: Quench Logo Animation
# A flashy finale showcasing terminal animation and ANSI color support

import time
import sys

# ASCII logo from the Quench web interface
logo_lines = [
"  ░██████                                               ░██        ",
" ░██   ░██                                              ░██        ",
"░██     ░██ ░██    ░██  ░███████  ░████████   ░███████  ░████████  ",
"░██     ░██ ░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██ ░██    ░██ ",
"░██     ░██ ░██    ░██ ░█████████ ░██    ░██ ░██        ░██    ░██ ",
" ░██   ░██  ░██   ░███ ░██        ░██    ░██ ░██    ░██ ░██    ░██ ",
"  ░██████    ░█████░██  ░███████  ░██    ░██  ░███████  ░██    ░██ ",
"       ░██                                                         ",
"        ░██                                                        ",
]

# Gradient color palette for metal quenching cycle (ANSI 256-color codes)
gradient_colors = [
    '\033[38;5;33m',   # Dark blue - cold metal
    '\033[38;5;33m',   # Dark blue - cold metal
    '\033[38;5;39m',   # Medium blue
    '\033[38;5;75m',   # Bright blue
    '\033[38;5;117m',  # Light blue
    '\033[38;5;250m',  # Light gray - transition (slightly darker)
    '\033[38;5;224m',  # Light pink/salmon
    '\033[38;5;210m',  # Light red
    '\033[38;5;204m',  # Bright medium red
    '\033[38;5;203m',  # Bright red - hot metal
    '\033[38;5;203m',  # Bright red - hot metal (peak)
    '\033[38;5;203m',  # Bright red - hot metal
    '\033[38;5;204m',  # Bright medium red
    '\033[38;5;210m',  # Light red
    '\033[38;5;224m',  # Light pink/salmon
    '\033[38;5;250m',  # Light gray - transition (slightly darker)
    '\033[38;5;117m',  # Light blue
    '\033[38;5;75m',   # Bright blue
    '\033[38;5;39m',   # Medium blue
    '\033[38;5;33m',   # Dark blue - cold metal
    '\033[38;5;33m',   # Dark blue - cold metal
]
reset = '\033[0m'

print("\n")

# Reserve space for the logo by printing empty lines
for _ in range(len(logo_lines)):
    print()

# Animate the logo with a color wave effect
for frame in range(94):
    # Move cursor up to the start of the logo
    sys.stdout.write(f'\033[{len(logo_lines)}A')

    # Print each line with animated colors
    for line in logo_lines:
        # Clear the line
        sys.stdout.write('\033[2K')

        colored_line = ''
        for i, char in enumerate(line):
            # Create wave effect: gradient position shifts with frame
            # The subtraction creates leftward motion
            gradient_pos = (i//6 - frame) % len(gradient_colors)
            colored_line += gradient_colors[gradient_pos] + char + reset

        sys.stdout.write(colored_line + '\n')

    sys.stdout.flush()
    time.sleep(0.10)  # 100ms per frame = ~1 fps
