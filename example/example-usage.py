#%%
# Quench Plugin Example Usage
# This file demonstrates all core functionality of the Quench Neovim plugin
# for interactive Python development with cell-based execution.

print("Welcome to Quench! This is your first Python cell.")
print("Position your cursor anywhere in this cell and run :call QuenchRunCell()")

#%%
# Cell 2: Basic Python execution
# This cell shows how regular Python code execution works

import numpy as np
import matplotlib.pyplot as plt

# Create some sample data
x = np.linspace(0, 2 * np.pi, 100)
y = np.sin(x)

print(f"Created data arrays: x.shape={x.shape}, y.shape={y.shape}")
print(f"Min/Max values: y_min={y.min():.2f}, y_max={y.max():.2f}")

#%%
# Cell 3: Rich media output (plots)
# This cell demonstrates how Quench displays plots in the browser

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

#%%
# Cell 4: Data analysis with pandas
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
# Cell 5: Interactive data visualization
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
# Cell 6: Error handling demonstration
# This shows how Quench displays errors in both Neovim and browser

print("This cell will demonstrate error handling...")

try:
    # This will cause a deliberate error
    result = 10 / 0
except ZeroDivisionError as e:
    print(f"Caught error: {e}")
    print("Error messages appear both in Neovim and in the browser!")

# This will show an uncaught error
# Uncomment the next line to see error display:
# undefined_variable + 5

print("Error handling demonstrated!")

#%%
# Cell 7: Working with different data types and rich output
# This shows how Quench handles various Python objects

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
# Display LaTeX math
print("Displaying mathematical equations...")
Math(r'\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}')
#%%
# Example ansi escape sequences for colored text
print("Demonstrating ANSI colored text:")
print("\033[91mThis is red text\033[0m")
# carriage return example
import time
print("Progress: 0%", end="")
for i in range(1, 100):
    time.sleep(0.2)
    print(f"\rProgress: {i*10}%", end="")
print("\nDone!")
#%%
# Cell 8: Plugin status and management
# This shows how to monitor and control Quench

print("=== Quench Plugin Status ===")
print("Run these commands in Neovim to manage the plugin:")
print("")
print(":QuenchStatus  - Show plugin status and active sessions")
print(":QuenchStop   - Stop all plugin components")
print(":HelloWorld   - Test basic plugin functionality")
print("")
print("The plugin automatically:")
print("• Starts web server on first cell execution")
print("• Creates IPython kernel sessions per buffer")
print("• Relays output to both Neovim and browser")
print("• Cleans up resources when Neovim exits")

#%%
# Cell 9: Best practices and tips
# This provides usage guidance for new users

print("=== Quench Best Practices ===")
print("")
print("1. CELL EXECUTION:")
print("   • Position cursor anywhere in a cell")
print("   • Run :call QuenchRunCell() or map to a key")
print("   • Cells are separated by #%% markers")
print("")
print("2. BROWSER INTEGRATION:")
print("   • Web server starts automatically on port 8765")
print("   • Open http://127.0.0.1:8765?kernel_id=<YOUR_KERNEL_ID>")
print("   • Rich output (plots, HTML, etc.) appears in browser")
print("   • Text output appears in Neovim")
print("")
print("3. KERNEL MANAGEMENT:")
print("   • Each buffer gets its own IPython kernel session")
print("   • Variables persist between cell executions")
print("   • Kernels are automatically cleaned up")
print("")
print("4. DEBUGGING:")
print("   • Check :QuenchStatus for plugin state")
print("   • Error messages appear in both Neovim and browser")
print("   • Use :QuenchStop to reset if needed")

#%%
# Cell 10: Advanced features demonstration
# This shows more sophisticated usage patterns

import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

print("=== Advanced Quench Features ===")

# Demonstrate async execution context
def long_running_task(n):
    """Simulate a long-running computation."""
    time.sleep(1)
    return f"Task {n} completed after 1 second"

print("Running multiple tasks (this will take a few seconds)...")

# Execute multiple tasks
results = []
for i in range(3):
    result = long_running_task(i + 1)
    results.append(result)
    print(result)

print(f"All tasks completed! Results: {len(results)} items")

# Show memory usage and performance
import sys
print(f"\nPython version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"Available modules: numpy, matplotlib, pandas, IPython")

#%%
# Cell 11: Final summary and next steps

print("🎉 Congratulations! You've completed the Quench tutorial!")
print("")
print("WHAT YOU'VE LEARNED:")
print("✓ How to execute Python cells with #%% separators")
print("✓ Browser integration for rich media output")
print("✓ Error handling and debugging")
print("✓ Plugin management commands")
print("✓ Best practices for interactive development")
print("")
print("NEXT STEPS:")
print("1. Create your own .py files with #%% cell markers")
print("2. Set up key mappings for QuenchRunCell()")
print("3. Explore the web interface at http://127.0.0.1:8765")
print("4. Try with your own data science projects!")
print("")
print("USEFUL KEYMAPPINGS to add to your init.vim/init.lua:")
print("\" Vim:")
print("autocmd FileType python nnoremap <buffer> <leader>r :call QuenchRunCell()<CR>")
print("")
print("-- Lua:")
print("vim.api.nvim_set_keymap('n', '<leader>r', ':call QuenchRunCell()<CR>', {noremap=true})")
print("")
print("Happy coding with Quench! 🚀")

#%%
