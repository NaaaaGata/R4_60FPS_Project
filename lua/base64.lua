local Base64 = {}
local alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

function Base64.encode(data)
    return ((data:gsub('.', function(character)
        local byte = character:byte()
        local bits = ''
        for index = 8, 1, -1 do bits = bits .. (byte % 2 ^ index - byte % 2 ^ (index - 1) > 0 and '1' or '0') end
        return bits
    end) .. '0000'):gsub('%d%d%d?%d?%d?%d?', function(bits)
        if #bits < 6 then return '' end
        local value = 0
        for index = 1, 6 do value = value + (bits:sub(index, index) == '1' and 2 ^ (6 - index) or 0) end
        return alphabet:sub(value + 1, value + 1)
    end) .. ({ '', '==', '=' })[#data % 3 + 1])
end

function Base64.decode(data)
    assert(type(data) == 'string' and not data:find('[^' .. alphabet .. '=]'), 'invalid base64')
    data = data:gsub('=', '')
    return (data:gsub('.', function(character)
        local value = alphabet:find(character, 1, true) - 1
        local bits = ''
        for index = 6, 1, -1 do bits = bits .. (value % 2 ^ index - value % 2 ^ (index - 1) > 0 and '1' or '0') end
        return bits
    end):gsub('%d%d%d?%d?%d?%d?%d?%d?', function(bits)
        if #bits ~= 8 then return '' end
        local value = 0
        for index = 1, 8 do value = value + (bits:sub(index, index) == '1' and 2 ^ (8 - index) or 0) end
        return string.char(value)
    end))
end

return Base64
