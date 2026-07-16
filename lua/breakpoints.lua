local Breakpoints = {}

function Breakpoints.set(host, specification)
    assert(specification.access == "read" or specification.access == "write" or specification.access == "execute")
    return host:set_breakpoint(specification)
end

function Breakpoints.clear(host, identifier)
    host:clear_breakpoint(identifier)
end

return Breakpoints

