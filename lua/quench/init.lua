---@class QuenchOpts
---@field web_server? { host?: string, port?: number }
---@field cell_delimiter? string

---@class CustomModule
local M = {}

---@param opts QuenchOpts
M.setup = function(opts)
  opts = opts or {}

  if opts.web_server then
    if opts.web_server.host then
      vim.g.quench_nvim_web_server_host = opts.web_server.host
    end
    if opts.web_server.port then
      vim.g.quench_nvim_web_server_port = opts.web_server.port
    end
  end

  if opts.cell_delimiter then
    vim.g.quench_nvim_cell_delimiter = opts.cell_delimiter
  end

  M.opts = opts
end

return M
