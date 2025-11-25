-- Quench Plugin Configuration Example
-- Add this to your init.lua or equivalent configuration

-- ============================================================================
-- INSTALLATION WITH LAZY.NVIM (RECOMMENDED)
-- ============================================================================

-- Example 1: Install from GitHub
return {
  "ryan-ressmeyer/quench.nvim",
  lazy = false,  -- Load on startup
  opts = {
    web_server = {
      host = "127.0.0.1",  -- Default: localhost only
      port = 8765,         -- Default: 8765
    },
    -- Optional: customize cell delimiter pattern (default: r'^#+\s*%%')
    -- cell_delimiter = "^#%%",
  },
  keys = {
    -- Cell execution
    { "<leader>n", "<Cmd>QuenchRunCellAdvance<CR>", desc = "Run Cell and Advance" },
    { "<leader>m", "<Cmd>QuenchRunCell<CR>", desc = "Run Cell" },
    { "<leader>ql", "<Cmd>QuenchRunLine<CR>", desc = "Run Line" },
    { "<leader>qv", "<Cmd>QuenchRunSelection<CR>", mode = "v", desc = "Run Selection" },
    { "<leader>qa", "<Cmd>QuenchRunAll<CR>", desc = "Run All Cells" },
    { "<leader>qu", "<Cmd>QuenchRunAbove<CR>", desc = "Run Above" },
    { "<leader>qd", "<Cmd>QuenchRunBelow<CR>", desc = "Run Below" },

    -- Kernel management
    { "<leader>qr", "<Cmd>QuenchResetKernel<CR>", desc = "Reset Kernel" },
    { "<leader>qi", "<Cmd>QuenchInterruptKernel<CR>", desc = "Interrupt Kernel" },
    { "<leader>qn", "<Cmd>QuenchStartKernel<CR>", desc = "Start Kernel" },
    { "<leader>qk", "<Cmd>QuenchShutdownKernel<CR>", desc = "Shutdown Kernel" },
    { "<leader>qs", "<Cmd>QuenchSelectKernel<CR>", desc = "Select Kernel" },

    -- Status and debugging
    { "<leader>qS", "<Cmd>QuenchStatus<CR>", desc = "Quench Status" },
    { "<leader>qx", "<Cmd>QuenchStop<CR>", desc = "Stop Quench" },
    { "<leader>qD", "<Cmd>QuenchDebug<CR>", desc = "Debug Quench" },
    { "<leader>qo", "<Cmd>QuenchOpen<CR>", desc = "Open Web Interface" },
  },
}

-- Example 2: Local development setup
-- {
--   "quench.nvim",
--   dir = "/path/to/local/quench.nvim",  -- Local path
--   lazy = false,
--   opts = {
--     web_server = {
--       host = "0.0.0.0",  -- Listen on all interfaces (for remote access)
--       port = 8765,
--     },
--   },
--   keys = {
--     -- Same keybindings as Example 1
--   },
-- }

-- ============================================================================
-- TRADITIONAL SETUP (WITHOUT LAZY.NVIM)
-- ============================================================================

-- Configure web server (optional)
vim.g.quench_nvim_web_server_host = "127.0.0.1"  -- Default: 127.0.0.1
vim.g.quench_nvim_web_server_port = 8765         -- Default: 8765

-- For remote development:
-- vim.g.quench_nvim_web_server_host = "0.0.0.0"  -- Listen on all interfaces

-- Automatically select next available port if configured port is in use
-- (default: false - disabled for security; fails if port unavailable)
vim.g.quench_nvim_web_server_auto_select_port = false

-- Cell delimiter pattern (regex)
-- (default: r'^#+\s*%%' - matches #%%, ##%%, # %%, etc.)
vim.g.quench_nvim_cell_delimiter = r'^#+\s*%%'

-- ============================================================================
-- KEY MAPPINGS (TRADITIONAL SETUP)
-- ============================================================================

-- Option 1: Python-only mappings (recommended)
vim.api.nvim_create_autocmd("FileType", {
  pattern = "python",
  callback = function()
    local opts = { noremap = true, silent = true, buffer = true }

    -- Cell execution
    vim.keymap.set('n', '<leader>n', ':QuenchRunCellAdvance<CR>', opts)
    vim.keymap.set('n', '<leader>m', ':QuenchRunCell<CR>', opts)
    vim.keymap.set('n', '<leader>ql', ':QuenchRunLine<CR>', opts)
    vim.keymap.set('v', '<leader>qv', ':QuenchRunSelection<CR>', opts)
    vim.keymap.set('n', '<leader>qa', ':QuenchRunAll<CR>', opts)
    vim.keymap.set('n', '<leader>qu', ':QuenchRunAbove<CR>', opts)
    vim.keymap.set('n', '<leader>qd', ':QuenchRunBelow<CR>', opts)

    -- Kernel management
    vim.keymap.set('n', '<leader>qr', ':QuenchResetKernel<CR>', opts)
    vim.keymap.set('n', '<leader>qi', ':QuenchInterruptKernel<CR>', opts)
    vim.keymap.set('n', '<leader>qn', ':QuenchStartKernel<CR>', opts)
    vim.keymap.set('n', '<leader>qk', ':QuenchShutdownKernel<CR>', opts)
    vim.keymap.set('n', '<leader>qs', ':QuenchSelectKernel<CR>', opts)

    -- Status and debugging
    vim.keymap.set('n', '<leader>qS', ':QuenchStatus<CR>', opts)
    vim.keymap.set('n', '<leader>qx', ':QuenchStop<CR>', opts)
    vim.keymap.set('n', '<leader>qD', ':QuenchDebug<CR>', opts)
    vim.keymap.set('n', '<leader>qo', ':QuenchOpen<CR>', opts)
  end,
})

-- Option 2: Global mappings (if you prefer)
-- vim.keymap.set('n', '<leader>n', ':QuenchRunCellAdvance<CR>', { noremap = true, silent = true })
-- vim.keymap.set('n', '<leader>m', ':QuenchRunCell<CR>', { noremap = true, silent = true })
-- ... (add other mappings as needed)

-- ============================================================================
-- POST-INSTALLATION STEPS
-- ============================================================================

-- 1. Install Python dependencies:
--    pip install pynvim jupyter-client aiohttp websockets

-- 2. Update remote plugins (REQUIRED after first install):
--    :UpdateRemotePlugins

-- 3. Restart Neovim

-- 4. Open a Python file and test with:
--    :QuenchStatus

-- ============================================================================
-- COMMAND REFERENCE
-- ============================================================================

-- Execution Commands:
--   :QuenchRunCell            - Execute current cell
--   :QuenchRunCellAdvance     - Execute current cell and move to next
--   :QuenchRunLine            - Execute current line
--   :QuenchRunSelection       - Execute visual selection
--   :QuenchRunAbove           - Execute all cells above cursor
--   :QuenchRunBelow           - Execute all cells below cursor
--   :QuenchRunAll             - Execute all cells in buffer

-- Kernel Management:
--   :QuenchInterruptKernel    - Interrupt running kernel (Ctrl+C)
--   :QuenchResetKernel        - Restart kernel and clear state
--   :QuenchStartKernel        - Start new unattached kernel
--   :QuenchShutdownKernel     - Shutdown running kernel
--   :QuenchSelectKernel       - Select/attach kernel to buffer

-- Status and Debugging:
--   :QuenchStatus             - Show plugin status
--   :QuenchDebug              - Show diagnostic information
--   :QuenchOpen               - Open web interface in browser
--   :QuenchStop               - Stop all Quench components
