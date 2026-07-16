local Protocol = {}
Protocol.__index = Protocol

function Protocol.new(writer, codec)
    assert(writer and writer.write and writer.flush, "writer with write/flush is required")
    assert(codec and codec.encode and codec.decode, "JSON codec is required")
    return setmetatable({ writer = writer, codec = codec, sequence = 0, version = 1 }, Protocol)
end

function Protocol:send(message)
    self.sequence = self.sequence + 1
    message.protocol_version = self.version
    message.sequence = self.sequence
    self.writer:write(self.codec.encode(message))
    self.writer:write("\n")
    self.writer:flush()
end

function Protocol:response(request, ok, payload, err)
    self:send({
        kind = "response",
        request_id = request.request_id,
        ok = ok,
        payload = payload or {},
        error = err,
    })
end

return Protocol

