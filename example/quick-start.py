#%%
# Quick Start with Quench
# Execute this cell to test your plugin installation

print("🚀 Quench is working!")
print("This output appears in Neovim")

#%%
# Test variables and state persistence
name = "Quench User"
numbers = [1, 2, 3, 4, 5]

print(f"Hello, {name}!")
print(f"Sum of numbers: {sum(numbers)}")

#%%  
# Test rich output (if matplotlib is available)
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
    print("🌐 Check your browser at the URL shown above")
    
except ImportError:
    print("📦 Install matplotlib for rich output: pip install matplotlib")

#%%
# Test error handling
print("Testing error handling...")

try:
    result = 10 / 0
except ZeroDivisionError:
    print("✅ Error handling works - errors appear in both Neovim and browser")

print("🎉 Quick start complete! You're ready to use Quench!")

#%%
