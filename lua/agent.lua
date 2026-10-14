--[[
agent.lua — "controle remoto" do Mupen para o Python (nk/emulator.py).

Toda a lógica (busca, coleta de dados, rede neural) fica no Python. Este script só executa
comandos, um por linha, e responde uma linha. Enquanto espera um comando o emulador fica parado,
então Python e jogo andam em lockstep (determinístico).

Comandos:
  PING                                  -> OK
  STATE                                 -> OK <estado>
  RUN n buttons x y [n buttons x y ...] [SAVE slot]
                                        -> OK <estado>   segure cada input por n frames; com SAVE,
                                                         salva o estado no último frame (sem custo)
  SPEED mode                            -> OK            0 normal, 1 fast, 2 ultra
  SAVE slot | LOAD slot | FREE slot     -> OK            savestates em memória (SAVE avulso faz o
                                                         jogo andar 1 frame; prefira RUN ... SAVE)
  SAVEFILE caminho | LOADFILE caminho   -> OK
  QUIT                                  -> OK            encerra o script
Erros respondem "ERR <mensagem>".

<estado> = progress velocity x y z timer course mode input_frame vi_frame
`buttons` é uma máscara de bits (BUTTONS abaixo); x/y são o analógico (-128..127).
]]--
package.path = debug.getinfo(1, "S").source:sub(2):match("^(.*)[\\/]") .. "\\?.lua;" .. package.path

local mk = require("mk")
local ipc = require("ipc")

local BUTTONS = {"A", "B", "Z", "R", "L", "start", "Cup", "Cdown", "Cleft", "Cright",
  "up", "down", "left", "right"}

-- Endereços do Mario Kart 64 (USA), endereço virtual 0x80000000 + offset da RDRAM.
local ADDR_PROGRESS = 0x801644D0 -- float: voltas completadas (0 a 3, fracionário)
local ADDR_VELOCITY = 0x800F6BBC -- float
local ADDR_POS = {0x800F69A4, 0x800F69A8, 0x800F69AC} -- float x, y, z do jogador
local ADDR_TIMER = 0x800DC598 -- float: tempo de corrida (s)
local ADDR_COURSE = 0x800DC5A1 -- u8
local ADDR_MODE = 0x800DC53F -- u8 (0 GP, 1 TT, 2 VS, 3 Battle)

local function state()
  return string.format("%.7g %.7g %.7g %.7g %.7g %.7g %d %d %d %d",
    memory.readfloat(ADDR_PROGRESS), memory.readfloat(ADDR_VELOCITY),
    memory.readfloat(ADDR_POS[1]), memory.readfloat(ADDR_POS[2]), memory.readfloat(ADDR_POS[3]),
    memory.readfloat(ADDR_TIMER), memory.readbyte(ADDR_COURSE), memory.readbyte(ADDR_MODE),
    joypad.count(), emu.framecount())
end

local function input_table(buttons, x, y)
  local t = {X = x, Y = y}
  for i, name in ipairs(BUTTONS) do
    if buttons & (1 << (i - 1)) ~= 0 then t[name] = true end
  end
  return t
end

local slots = {}

local function split(line)
  local cmd, rest = line:match("^(%S+)%s*(.*)$")
  return cmd, rest
end

local function numbers(s)
  local t = {}
  for v in s:gmatch("%S+") do t[#t + 1] = math.tointeger(tonumber(v)) or tonumber(v) end
  return t
end

local handlers = {}

function handlers.PING() return "OK" end

function handlers.STATE() return "OK " .. state() end

-- Último input aplicado: mantido nos frames em que o Lua espera um savestate (ver mk.lua).
local last_input = {}

function handlers.RUN(args)
  local inputs, save_slot = args:match("^(.-)%s*SAVE%s+(%S+)%s*$")
  if inputs == nil then inputs = args end
  local v = numbers(inputs)
  if #v == 0 or #v % 4 ~= 0 then return "ERR RUN espera grupos de 'n buttons x y' [SAVE slot]" end
  local total = 0
  for i = 1, #v, 4 do total = total + v[i] end
  local frame = 0
  for i = 1, #v, 4 do
    local t = input_table(v[i + 1], v[i + 2], v[i + 3])
    last_input = t
    for _ = 1, v[i] do
      frame = frame + 1
      if save_slot ~= nil and frame == total then
        -- Salva no último frame, com o input da ação: o save acontece no fim deste frame e não custa
        -- frame extra (um SAVE separado faria o jogo andar 1 frame a mais).
        local data = mk.save_state(t)
        if data == nil or #data == 0 then return "ERR falha ao salvar" end
        slots[save_slot] = data
      else
        joypad.set(t)
        mk.frameadvance()
      end
    end
  end
  return "OK " .. state()
end

function handlers.SPEED(args)
  emu.set_speed_mode(numbers(args)[1])
  return "OK"
end

function handlers.SAVE(slot)
  -- Atenção: um SAVE separado faz o jogo andar 1 frame (com o último input). Para salvar sem mudar
  -- o ritmo do jogo, use "RUN ... SAVE slot".
  local data = mk.save_state(last_input)
  if data == nil or #data == 0 then return "ERR falha ao salvar" end
  slots[slot] = data
  return "OK"
end

function handlers.LOAD(slot)
  if slots[slot] == nil then return "ERR slot vazio: " .. slot end
  mk.load_state(slots[slot])
  return "OK"
end

function handlers.FREE(slot)
  slots[slot] = nil
  return "OK"
end

function handlers.SAVEFILE(path) mk.save_state_file(path); return "OK" end
function handlers.LOADFILE(path) mk.load_state_file(path); return "OK" end

mk.run(function()
  local client, err = ipc.connect()
  if client == nil then
    print("agent: falha ao conectar no Python: " .. tostring(err))
    return
  end
  mk.onexit(function() client:close() end)
  client:send("HELLO 1")

  while true do
    local line = client:receive()
    if line == nil then break end -- Python desconectou
    local cmd, args = split(line)
    if cmd == "QUIT" then client:send("OK"); break end
    local handler = handlers[cmd]
    local ok, reply = pcall(function()
      if handler == nil then return "ERR comando desconhecido: " .. tostring(cmd) end
      return handler(args)
    end)
    client:send(ok and reply or ("ERR " .. tostring(reply):gsub("\n", " ")))
  end
end)
