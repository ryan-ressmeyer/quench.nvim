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
-- Priority: 1) NVIM_PYTHON_HOST (CI), 2) venv (local dev), 3) system python (fallback)
local python_host = os.getenv('NVIM_PYTHON_HOST')
if python_host then
  -- CI environment - use explicitly provided Python
  vim.g.python3_host_prog = python_host
else
  -- Local development - try venv first
  local venv_python = '/home/ryanress/code/ubuntu-config/nvim/pynvim-env/.venv/bin/python'
  if vim.fn.executable(venv_python) == 1 then
    vim.g.python3_host_prog = venv_python
  else
    -- Fallback to system python if venv doesn't exist
    local python_path = vim.fn.exepath('python3') or vim.fn.exepath('python')
    if python_path ~= '' then
      vim.g.python3_host_prog = python_path
    end
  end
end

-- Configure Quench plugin settings for testing
vim.g.quench_log_level = 'DEBUG'
vim.g.quench_nvim_web_server_port = 8766  -- Use different port for testing to avoid conflicts