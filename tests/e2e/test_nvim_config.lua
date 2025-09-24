-- Test configuration for Neovim end-to-end testing
-- This config is minimal and focused only on loading Quench plugin

-- Basic Neovim settings for testing
vim.opt.compatible = false
vim.opt.cmdheight = 2  -- More space for command output
vim.opt.shortmess:remove('F')  -- Show full messages
vim.opt.updatetime = 100  -- Faster updates for testing

-- Disable swap files and backups for testing
vim.opt.swapfile = false
vim.opt.backup = false
vim.opt.writebackup = false

-- Enable plugin loading
vim.opt.loadplugins = true

-- Set up basic Python syntax
vim.cmd('syntax enable')
vim.cmd('filetype plugin indent on')

-- Explicitly add current directory and rplugin paths to runtime
local current_dir = vim.fn.getcwd()
vim.opt.runtimepath:prepend(current_dir)
vim.opt.runtimepath:append(current_dir .. '/rplugin')

-- Enable Python 3 provider (required for pynvim)
vim.g.python3_host_prog = '/home/ryanress/code/ubuntu-config/nvim/pynvim-env/.venv/bin/python'

-- Configure Quench plugin settings for testing
vim.g.quench_log_level = 'DEBUG'