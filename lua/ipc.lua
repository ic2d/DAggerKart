--[[
ipc.lua

Conexão com o Python por named pipes do Windows, abertos com io.open (o Lua 5.5 do Mupen não tem
sockets, e as DLLs antigas do LuaSocket eram Lua 5.1 32-bit).

O Python cria dois pipes de bytes: \\.\pipe\<nome>_req (Python -> Lua, comandos) e
\\.\pipe\<nome>_resp (Lua -> Python, respostas). Uma linha por mensagem.
O nome vem da variável de ambiente NK_PIPE (permite vários emuladores em paralelo).
]]--

local ipc = {}

local Client = {}
Client.__index = Client

function ipc.connect(name)
  name = name or os.getenv("NK_PIPE") or "neuralkart"
  local cmd, err = io.open("\\\\.\\pipe\\" .. name .. "_req", "rb")
  if cmd == nil then return nil, err end
  local resp, err2 = io.open("\\\\.\\pipe\\" .. name .. "_resp", "wb")
  if resp == nil then cmd:close(); return nil, err2 end
  return setmetatable({cmd = cmd, resp = resp}, Client)
end

-- Bloqueia até chegar um comando (o emulador fica parado enquanto isso). nil = Python desconectou.
function Client:receive()
  return self.cmd:read("l")
end

function Client:send(line)
  self.resp:write(line, "\n")
  self.resp:flush()
end

function Client:close()
  pcall(function() self.cmd:close() end)
  pcall(function() self.resp:close() end)
end

return ipc
