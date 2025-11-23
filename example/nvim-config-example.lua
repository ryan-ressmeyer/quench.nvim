-- Quench Plugin Configuration Example
-- Add this to your init.lua or equivalent configuration

-- ============================================================================
-- BASIC SETUP
-- ============================================================================

-- Ensure pynvim is available (install with: pip install pynvim)
-- The plugin should be in your Neovim runtime path

-- Update remote plugins after installation:
-- :UpdateRemotePlugins

-- ============================================================================
-- WEB SERVER CONFIGURATION
-- ============================================================================

-- Configure web server host and port (optional)
-- These can be set globally or through lazy.nvim opts
vim.g.quench_nvim_web_server_host = "127.0.0.1"  -- Default: 127.0.0.1
vim.g.quench_nvim_web_server_port = 8765         -- Default: 8765

-- For remote development, you might want:
-- vim.g.quench_nvim_web_server_host = "0.0.0.0"  -- Listen on all interfaces
-- vim.g.quench_nvim_web_server_port = 8766       -- Use different port

-- Alternative: Set through lazy.nvim opts (if using lazy.nvim):
-- {
--   "your-username/quench.nvim",
--   opts = {
--     web_server = {
--       host = "0.0.0.0",  -- For remote development
--       port = 8766,
--     }
--   }
-- }

-- ============================================================================
-- KEY MAPPINGS
-- ============================================================================

-- Execute current Python cell with <leader>r
vim.api.nvim_create_autocmd("FileType", {
  pattern = "python",
  callback = function()
    local opts = { noremap = true, silent = true, buffer = true }
    
    -- Execute current cell
    vim.keymap.set('n', '<leader>r', ':call QuenchRunCell()<CR>', opts)
    
    -- Show plugin status
    vim.keymap.set('n', '<leader>s', ':QuenchStatus<CR>', opts)
    
    -- Stop plugin (for troubleshooting)
    vim.keymap.set('n', '<leader>x', ':QuenchStop<CR>', opts)
  end
})

-- Alternative: Global mappings (uncomment if preferred)
-- vim.keymap.set('n', '<leader>pr', ':call QuenchRunCell()<CR>', { noremap = true })
-- vim.keymap.set('n', '<leader>ps', ':QuenchStatus<CR>', { noremap = true })
