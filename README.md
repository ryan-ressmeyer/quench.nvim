
  ░██████   ░██     ░██ ░██████████ ░███    ░██   ░██████  ░██     ░██ 
 ░██   ░██  ░██     ░██ ░██         ░████   ░██  ░██   ░██ ░██     ░██ 
░██     ░██ ░██     ░██ ░██         ░██░██  ░██ ░██        ░██     ░██ 
░██     ░██ ░██     ░██ ░█████████  ░██ ░██ ░██ ░██        ░██████████ 
░██     ░██ ░██     ░██ ░██         ░██  ░██░██ ░██        ░██     ░██ 
 ░██   ░██   ░██   ░██  ░██         ░██   ░████  ░██   ░██ ░██     ░██ 
  ░██████     ░██████   ░██████████ ░██    ░███   ░██████  ░██     ░██ 
       ░██                                                             
        ░██                                                            
                              
# Quench.nvim 💧

**Interactive Python development in Neovim, inspired by Jupyter notebooks.** 🐍

Quench brings the fluid, cell-based execution of modern data science tools directly into Neovim. Write Python code in standard `.py` files, execute cells on the fly, and see rich media output like plots, tables, and HTML in a browser—all without leaving your editor. Quench is designed for a seamless, non-blocking, and powerful interactive programming experience. 🚀

## ✨ Features

  * **Cell-Based Execution**: Structure your Python scripts with `#%%` delimiters and run code blocks individually.
  * **Rich Media Output**: Quench automatically opens a browser window 🌐 to display rich outputs like Matplotlib plots 📈, Pandas DataFrames, and HTML content that don't fit in a terminal.
  * **Seamless Integration**: Get immediate text-based feedback directly within Neovim while your rich media renders in the browser.
  * **Powerful Kernel Management**: Quench manages IPython kernels for you, ensuring a clean and isolated environment for each of your projects. Each buffer is mapped to its own kernel session, and variables persist between cell executions within the same buffer. 🧠
  * **Asynchronous and Non-Blocking**: Built with `asyncio`, Quench runs in the background, so your editor is always responsive. ⚡
  * **Extensive Execution Commands**: Beyond running the current cell, you can also execute the current line, a visual selection, or all cells above/below the cursor. 🎬

## ✅ Requirements

  * Neovim \>= 0.8.0
  * Python 3
  * `pynvim`
  * `jupyter-client`
  * `aiohttp` (optional, for web server and rich output)
  * `websockets` (optional, for web server and rich output)

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
    pip install pynvim jupyter-client aiohttp websockets matplotlib pandas
    ```

2.  **Open a Python file** (`.py`) in Neovim.

3.  **Create your first cell** by adding `#%%` as a delimiter:

    ```python
    #%%
    print("Hello, Quench! 👋")

    import matplotlib.pyplot as plt
    plt.plot([1, 2, 3], [4, 5, 6])
    plt.show()
    ```

4.  **Execute the cell** by placing your cursor inside it and running the command:

    ```vim
    :QuenchRunCell
    ```

5.  **Check your output**. "Hello, Quench\!" will appear in your Neovim command line, and a browser window will open to display the Matplotlib plot. 🎉

## 🛠️ Commands

Quench provides a comprehensive set of commands for executing code:

| Command | Description |
| :--- | :--- |
| `:QuenchRunCell` | Executes the code in the current cell. |
| `:QuenchRunCellAdvance` | Executes the current cell and moves the cursor to the next one. ➡️ |
| `:QuenchRunSelection` | Executes the visually selected lines of code. |
| `:QuenchRunLine` | Executes only the line the cursor is currently on. |
| `:QuenchRunAbove` | Runs all cells from the top of the buffer to the current cell. 🔼 |
| `:QuenchRunBelow` | Runs all cells from the current cell to the end of the buffer. 🔽 |
| `:QuenchRunAll` | Runs all cells in the current buffer. |
| `:QuenchStatus` | Shows the status of the Quench plugin, including the web server and active kernel sessions. ℹ️ |
| `:QuenchStop` | Stops all Quench components, including the web server and all kernel sessions. ⏹️ |

For a better workflow, it's recommended to map these commands to keybindings in your Neovim configuration.

## ⚙️ Configuration

You can customize Quench's behavior by setting the following global variables in your `init.lua` or `init.vim`:

**Lua**

```lua
-- Web server host (default: "127.0.0.1")
vim.g.quench_nvim_web_server_host = "127.0.0.1"

-- Web server port (default: 8765)
vim.g.quench_nvim_web_server_port = 8765

-- Recommended keybindings ⌨️
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

" Recommended keybindings ⌨️
autocmd FileType python nnoremap <buffer><silent> <leader>r :QuenchRunCell<CR>
autocmd FileType python nnoremap <buffer><silent> <leader>R :QuenchRunCellAdvance<CR>
autocmd FileType python vnoremap <buffer><silent> <leader>r :QuenchRunSelection<CR>
autocmd FileType python nnoremap <buffer><silent> <leader>s :QuenchStatus<CR>
```
