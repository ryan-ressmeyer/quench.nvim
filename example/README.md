# Quench Plugin Example Usage

This directory contains examples demonstrating how to use the Quench Neovim plugin for interactive Python development.

## Getting Started

### Prerequisites

1. **Install Quench Plugin** in your Neovim configuration
2. **Install Required Python Dependencies:**
   ```bash
   pip install pynvim jupyter-client aiohttp websockets
   
   # For the examples:
   pip install numpy matplotlib pandas ipython
   ```

3. **Update Remote Plugins:**
   ```vim
   :UpdateRemotePlugins
   ```
   Restart Neovim after installation.

## Using the Example

### Step 1: Open the Example File

```bash
nvim example/example-usage.py
```

### Step 2: Execute Your First Cell

1. Position your cursor anywhere in the first cell (lines starting with `#%%`)
2. Run the command: `:call QuenchRunCell()`
3. Watch the output appear in Neovim
4. Note the web server URL that appears

### Step 3: Connect Your Browser

1. Copy the URL shown in Neovim (typically `http://127.0.0.1:8765`)
2. Add the kernel ID parameter: `?kernel_id=<KERNEL_ID>`
3. Open this URL in your web browser
4. You'll see rich output (plots, HTML, etc.) rendered in the browser

### Step 4: Execute More Cells

Continue executing cells to see:
- ✅ Basic Python execution
- ✅ Matplotlib plots in browser
- ✅ Pandas DataFrames  
- ✅ Error handling
- ✅ Rich media (HTML, Markdown, LaTeX)
- ✅ Plugin management

## Example Cell Structure

```python
#%%
# This is cell 1
print("Hello from cell 1!")
x = 42

#%%  
# This is cell 2  
print(f"x from previous cell: {x}")
y = x * 2

#%%
# This is cell 3
import matplotlib.pyplot as plt
plt.plot([1, 2, 3], [1, 4, 9])
plt.show()  # This appears in browser!
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `:call QuenchRunCell()` | Execute current cell |
| `:QuenchStatus` | Show plugin status |
| `:QuenchStop` | Stop all plugin components |
| `:HelloWorld` | Test plugin is loaded |

## Recommended Key Mappings

Add these to your `init.vim` or `init.lua`:

**Vim Script:**
```vim
" Execute current Python cell with <leader>r
autocmd FileType python nnoremap <buffer> <leader>r :call QuenchRunCell()<CR>

" Show plugin status with <leader>s
autocmd FileType python nnoremap <buffer> <leader>s :QuenchStatus<CR>
```

**Lua:**
```lua
-- Execute current Python cell with <leader>r  
vim.api.nvim_create_autocmd("FileType", {
  pattern = "python",
  callback = function()
    vim.api.nvim_buf_set_keymap(0, 'n', '<leader>r', ':call QuenchRunCell()<CR>', {noremap=true})
    vim.api.nvim_buf_set_keymap(0, 'n', '<leader>s', ':QuenchStatus<CR>', {noremap=true})
  end
})
```

## Browser Features

When you open the web interface, you'll see:

- **Real-time Output:** Code execution results stream to browser
- **Rich Media:** Plots, images, HTML, and LaTeX rendered properly  
- **Cell Correlation:** Input code and outputs grouped by execution
- **Error Display:** Formatted error messages with tracebacks
- **Auto-reconnect:** Browser reconnects if connection drops

## Troubleshooting

### Plugin Not Loading
```vim
:UpdateRemotePlugins
" Restart Neovim
```

### No Output in Browser
1. Check `:QuenchStatus` for web server status
2. Verify browser URL includes `?kernel_id=<ID>`
3. Try `:QuenchStop` and execute a cell again

### Python Import Errors
```bash
# Install in the same Python environment as pynvim
pip install jupyter-client aiohttp websockets numpy matplotlib pandas
```

### Kernel Issues
- Check `:QuenchStatus` for active sessions
- Each buffer gets its own kernel session
- Variables persist between cells in the same buffer

## Example Workflow

1. **Open Python file** with `#%%` cell markers
2. **Execute first cell** to start web server and kernel
3. **Open browser** to see rich output
4. **Develop iteratively** - execute cells as you write code
5. **Monitor with** `:QuenchStatus` if needed

## Tips for Best Experience

- **Use meaningful cell comments** to organize your work
- **Keep cells focused** - one concept per cell
- **Check browser and Neovim** for different types of output
- **Save frequently** - kernels persist variables but not files
- **Restart if needed** with `:QuenchStop` then execute a cell

Enjoy interactive Python development in Neovim! 🎉