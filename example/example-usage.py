#%%
# ==============================================================================
# SECTION 1: QUICK START - Getting Started with Quench
# ==============================================================================
# Cell 1: Simple "Hello World" test
# Execute this cell to test your plugin installation

print("🚀 Quench is working!")
print("This output appears in Neovim")
print("Position your cursor anywhere in this cell and run :call QuenchRunCell()")

#%%
# Cell 2: State persistence test
# This demonstrates that variables persist between cell executions

name = "Quench User"
numbers = [1, 2, 3, 4, 5]

print(f"Hello, {name}!")
print(f"Sum of numbers: {sum(numbers)}")
print("✅ Variables persist across cells - try accessing 'name' or 'numbers' in the next cell!")

#%%
# Cell 3: Basic plotting with rich output
# This tests matplotlib integration and browser display

try:
    import matplotlib.pyplot as plt
    import numpy as np

    x = np.linspace(0, 10, 50)
    y = np.sin(x)

    plt.figure(figsize=(8, 4))
    plt.plot(x, y, 'b-', linewidth=2)
    plt.title('Sine Wave - Rich Output Test')
    plt.xlabel('x')
    plt.ylabel('sin(x)')
    plt.grid(True)
    plt.show()

    print("✅ Rich output (plot) should appear in browser!")
    print("🌐 Check your browser at the URL shown in Neovim")

except ImportError:
    print("📦 Install matplotlib and numpy for rich output:")
    print("   pip install matplotlib numpy")

#%%
# Cell 4: Error handling demonstration
# This shows how Quench displays errors in both Neovim and browser

print("Testing error handling...")

try:
    result = 10 / 0
except ZeroDivisionError:
    print("✅ Error handling works - errors appear in both Neovim and browser")

print("🎉 Quick start complete! Continue below for comprehensive examples.")

#%%
# ==============================================================================
# SECTION 2: COMPREHENSIVE EXAMPLES - Core Features
# ==============================================================================
# Cell 5: Advanced plotting with trigonometric functions
# This cell shows more sophisticated matplotlib usage

print("Creating advanced trigonometric plot...")

# Reuse x from earlier or create new data
x = np.linspace(0, 2 * np.pi, 100)
y = np.sin(x)

# Create a matplotlib plot
plt.figure(figsize=(10, 6))
plt.plot(x, y, 'b-', label='sin(x)', linewidth=2)
plt.plot(x, np.cos(x), 'r--', label='cos(x)', linewidth=2)
plt.xlabel('x')
plt.ylabel('y')
plt.title('Trigonometric Functions')
plt.legend()
plt.grid(True)
plt.show()

print("Plot displayed in browser! Check your web browser at the URL shown in Neovim.")
print(f"Created data arrays: x.shape={x.shape}, y.shape={y.shape}")
print(f"Min/Max values: y_min={y.min():.2f}, y_max={y.max():.2f}")

#%%
# Cell 6: Data analysis with pandas
# This shows how Quench handles tabular data display

import pandas as pd

# Create sample data
data = {
    'Name': ['Alice', 'Bob', 'Charlie', 'Diana'],
    'Age': [25, 30, 35, 28],
    'City': ['New York', 'London', 'Tokyo', 'Paris'],
    'Salary': [50000, 60000, 70000, 55000]
}

df = pd.DataFrame(data)
print("Sample DataFrame:")
print(df)

# Show some statistics
print("\nDataFrame Info:")
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Average salary: ${df['Salary'].mean():,.2f}")

#%%
# Cell 7: Interactive data visualization with subplots
# This demonstrates more complex visualizations

# Create multiple subplots
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))

# Subplot 1: Bar chart
df.plot(x='Name', y='Salary', kind='bar', ax=ax1, color='skyblue')
ax1.set_title('Salary by Person')
ax1.set_ylabel('Salary ($)')

# Subplot 2: Age distribution
df['Age'].hist(ax=ax2, bins=5, color='lightgreen', alpha=0.7)
ax2.set_title('Age Distribution')
ax2.set_xlabel('Age')
ax2.set_ylabel('Count')

# Subplot 3: Scatter plot
ax3.scatter(df['Age'], df['Salary'], s=100, alpha=0.7, c='red')
ax3.set_title('Age vs Salary')
ax3.set_xlabel('Age')
ax3.set_ylabel('Salary ($)')

# Subplot 4: Pie chart of cities
city_counts = df['City'].value_counts()
ax4.pie([1, 1, 1, 1], labels=df['City'], autopct='%1.0f%%')
ax4.set_title('City Distribution')

plt.tight_layout()
plt.show()

print("Multi-plot visualization complete!")

#%%
# Cell 8: Rich output types - HTML, Markdown, and LaTeX
# This shows how Quench handles various display formats

from IPython.display import HTML, Markdown, Math

# Display HTML content
html_content = """
<div style="background-color: #f0f0f0; padding: 10px; border-radius: 5px;">
    <h3 style="color: #333;">HTML Content in Quench</h3>
    <p>This HTML is rendered in the browser!</p>
    <ul>
        <li>Rich formatting</li>
        <li>Interactive elements</li>
        <li>Styled content</li>
    </ul>
</div>
"""

print("Displaying HTML content...")
HTML(html_content)

#%%
# Cell 9: Markdown and LaTeX support
# Continued demonstration of rich display capabilities

# Display Markdown
markdown_content = """
# Markdown Support

Quench supports **Markdown** rendering too!

## Features:
- *Italic text*
- **Bold text**
- `Code snippets`
- [Links](https://github.com)

### Lists:
1. Numbered lists
2. Work great
   - With sublists
   - And more...
"""

print("Displaying Markdown content...")
Markdown(markdown_content)

#%%
# Cell 10: LaTeX math and ANSI colors
# This demonstrates mathematical equations and colored terminal output

# Display LaTeX math
print("Displaying mathematical equations...")
Math(r'\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}')

#%%
# Cell 11: ANSI escape sequences and progress indicators
# Shows colored text and carriage return handling

import time

# Example ANSI escape sequences for colored text
print("\nDemonstrating ANSI colored text:")
print("\033[91mThis is red text\033[0m")

# Carriage return example with progress indicator
print("\nProgress indicator demo:")
print("Progress: 0%", end="")
for i in range(1, 11):
    time.sleep(0.2)
    print(f"\rProgress: {i*10}%", end="")
print("\nDone!")

#%%
# Cell 12: Shell command execution
# This demonstrates IPython's shell command feature using the ! prefix
# Shell commands are executed directly in the system shell

! echo "This is a shell command executed from within the Python cell."
! pwd
! ls -la | head -5

print("\n✅ Shell commands executed successfully!")
print("💡 Use the ! prefix to run any shell command from your Python cells")

#%%
# ==============================================================================
# SECTION 3: GUIDANCE - Advanced Features and Best Practices
# ==============================================================================
# Cell 13: Advanced features and system information

import sys
import os
from concurrent.futures import ThreadPoolExecutor

print("=== Advanced Quench Features ===")

# Demonstrate long-running task
def long_running_task(n):
    """Simulate a long-running computation."""
    time.sleep(1)
    return f"Task {n} completed after 1 second"

print("\nRunning multiple tasks (this will take a few seconds)...")

# Execute multiple tasks
results = []
for i in range(3):
    result = long_running_task(i + 1)
    results.append(result)
    print(result)

print(f"\nAll tasks completed! Results: {len(results)} items")

# Show system information
print(f"\nPython version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"Available modules: numpy, matplotlib, pandas, IPython")

#%%
# ==============================================================================
# SECTION 4: ADVANCED VISUALIZATION - Matplotlib Animations
# ==============================================================================
# Cell 14: Lorentz Attractor Animation
# This demonstrates animated 3D visualization with multiple trajectories

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d import Axes3D
from IPython.display import HTML

print("Creating Lorentz Attractor animation...")
print("This may take a moment to render...")

# Lorentz system parameters
sigma = 10.0
rho = 28.0
beta = 8.0 / 3.0

def lorentz_derivatives(state, sigma, rho, beta):
    """Compute derivatives for the Lorentz system."""
    x, y, z = state
    return np.array([
        sigma * (y - x),
        x * (rho - z) - y,
        x * y - beta * z
    ])

def integrate_lorentz(initial_state, dt, num_steps):
    """Integrate Lorentz system using RK4."""
    trajectory = np.zeros((num_steps, 3))
    trajectory[0] = initial_state
    state = initial_state.copy()

    for i in range(1, num_steps):
        k1 = lorentz_derivatives(state, sigma, rho, beta)
        k2 = lorentz_derivatives(state + 0.5 * dt * k1, sigma, rho, beta)
        k3 = lorentz_derivatives(state + 0.5 * dt * k2, sigma, rho, beta)
        k4 = lorentz_derivatives(state + dt * k3, sigma, rho, beta)
        state = state + (dt / 6.0) * (k1 + 2*k2 + 2*k3 + k4)
        trajectory[i] = state

    return trajectory

# Simulation parameters
dt = 0.01
num_steps = 3000  # 10 seconds of simulation time
fps = 20
duration = 10  # seconds
num_frames = fps * duration

# Initialize 5 points with slight variations
np.random.seed(42)
base_state = np.array([4.0, 1.0, 1.0])
initial_states = [base_state + np.random.randn(3) for _ in range(5)]

# Compute all trajectories
print("Computing trajectories for 5 particles...")
trajectories = [integrate_lorentz(state, dt, num_steps) for state in initial_states]

# Colors for each trajectory
colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']

# Create figure and 3D axis
fig = plt.figure(figsize=(5, 5))
ax = fig.add_subplot(111, projection='3d')

# Initialize line objects and point markers
lines = [ax.plot([], [], [], color=c, alpha=0.7, linewidth=1)[0] for c in colors]
points = [ax.plot([], [], [], 'o', color=c, markersize=6)[0] for c in colors]

# Set axis limits based on trajectory data
all_data = np.vstack(trajectories)
ax.set_xlim(all_data[:, 0].min() - 5, all_data[:, 0].max() + 5)
ax.set_ylim(all_data[:, 1].min() - 5, all_data[:, 1].max() + 5)
ax.set_zlim(all_data[:, 2].min() - 5, all_data[:, 2].max() + 5)

ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')
ax.set_title('Lorentz Attractor - 5 Trajectories', fontsize=14)

# Calculate indices for animation (spread across simulation)
frame_indices = np.linspace(0, num_steps - 1, num_frames, dtype=int)
trail_length = 500  # Number of points in the trail

def init():
    """Initialize animation."""
    for line, point in zip(lines, points):
        line.set_data([], [])
        line.set_3d_properties([])
        point.set_data([], [])
        point.set_3d_properties([])
    return lines + points

def animate(frame):
    """Update animation frame."""
    idx = frame_indices[frame]
    start_idx = max(0, idx - trail_length)

    # Update each trajectory
    for i, (line, point, traj) in enumerate(zip(lines, points, trajectories)):
        # Trail
        line.set_data(traj[start_idx:idx+1, 0], traj[start_idx:idx+1, 1])
        line.set_3d_properties(traj[start_idx:idx+1, 2])
        # Current point
        point.set_data([traj[idx, 0]], [traj[idx, 1]])
        point.set_3d_properties([traj[idx, 2]])

    # Slowly rotate the view (full 360° rotation over the animation)
    ax.view_init(elev=20, azim=frame * 180 / num_frames)

    return lines + points

# Create animation
print("Rendering animation...")
anim = FuncAnimation(fig, animate, init_func=init, frames=num_frames,
                     interval=1000/fps, blit=False)

# Convert to JavaScript HTML animation (no ffmpeg required)
plt.rcParams['animation.html'] = 'jshtml'
plt.rcParams['animation.embed_limit'] = 50  # 50 MB limit
html_anim = anim.to_jshtml()
plt.close(fig)  # Close the figure to prevent double display

print("✅ Animation complete!")
print("🎬 7-second animation with 5 chaotic trajectories")
print("🔄 Watch how nearby points diverge - the butterfly effect!")
print("▶️  Use the playback controls below the animation")

HTML(html_anim)

#%%
