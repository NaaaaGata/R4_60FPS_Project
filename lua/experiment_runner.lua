local Runner = {}
Runner.__index = Runner

function Runner.new(host, protocol, telemetry)
    return setmetatable({ host = host, protocol = protocol, telemetry = telemetry, vblank = 0, running = true }, Runner)
end

function Runner:on_vblank()
    self.vblank = self.vblank + 1
    self.protocol:send(self.telemetry.vblank(self.vblank, self.host))
end

function Runner:dispatch(request)
    print('R4 AutoLab handling request ' .. tostring(request.operation))
    local ok, result = pcall(function()
        return self.host:dispatch(request.operation, request.payload or {})
    end)
    if ok then
        self.protocol:response(request, true, result or {})
    else
        self.protocol:response(request, false, {}, { code = "HOST_ERROR", message = tostring(result) })
    end
end

return Runner
