-- Atomic login attempt tracking and lockout check.
-- Returns 1 if locked out, 0 if allowed.
-- KEYS[1] = lockout hash key
-- ARGV[1] = current timestamp
-- ARGV[2] = lockout window in seconds
-- ARGV[3] = max attempts threshold

local count = redis.call('HINCRBY', KEYS[1], 'count', 1)
redis.call('HSETNX', KEYS[1], 'first_attempt', ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])

if count >= tonumber(ARGV[3]) then
    return 1
end
return 0
