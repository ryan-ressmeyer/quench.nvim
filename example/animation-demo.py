#%%
# ==============================================================================
# QUENCH ANIMATION DEMO - Lorentz Attractor
# ==============================================================================
# This example demonstrates Quench's ability to display animated visualizations
# in the browser. It creates an interactive 3D animation of the Lorentz attractor,
# a classic chaotic dynamical system.
#
# Requirements:
#   - numpy
#   - matplotlib
#   - IPython
#
# Usage:
#   1. Open this file in Neovim with Quench installed
#   2. Run the cell below with :call QuenchRunCell()
#   3. Watch the animation render in your browser
#
# Note: This animation may take 10-20 seconds to render.
# ==============================================================================

#%%
# Lorentz Attractor Animation
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
print("🎬 10-second animation with 5 chaotic trajectories")
print("🔄 Watch how nearby points diverge - the butterfly effect!")
print("▶️  Use the playback controls below the animation")

HTML(html_anim)

#%%
