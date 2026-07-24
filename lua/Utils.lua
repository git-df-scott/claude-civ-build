-- Utils.lua — minimal JSON encoder/decoder for Civ 6 UI Lua (no require, no io).
-- NOTE (verified in-engine 2026-07-16): type(io)==nil and os.remove==nil in this
-- sandbox, so there are NO file helpers here. All file traffic is handled by the
-- Python daemon across the tuner socket; this module only does JSON.

BridgeJSON = {}

local function esc(s)
  s = string.gsub(s, "\\", "\\\\")
  s = string.gsub(s, '"', '\\"')
  s = string.gsub(s, "\n", "\\n")
  s = string.gsub(s, "\r", "\\r")
  s = string.gsub(s, "\t", "\\t")
  return s
end

function BridgeJSON.encode(v)
  local t = type(v)
  if v == nil then
    return "null"
  elseif t == "number" or t == "boolean" then
    return tostring(v)
  elseif t == "string" then
    return '"' .. esc(v) .. '"'
  elseif t == "table" then
    -- array if [1..n] contiguous
    local n = 0
    for _ in pairs(v) do n = n + 1 end
    if n == #v then
      local parts = {}
      for i = 1, #v do parts[i] = BridgeJSON.encode(v[i]) end
      return "[" .. table.concat(parts, ",") .. "]"
    else
      local parts = {}
      for k, val in pairs(v) do
        parts[#parts + 1] = '"' .. esc(tostring(k)) .. '":' .. BridgeJSON.encode(val)
      end
      return "{" .. table.concat(parts, ",") .. "}"
    end
  end
  return "null"
end

-- Decoder: small recursive-descent parser, enough for command payloads.
local function skip(s, i)
  while i <= #s and string.find(" \t\r\n", string.sub(s, i, i), 1, true) do i = i + 1 end
  return i
end

local parse_value

local function parse_string(s, i)
  local out, j = {}, i + 1
  while j <= #s do
    local c = string.sub(s, j, j)
    if c == '"' then return table.concat(out), j + 1 end
    if c == "\\" then
      local e = string.sub(s, j + 1, j + 1)
      if e == "n" then out[#out + 1] = "\n"
      elseif e == "t" then out[#out + 1] = "\t"
      elseif e == "r" then out[#out + 1] = "\r"
      else out[#out + 1] = e end
      j = j + 2
    else
      out[#out + 1] = c
      j = j + 1
    end
  end
  return nil, i
end

local function parse_number(s, i)
  local j = i
  while j <= #s and string.find("-+.eE0123456789", string.sub(s, j, j), 1, true) do j = j + 1 end
  return tonumber(string.sub(s, i, j - 1)), j
end

parse_value = function(s, i)
  i = skip(s, i)
  local c = string.sub(s, i, i)
  if c == '"' then return parse_string(s, i) end
  if c == "{" then
    local obj = {}
    i = skip(s, i + 1)
    if string.sub(s, i, i) == "}" then return obj, i + 1 end
    while true do
      local k; k, i = parse_string(s, skip(s, i))
      i = skip(s, i)
      i = i + 1 -- ':'
      local v; v, i = parse_value(s, i)
      obj[k] = v
      i = skip(s, i)
      local d = string.sub(s, i, i)
      i = i + 1
      if d == "}" then return obj, i end
    end
  end
  if c == "[" then
    local arr = {}
    i = skip(s, i + 1)
    if string.sub(s, i, i) == "]" then return arr, i + 1 end
    while true do
      local v; v, i = parse_value(s, i)
      arr[#arr + 1] = v
      i = skip(s, i)
      local d = string.sub(s, i, i)
      i = i + 1
      if d == "]" then return arr, i end
    end
  end
  if string.sub(s, i, i + 3) == "true" then return true, i + 4 end
  if string.sub(s, i, i + 4) == "false" then return false, i + 5 end
  if string.sub(s, i, i + 3) == "null" then return nil, i + 4 end
  return parse_number(s, i)
end

function BridgeJSON.decode(s)
  local ok, v = pcall(function()
    local val = select(1, parse_value(s, 1))
    return val
  end)
  if ok then return v end
  return nil
end
