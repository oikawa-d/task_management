local old_value = redis.call('GET', KEYS[1])
local revoked_key
local members_key
if old_value then
    local old_data = cjson.decode(old_value)
    revoked_key = ARGV[6] .. 'refresh_family_revoked:' .. old_data.user_id .. ':' .. old_data.family_id
    members_key = ARGV[6] .. 'user_refresh:' .. old_data.user_id
    if redis.call('EXISTS', revoked_key) == 1 then
        return {2, old_data.user_id, old_data.family_id}
    end
    local new_data = cjson.decode(ARGV[3])
    new_data.user_id = old_data.user_id
    new_data.family_id = old_data.family_id
    redis.call('DEL', KEYS[1])
    redis.call(
        'SET', KEYS[3],
        cjson.encode({user_id=old_data.user_id, family_id=old_data.family_id, used_at=ARGV[5]}),
        'EX', ARGV[4]
    )
    redis.call('SET', KEYS[2], cjson.encode(new_data), 'EX', ARGV[4])
    redis.call('SREM', members_key, ARGV[1])
    redis.call('SADD', members_key, ARGV[2])
    redis.call('EXPIRE', members_key, ARGV[4])
    return {1, old_data.user_id, old_data.family_id}
end
local used_value = redis.call('GET', KEYS[3])
if used_value then
    local used_data = cjson.decode(used_value)
    revoked_key = ARGV[6] .. 'refresh_family_revoked:' .. used_data.user_id .. ':' .. used_data.family_id
    redis.call('SET', revoked_key, '1', 'EX', ARGV[4])
    return {2, used_data.user_id, used_data.family_id}
end
return {0}
