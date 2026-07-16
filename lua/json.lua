-- Minimal strict JSON codec for the versioned localhost IPC protocol.
local Json = {}

local escapes = {
    ['"'] = '\\"',
    ['\\'] = '\\\\',
    ['\b'] = '\\b',
    ['\f'] = '\\f',
    ['\n'] = '\\n',
    ['\r'] = '\\r',
    ['\t'] = '\\t',
}

local function encode_string(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(character)
        return escapes[character] or string.format('\\u%04x', string.byte(character))
    end) .. '"'
end

local function is_array(value)
    local maximum = 0
    local count = 0
    for key, _ in pairs(value) do
        if type(key) ~= 'number' or key < 1 or key % 1 ~= 0 then return false, 0 end
        maximum = math.max(maximum, key)
        count = count + 1
    end
    return maximum == count, maximum
end

local encode_value
encode_value = function(value, seen)
    local kind = type(value)
    if kind == 'nil' then return 'null' end
    if kind == 'boolean' then return value and 'true' or 'false' end
    if kind == 'number' then
        assert(value == value and value ~= math.huge and value ~= -math.huge, 'non-finite JSON number')
        return tostring(value)
    end
    if kind == 'string' then return encode_string(value) end
    assert(kind == 'table', 'unsupported JSON type: ' .. kind)
    assert(not seen[value], 'cyclic JSON table')
    seen[value] = true
    local array, length = is_array(value)
    local parts = {}
    if array and length > 0 then
        for index = 1, length do parts[index] = encode_value(value[index], seen) end
        seen[value] = nil
        return '[' .. table.concat(parts, ',') .. ']'
    end
    for key, item in pairs(value) do
        assert(type(key) == 'string', 'JSON object keys must be strings')
        parts[#parts + 1] = encode_string(key) .. ':' .. encode_value(item, seen)
    end
    table.sort(parts)
    seen[value] = nil
    return '{' .. table.concat(parts, ',') .. '}'
end

function Json.encode(value)
    return encode_value(value, {})
end

local function decode_error(position, message)
    error(string.format('invalid JSON at byte %d: %s', position, message), 0)
end

local function skip_space(text, position)
    local _, last = text:find('^[ \t\r\n]*', position)
    return (last or position - 1) + 1
end

local decode_value

local function decode_string(text, position)
    local output = {}
    position = position + 1
    while position <= #text do
        local byte = text:byte(position)
        if byte == 34 then return table.concat(output), position + 1 end
        if byte < 32 then decode_error(position, 'control character in string') end
        if byte == 92 then
            local escape = text:sub(position + 1, position + 1)
            local simple = { ['"'] = '"', ['\\'] = '\\', ['/'] = '/', b = '\b', f = '\f', n = '\n', r = '\r', t = '\t' }
            if simple[escape] then
                output[#output + 1] = simple[escape]
                position = position + 2
            elseif escape == 'u' then
                local digits = text:sub(position + 2, position + 5)
                if not digits:match('^%x%x%x%x$') then decode_error(position, 'bad unicode escape') end
                local code = tonumber(digits, 16)
                if code < 0x80 then
                    output[#output + 1] = string.char(code)
                elseif code < 0x800 then
                    output[#output + 1] = string.char(0xC0 + math.floor(code / 64), 0x80 + code % 64)
                else
                    output[#output + 1] = string.char(0xE0 + math.floor(code / 4096), 0x80 + math.floor(code / 64) % 64, 0x80 + code % 64)
                end
                position = position + 6
            else
                decode_error(position, 'bad escape')
            end
        else
            output[#output + 1] = string.char(byte)
            position = position + 1
        end
    end
    decode_error(position, 'unterminated string')
end

local function decode_array(text, position)
    local result = {}
    position = skip_space(text, position + 1)
    if text:sub(position, position) == ']' then return result, position + 1 end
    while true do
        local item
        item, position = decode_value(text, position)
        result[#result + 1] = item
        position = skip_space(text, position)
        local separator = text:sub(position, position)
        if separator == ']' then return result, position + 1 end
        if separator ~= ',' then decode_error(position, 'expected comma or closing bracket') end
        position = skip_space(text, position + 1)
    end
end

local function decode_object(text, position)
    local result = {}
    position = skip_space(text, position + 1)
    if text:sub(position, position) == '}' then return result, position + 1 end
    while true do
        if text:sub(position, position) ~= '"' then decode_error(position, 'expected object key') end
        local key
        key, position = decode_string(text, position)
        position = skip_space(text, position)
        if text:sub(position, position) ~= ':' then decode_error(position, 'expected colon') end
        local item
        item, position = decode_value(text, skip_space(text, position + 1))
        result[key] = item
        position = skip_space(text, position)
        local separator = text:sub(position, position)
        if separator == '}' then return result, position + 1 end
        if separator ~= ',' then decode_error(position, 'expected comma or closing brace') end
        position = skip_space(text, position + 1)
    end
end

decode_value = function(text, position)
    position = skip_space(text, position)
    local first = text:sub(position, position)
    if first == '"' then return decode_string(text, position) end
    if first == '{' then return decode_object(text, position) end
    if first == '[' then return decode_array(text, position) end
    if text:sub(position, position + 3) == 'true' then return true, position + 4 end
    if text:sub(position, position + 4) == 'false' then return false, position + 5 end
    if text:sub(position, position + 3) == 'null' then return nil, position + 4 end
    local number = text:sub(position):match('^-?%d+%.?%d*[eE]?[+-]?%d*')
    if number and #number > 0 then
        local value = tonumber(number)
        if value then return value, position + #number end
    end
    decode_error(position, 'unexpected token')
end

function Json.decode(text)
    assert(type(text) == 'string', 'JSON input must be a string')
    local value, position = decode_value(text, 1)
    position = skip_space(text, position)
    if position <= #text then decode_error(position, 'trailing content') end
    return value
end

return Json
