"""
Lua scripts para operações atômicas no Redis
"""

# Script para pintar um pixel atomicamente
DRAW_PIXEL_SCRIPT = """
local imageId = KEYS[1]
local userId = ARGV[1]
local pixelKey = ARGV[2]
local color = ARGV[3]
local tool = ARGV[4]
local timestamp = ARGV[5]

-- Verifica pixels disponíveis
local pixelsKey = "pixels:" .. userId
local pixels = redis.call('GET', pixelsKey)

if not pixels or tonumber(pixels) <= 0 then
  return {0, "out_of_pixels"}
end

-- Verifica rate limit
local rateLimitKey = "rate_limit:" .. userId
local lastDraw = redis.call('GET', rateLimitKey)
local currentTime = tonumber(timestamp)

if lastDraw and (currentTime - tonumber(lastDraw)) < 100 then
  return {0, "rate_limit_exceeded"}
end

-- Tenta "pintar" (set hash)
local canvasKey = "canvas:" .. imageId
local prevColor = redis.call('HGET', canvasKey, pixelKey)

redis.call('HSET', canvasKey, pixelKey, color)

-- Decrementa pixels
redis.call('DECR', pixelsKey)

-- Reinicia a ancora de recuperacao a partir do ultimo envio efetivo
redis.call('SET', 'last_pixel_reset:' .. userId, math.floor(currentTime / 1000))

-- Atualiza rate limit
redis.call('SET', rateLimitKey, currentTime, 'EX', 1)

-- Registra ação para persistência
redis.call('LPUSH', 'draw_log:' .. imageId, userId .. ':' .. pixelKey .. ':' .. color .. ':' .. tool .. ':' .. timestamp)

-- Remoção de histórico antigo (mantém apenas últimos 1000)
redis.call('LTRIM', 'draw_log:' .. imageId, 0, 999)

local newPixels = redis.call('GET', pixelsKey)

return {1, newPixels, prevColor or "empty"}
"""


DRAW_BATCH_SCRIPT = """
local imageId = KEYS[1]
local userId = ARGV[1]
local drawCount = tonumber(ARGV[2])
local submittedAt = tonumber(ARGV[3])

local pixelsKey = "pixels:" .. userId
local pixels = tonumber(redis.call('GET', pixelsKey) or 0)

if not drawCount or drawCount <= 0 then
  return {0, pixels, "invalid_draw_batch"}
end

if pixels < drawCount then
  return {0, pixels, "out_of_pixels"}
end

local canvasKey = "canvas:" .. imageId
local argIndex = 4

for i = 1, drawCount do
  local pixelKey = ARGV[argIndex]
  local color = ARGV[argIndex + 1]
  local tool = ARGV[argIndex + 2]
  local timestamp = ARGV[argIndex + 3]

  redis.call('HSET', canvasKey, pixelKey, color)
  redis.call('LPUSH', 'draw_log:' .. imageId, userId .. ':' .. pixelKey .. ':' .. color .. ':' .. tool .. ':' .. timestamp)

  argIndex = argIndex + 4
end

redis.call('LTRIM', 'draw_log:' .. imageId, 0, 999)

local newPixels = pixels - drawCount
redis.call('SET', pixelsKey, newPixels)
redis.call('SET', 'last_pixel_reset:' .. userId, submittedAt)
redis.call('DEL', 'rate_limit:' .. userId)

return {1, newPixels, drawCount}
"""

# Script para recuperar pixels com controle de tempo
RECOVER_PIXELS_SCRIPT = """
local userId = KEYS[1]
local pixelsMax = tonumber(ARGV[1])
local currentTime = tonumber(ARGV[2])
local recoveryInterval = tonumber(ARGV[3])

local pixelsKey = "pixels:" .. userId
local lastResetKey = "last_pixel_reset:" .. userId

local currentPixels = tonumber(redis.call('GET', pixelsKey) or pixelsMax)
local lastReset = tonumber(redis.call('GET', lastResetKey) or currentTime)

if currentPixels > pixelsMax then
  currentPixels = pixelsMax
  redis.call('SET', pixelsKey, currentPixels)
end

-- Se está no máximo, não recupera
if currentPixels >= pixelsMax then
  redis.call('SET', lastResetKey, currentTime)
  return {currentPixels, 0, 0}
end

-- Calcula tempo decorrido e pixels ganhos
local timeElapsed = currentTime - lastReset
local pixelsGained = math.floor(timeElapsed / recoveryInterval)

local nextPixelIn = recoveryInterval - (timeElapsed % recoveryInterval)

if pixelsGained == 0 then
  return {currentPixels, 0, nextPixelIn}
end

-- Atualiza pixels
local newPixels = math.min(currentPixels + pixelsGained, pixelsMax)
redis.call('SET', pixelsKey, newPixels)

-- Atualiza último reset
if newPixels >= pixelsMax then
  redis.call('SET', lastResetKey, currentTime)
  nextPixelIn = 0
else
  local consumedIntervals = pixelsGained * recoveryInterval
  local newAnchor = lastReset + consumedIntervals
  redis.call('SET', lastResetKey, newAnchor)
  nextPixelIn = recoveryInterval - (currentTime - newAnchor)
end

return {newPixels, pixelsGained, nextPixelIn}
"""

# Script para inicializar usuário se não existe
INIT_USER_SCRIPT = """
local userId = KEYS[1]
local pixelsMax = tonumber(ARGV[1])
local currentTime = tonumber(ARGV[2])

local pixelsKey = "pixels:" .. userId
local lastResetKey = "last_pixel_reset:" .. userId

-- Se não existe, inicializa
if redis.call('EXISTS', pixelsKey) == 0 then
  redis.call('SET', pixelsKey, pixelsMax)
  redis.call('SET', lastResetKey, currentTime)
  return {1, pixelsMax}
else
  local currentPixels = tonumber(redis.call('GET', pixelsKey) or pixelsMax)
  if currentPixels > pixelsMax then
    currentPixels = pixelsMax
    redis.call('SET', pixelsKey, currentPixels)
  end
  if redis.call('EXISTS', lastResetKey) == 0 then
    redis.call('SET', lastResetKey, currentTime)
  end
  return {0, currentPixels}
end
"""
