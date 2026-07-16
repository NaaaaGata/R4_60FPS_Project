local Telemetry = require("telemetry")

local Runner = {}
Runner.__index = Runner

function Runner.new(host, protocol)
    return setmetatable({ host = host, protocol = protocol, vblank = 0, running = true }, Runner)
end

function Runner:on_vblank()
    self.vblank = self.vblank + 1
    self.protocol:send(Telemetry.vblank(self.vblank, self.host))
end

function Runner:dispatch(request)
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

