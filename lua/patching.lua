local Patching = {}

function Patching.apply(host, address, expected, replacement)
    local actual = host:read_memory(address, #expected)
    assert(actual == expected, "original bytes mismatch")
    host:write_memory(address, replacement)
    return { address = address, original = actual }
end

function Patching.restore(host, receipt)
    host:write_memory(receipt.address, receipt.original)
end

return Patching

