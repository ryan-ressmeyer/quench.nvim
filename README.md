# 🔥 Quench.nvim 💧

[![Neovim](https://img.shields.io/badge/Neovim-0.8+-green.svg?style=flat-square&logo=neovim)](https://neovim.io)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg?style=flat-square&logo=python)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![codecov](https://codecov.io/gh/ryan-ressmeyer/quench.nvim/branch/main/graph/badge.svg)](https://codecov.io/gh/ryan-ressmeyer/quench.nvim)

**Interactive Python development in Neovim using cell-based execution.**

Quench brings Visual Studio Code's Jupyter-like cell execution workflow to Neovim. Similar to how VS Code's Python extension allows you to run code cells defined with `# %%` delimiters, Quench enables you to structure Python scripts into executable blocks and run them interactively. Write Python code in standard `.py` files, execute cells on the fly, and view rich media output like plots, tables, and HTML in a browser—all without leaving your editor.

## ✨ Features

  * **Cell-Based Execution**: Structure your Python scripts with `#%%` delimiters and run code blocks individually.
  * **Rich Media Output**: Automatically displays Matplotlib plots, Pandas DataFrames, and HTML content in a browser window for content that doesn't fit in a terminal.
  * **Auto-Start Web Server**: Web server automatically starts when Neovim launches, allowing you to connect your browser immediately (configurable).
  * **Direct Integration**: Get immediate text-based feedback within Neovim while rich media renders in the browser.
  * **Kernel Management**: Manages IPython kernels with isolated environments for each project. Each buffer maps to its own kernel session, and variables persist between cell executions within the same buffer.
  * **Non-blocking Asynchronous Operation**: Built with `asyncio` to run in the background, keeping your editor responsive.
  * **Extensive Execution Commands**: Execute the current cell, line, visual selection, or all cells above/below the cursor.

## ✅ Requirements

**Required:**
  * Neovim >= 0.8.0
  * Python >= 3.9
  * `pynvim >= 0.4.3`
  * `jupyter-client >= 7.0.0`
  * `aiohttp >= 3.8.0`
  * `websockets >= 11.0.0`

## 📦 Installation

You can install Quench.nvim using your favorite plugin manager.

**lazy.nvim**

```lua
{
  "ryan-ressmeyer/quench.nvim",
  config = function()
    -- Optional configuration
    vim.g.quench_nvim_web_server_host = "127.0.0.1"
    vim.g.quench_nvim_web_server_port = 8765
  end
}
```

After installing, you need to update the remote plugins by running the following command in Neovim and restarting:

```vim
:UpdateRemotePlugins
```

## 🚀 Quick Start

1.  **Install the Python dependencies**:

    ```bash
    pip install pynvim jupyter-client aiohttp websockets
    ```

2.  **Open a Python file** (`.py`) in Neovim.

3.  **Create your first cell** by adding `#%%` as a delimiter:

    ```python
    #%%
    print("Hello, Quench!")

    import matplotlib.pyplot as plt
    plt.plot([1, 2, 3], [4, 5, 6])
    plt.show()
    ```

4.  **Execute the cell** by placing your cursor inside it and running the command:

    ```vim
    :QuenchRunCell
    ```

5.  **Check your output**. Open a browser window to display the Matplotlib plot. 🎉

## 🛠️ Commands

Quench provides a comprehensive set of commands for executing code:

| Command | Description |
| :--- | :--- |
| `:QuenchRunCell` | Executes the code in the current cell. |
| `:QuenchRunCellAdvance` | Executes the current cell and moves the cursor to the next one. |
| `:QuenchRunSelection` | Executes the visually selected lines of code. |
| `:QuenchRunLine` | Executes only the line the cursor is currently on. |
| `:QuenchRunAbove` | Runs all cells from the top of the buffer to the current cell. |
| `:QuenchRunBelow` | Runs all cells from the current cell to the end of the buffer. |
| `:QuenchRunAll` | Runs all cells in the current buffer. |
| `:QuenchStatus` | Shows the status of the Quench plugin, including the web server and active kernel sessions. |
| `:QuenchStop` | Stops all Quench components, including the web server and all kernel sessions. |
| `:QuenchDebug` | Shows diagnostic information for debugging plugin functionality. |
| `:QuenchOpen` | Opens the Quench web interface in your default browser. |
| `:QuenchInterruptKernel` | Sends an interrupt signal to the kernel associated with the current buffer. |
| `:QuenchResetKernel` | Restarts the kernel associated with the current buffer and clears its state. 🔄 |
| `:QuenchStartKernel` | Starts a new kernel not attached to any buffers. |
| `:QuenchShutdownKernel` | Shuts down a running kernel and detaches any buffers linked to it. |
| `:QuenchSelectKernel` | Selects a kernel for the current buffer. Can attach to running kernels or start new ones. |

For a better workflow, it's recommended to map these commands to keybindings in your Neovim configuration.

## ⚙️ Configuration

You can customize Quench's behavior by setting the following global variables in your `init.lua` or `init.vim`:

**Lua**

```lua
-- Web server host (default: "127.0.0.1")
vim.g.quench_nvim_web_server_host = "127.0.0.1"

-- Web server port (default: 8765)
vim.g.quench_nvim_web_server_port = 8765

-- Auto-start web server when Neovim launches (default: true)
-- Set to false if you prefer manual server startup via :QuenchRunCell
vim.g.quench_nvim_autostart_server = true

-- Automatically select next available port if configured port is in use
-- (default: false - disabled for security; fails if port unavailable)
vim.g.quench_nvim_web_server_auto_select_port = false

-- Cell delimiter pattern (regex)
-- (default: r'^#+\s*%%' - matches #%%, ##%%, # %%, etc.)
vim.g.quench_nvim_cell_delimiter = r'^#+\s*%%'

-- Recommended keybindings
vim.api.nvim_create_autocmd("FileType", {
  pattern = "python",
  callback = function()
    local opts = { noremap = true, silent = true, buffer = true }
    vim.keymap.set('n', '<leader>r', ':QuenchRunCell<CR>', opts)
    vim.keymap.set('n', '<leader>R', ':QuenchRunCellAdvance<CR>', opts)
    vim.keymap.set('v', '<leader>r', ':QuenchRunSelection<CR>', opts)
    vim.keymap.set('n', '<leader>s', ':QuenchStatus<CR>', opts)
  end,
})
```

**Vimscript**

```vim
" Web server host (default: "127.0.0.1")
let g:quench_nvim_web_server_host = "127.0.0.1"

" Web server port (default: 8765)
let g:quench_nvim_web_server_port = 8765

" Auto-start web server when Neovim launches (default: 1)
" Set to 0 if you prefer manual server startup via :QuenchRunCell
let g:quench_nvim_autostart_server = 1

" Automatically select next available port if configured port is in use
" (default: 0 - disabled for security; fails if port unavailable)
let g:quench_nvim_web_server_auto_select_port = 0

" Cell delimiter pattern (regex)
" (default: r'^#+\s*%%' - matches #%%, ##%%, # %%, etc.)
let g:quench_nvim_cell_delimiter = r'^#+\s*%%'

" Recommended keybindings
autocmd FileType python nnoremap <buffer><silent> <leader>r :QuenchRunCell<CR>
autocmd FileType python nnoremap <buffer><silent> <leader>R :QuenchRunCellAdvance<CR>
autocmd FileType python vnoremap <buffer><silent> <leader>r :QuenchRunSelection<CR>
autocmd FileType python nnoremap <buffer><silent> <leader>s :QuenchStatus<CR>
```

## ☕ Support

I'm a neuroscience PhD student who writes open source code on the side. If you find Quench useful, I'd appreciate any support!

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-donate-yellow.svg?style=flat-square&logo=buy-me-a-coffee)](https://buymeacoffee.com/ryanress)
