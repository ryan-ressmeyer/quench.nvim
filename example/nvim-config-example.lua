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
    
    -- Test plugin is working
    vim.keymap.set('n', '<leader>h', ':HelloWorld<CR>', opts)
  end
})

-- Alternative: Global mappings (uncomment if preferred)
-- vim.keymap.set('n', '<leader>pr', ':call QuenchRunCell()<CR>', { noremap = true })
-- vim.keymap.set('n', '<leader>ps', ':QuenchStatus<CR>', { noremap = true })

-- ============================================================================
-- AUTO COMMANDS
-- ============================================================================

-- Automatically show helpful message when opening Python files
vim.api.nvim_create_autocmd("FileType", {
  pattern = "python",
  callback = function()
    -- Only show once per session
    if not vim.g.quench_help_shown then
      vim.defer_fn(function()
        print("Quench: Use <leader>r to execute Python cells (marked with #%%)")
        local host = vim.g.quench_nvim_web_server_host or "127.0.0.1"
        local port = vim.g.quench_nvim_web_server_port or 8765
        print("Quench: Browser output at http://" .. host .. ":" .. port)
      end, 1000) -- Show after 1 second
      vim.g.quench_help_shown = true
    end
  end
})

-- ============================================================================
-- OPTIONAL: CELL HIGHLIGHTING
-- ============================================================================

-- Highlight #%% cell separators
vim.api.nvim_create_autocmd({"BufRead", "BufNewFile"}, {
  pattern = "*.py",
  callback = function()
    -- Create highlight group for cell separators
    vim.api.nvim_set_hl(0, "QuenchCellSep", { fg = "#61AFEF", bold = true })
    
    -- Match #%% patterns
    vim.fn.matchadd("QuenchCellSep", "^#%%.*")
  end
})

-- ============================================================================
-- OPTIONAL: STATUS LINE INTEGRATION
-- ============================================================================

-- Function to get Quench status for statusline
function _G.quench_status()
  -- This is a simple example - you could make it more sophisticated
  return "🐍 Quench"
end

-- Example statusline integration (adjust to your statusline plugin)
-- vim.o.statusline = vim.o.statusline .. " %{v:lua.quench_status()}"

-- ============================================================================
-- OPTIONAL: WHICH-KEY INTEGRATION
-- ============================================================================

-- If you use which-key.nvim, add descriptions for the mappings
local ok, wk = pcall(require, "which-key")
if ok then
  wk.register({
    ["<leader>r"] = { "Execute Python Cell" },
    ["<leader>s"] = { "Quench Status" },
    ["<leader>x"] = { "Stop Quench" },
    ["<leader>h"] = { "Test Quench" },
  }, { mode = "n", buffer = nil })
end

-- ============================================================================
-- OPTIONAL: TELESCOPE INTEGRATION
-- ============================================================================

-- Custom Telescope picker for Python cells (advanced example)
local function create_cell_picker()
  local ok_tel, telescope = pcall(require, "telescope")
  if not ok_tel then return end
  
  local pickers = require("telescope.pickers")
  local finders = require("telescope.finders")
  local conf = require("telescope.config").values
  
  local function find_cells()
    local bufnr = vim.api.nvim_get_current_buf()
    local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
    local cells = {}
    
    for i, line in ipairs(lines) do
      if line:match("^#%%") then
        local title = line:gsub("^#%%", ""):gsub("^%s*", "")
        if title == "" then title = "Cell " .. #cells + 1 end
        table.insert(cells, { line = i, title = title, content = line })
      end
    end
    
    return cells
  end
  
  pickers.new({}, {
    prompt_title = "Python Cells",
    finder = finders.new_table {
      results = find_cells(),
      entry_maker = function(entry)
        return {
          value = entry,
          display = string.format("Line %d: %s", entry.line, entry.title),
          ordinal = entry.title,
        }
      end
    },
    sorter = conf.generic_sorter({}),
    attach_mappings = function(prompt_bufnr, map)
      local actions = require("telescope.actions")
      local action_state = require("telescope.actions.state")
      
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local selection = action_state.get_selected_entry()
        vim.api.nvim_win_set_cursor(0, {selection.value.line, 0})
      end)
      
      return true
    end,
  }):find()
end

-- Register the cell picker command
vim.api.nvim_create_user_command("QuenchCells", create_cell_picker, {})

-- ============================================================================
-- HELPFUL COMMANDS
-- ============================================================================

-- Create user commands for common actions
vim.api.nvim_create_user_command("QuenchExample", function()
  vim.cmd("edit " .. vim.fn.stdpath("data") .. "/site/pack/*/opt/quench.nvim/example/quick-start.py")
end, { desc = "Open Quench example file" })

vim.api.nvim_create_user_command("QuenchHelp", function()
  print("Quench Plugin Help:")
  print("  :call QuenchRunCell() - Execute current cell")
  print("  :QuenchStatus         - Show plugin status")
  print("  :QuenchStop          - Stop plugin")
  print("  :QuenchExample       - Open example file")
  local host = vim.g.quench_nvim_web_server_host or "127.0.0.1"
  local port = vim.g.quench_nvim_web_server_port or 8765
  print("  Browser: http://" .. host .. ":" .. port .. "?kernel_id=<ID>")
end, { desc = "Show Quench help" })

-- ============================================================================
-- CONFIGURATION VALIDATION
-- ============================================================================

-- Check if plugin is properly installed
vim.defer_fn(function()
  local has_quench = vim.fn.exists(":HelloWorld") == 2
  if not has_quench then
    vim.notify("Quench plugin not found. Run :UpdateRemotePlugins and restart Neovim.", vim.log.levels.WARN)
  end
end, 2000)

print("Quench configuration loaded! Use :QuenchHelp for usage info.")