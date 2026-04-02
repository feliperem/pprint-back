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

-- Atualiza rate limit
redis.call('SET', rateLimitKey, currentTime, 'EX', 1)

-- Registra ação para persistência
redis.call('LPUSH', 'draw_log:' .. imageId, userId .. ':' .. pixelKey .. ':' .. color .. ':' .. tool .. ':' .. timestamp)

-- Remoção de histórico antigo (mantém apenas últimos 1000)
redis.call('LTRIM', 'draw_log:' .. imageId, 0, 999)

local newPixels = redis.call('GET', pixelsKey)

return {1, newPixels, prevColor or "empty"}
"""

# Script para recuperar pixels com controle de tempo
RECOVER_PIXELS_SCRIPT = """
local userId = KEYS[1]
local pixelsMax = tonumber(ARGV[1])
local currentTime = tonumber(ARGV[2])
local recoveryInterval = tonumber(ARGV[3])

local pixelsKey = "pixels:" .. userId
local lastResetKey = "last_pixel_reset:" .. userId

local currentPixels = tonumber(redis.call('GET', pixelsKey) or 0)
local lastReset = tonumber(redis.call('GET', lastResetKey) or currentTime)

-- Se está no máximo, não recupera
if currentPixels >= pixelsMax then
  return {currentPixels, 0}
end

-- Calcula tempo decorrido e pixels ganhos
local timeElapsed = currentTime - lastReset
local pixelsGained = math.floor(timeElapsed / recoveryInterval)

if pixelsGained == 0 then
  return {currentPixels, 0}
end

-- Atualiza pixels
local newPixels = math.min(currentPixels + pixelsGained, pixelsMax)
redis.call('SET', pixelsKey, newPixels)

-- Atualiza último reset
redis.call('SET', lastResetKey, currentTime)

return {newPixels, pixelsGained}
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
  local currentPixels = tonumber(redis.call('GET', pixelsKey))
  return {0, currentPixels}
end
"""
