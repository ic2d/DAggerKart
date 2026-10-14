--[[
mk.lua

Base para escrever scripts do Mupen64-rr-lua 1.5 no estilo "loop com frameadvance()".

O Mupen é baseado em callbacks. Aqui o código principal roda numa corrotina que é retomada a cada
leitura de controle do jogo (emu.atinput); mk.frameadvance() faz yield até a próxima. Um "frame"
é um input frame (o Mario Kart 64 lê o controle a 30 Hz, a cada 2 VIs).

O Mupen trava (crash nativo) se uma função da API dele for chamada de dentro de uma corrotina,
porque ele identifica o script pelo lua_State. Por isso as tabelas da API (memory, joypad, emu, ...)
são trocadas por proxies: dentro da corrotina a chamada é repassada via yield para o thread
principal, que executa e devolve o resultado. Para quem usa, é transparente.
]]--

local mk = {}

mk.LUA_DIR = debug.getinfo(1, "S").source:sub(2):match("^(.*)[\\/]")
mk.ROOT_DIR = mk.LUA_DIR:match("^(.*)[\\/]")

-- emu.set_speed_mode. Com o plugin embutido TAS Video o Mario Kart trava em fast-forward; use o
-- GLideN64. Em ULTRA a imagem não é atualizada.
mk.SPEED_NORMAL, mk.SPEED_FAST, mk.SPEED_ULTRA = 0, 1, 2

local co = nil
local finished = false
local exit_handlers = {}

--[[ Proxy da API do Mupen ]]--

local CALL, FRAME = {}, {}
local API_TABLES = {"emu", "memory", "joypad", "wgui", "d2d", "savestate", "input", "movie", "avi",
  "iohelper", "action", "hotkey", "debugger", "clipboard"}
local API_FUNCTIONS = {"print", "tostringex", "stop"}

local function in_coroutine()
  local _, is_main = coroutine.running()
  return not is_main
end

local function proxy(f)
  return function(...)
    if not in_coroutine() then return f(...) end
    local r = coroutine.yield(CALL, f, table.pack(...))
    if not r[1] then error(r[2], 2) end
    return table.unpack(r, 2, r.n)
  end
end

if not _G.__mk_proxied then
  _G.__mk_proxied = true
  for _, name in ipairs(API_TABLES) do
    local t = _G[name]
    if type(t) == "table" then
      local p = {}
      for k, v in pairs(t) do p[k] = type(v) == "function" and proxy(v) or v end
      _G[name] = p
    end
  end
  for _, name in ipairs(API_FUNCTIONS) do
    if type(_G[name]) == "function" then _G[name] = proxy(_G[name]) end
  end
end

--[[ Corrotina / loop principal ]]--

function mk.frameadvance()
  coroutine.yield(FRAME)
end

function mk.onexit(f) table.insert(exit_handlers, f) end

local function finish()
  if finished then return end
  finished = true
  for i = #exit_handlers, 1, -1 do
    local ok, err = pcall(exit_handlers[i])
    if not ok then print("Erro no onexit: " .. tostring(err)) end
  end
  exit_handlers = {}
end

-- Retoma a corrotina e executa as chamadas de API que ela pedir, até ela avançar um frame.
local function step()
  local r = table.pack(coroutine.resume(co))
  while r[1] and r[2] == CALL do
    local result = table.pack(pcall(r[3], table.unpack(r[4], 1, r[4].n)))
    r = table.pack(coroutine.resume(co, result))
  end
  return r[1], r[2]
end

local function on_input()
  if finished or co == nil then return end
  local ok, err = step()
  if not ok then
    print("Erro no script: " .. tostring(err))
    print(debug.traceback(co))
    finish()
  elseif coroutine.status(co) == "dead" then
    finish()
  end
end

-- Executa `main` como o loop principal do script. Deve ser chamada uma única vez, no fim do script.
function mk.run(main)
  co = coroutine.create(main)
  emu.atinput(on_input)
  emu.atstop(finish)
  if emu.getpause() then emu.pause(true) end -- emu.pause(true) = despausar (API invertida)
end

--[[ Savestates (em memória ou arquivo). Bloqueiam a corrotina até terminar. ]]--

-- O savestate é executado pelo Mupen no fim do frame atual; a corrotina espera o callback.
-- `hold` = input a manter enquanto espera. ATENÇÃO: salvar faz o jogo andar 1 frame (o atual) antes
-- de capturar o estado; sem `hold`, esse frame roda sem nenhum botão e muda a dinâmica do jogo.
local function wait_savestate(start, hold)
  local done, result, data = false, nil, nil
  start(function(res, buf) done, result, data = true, res, buf end)
  while not done do
    if hold ~= nil then joypad.set(hold) end
    mk.frameadvance()
  end
  return result, data
end

function mk.save_state(hold)
  local _, data = wait_savestate(function(cb) savestate.do_memory("", "save", cb, true) end, hold)
  return data
end

function mk.load_state(buffer)
  wait_savestate(function(cb) savestate.do_memory(buffer, "load", cb, true) end)
end

function mk.save_state_file(path)
  wait_savestate(function(cb) savestate.do_file(path, "save", cb, true) end)
end

function mk.load_state_file(path)
  wait_savestate(function(cb) savestate.do_file(path, "load", cb, true) end)
end

return mk
