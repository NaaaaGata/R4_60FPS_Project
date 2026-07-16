local Host = {}
Host.__index = Host

local MAX_MESSAGE_BYTES = 1024 * 1024
local MAX_MEMORY_BYTES = 65536
local ADDRESS_SPACE_SIZE = 0x100000000

local function integer(value, name)
    assert(type(value) == 'number' and value >= 0 and value % 1 == 0, name .. ' must be a non-negative integer')
    return value
end

local function safe_memory_range(address, size)
    address = integer(address, 'address')
    size = integer(size, 'size')
    assert(size > 0 and size <= MAX_MEMORY_BYTES, 'size is outside the safe request limit')
    assert(address < ADDRESS_SPACE_SIZE and address <= ADDRESS_SPACE_SIZE - size, 'memory range overflow')
    return address, size
end

local function register_snapshot()
    local registers = PCSX.getRegisters()
    local gpr = registers.GPR.n
    local values = {
        gp = tonumber(gpr.gp),
        a0 = tonumber(gpr.a0), a1 = tonumber(gpr.a1), a2 = tonumber(gpr.a2), a3 = tonumber(gpr.a3),
        v0 = tonumber(gpr.v0), v1 = tonumber(gpr.v1),
        s0 = tonumber(gpr.s0), s1 = tonumber(gpr.s1), s2 = tonumber(gpr.s2), s3 = tonumber(gpr.s3),
        s4 = tonumber(gpr.s4), s5 = tonumber(gpr.s5), s6 = tonumber(gpr.s6), s7 = tonumber(gpr.s7),
        t0 = tonumber(gpr.t0), t1 = tonumber(gpr.t1), t2 = tonumber(gpr.t2), t3 = tonumber(gpr.t3),
        t4 = tonumber(gpr.t4), t5 = tonumber(gpr.t5), t6 = tonumber(gpr.t6), t7 = tonumber(gpr.t7),
        t8 = tonumber(gpr.t8), t9 = tonumber(gpr.t9),
    }
    return { pc = tonumber(registers.pc), ra = tonumber(gpr.ra), sp = tonumber(gpr.sp), gprs = values }
end

function Host.new(json, base64)
    assert(luv and luv.new_tcp, 'PCSX-Redux Luv bindings are unavailable')
    local host = os.getenv('R4_AUTOLAB_IPC_HOST')
    local port = tonumber(os.getenv('R4_AUTOLAB_IPC_PORT') or '')
    assert(host == '127.0.0.1', 'IPC host must be exactly 127.0.0.1')
    assert(port and port > 0 and port < 65536, 'invalid IPC port')
    local output = os.getenv('R4_AUTOLAB_OUTPUT_DIR')
    assert(output and #output > 0, 'missing output directory')
    local self = setmetatable({
        json = json,
        base64 = base64,
        ipc_host = host,
        ipc_port = port,
        output_directory = output:gsub('/+$', ''),
        expected_token = os.getenv('R4_AUTOLAB_SESSION_TOKEN'),
        client = luv.new_tcp(),
        connected = false,
        closed = false,
        outgoing = {},
        incoming = '',
        incoming_sequence = -1,
        dropped = 0,
        vblank_count = 0,
        breakpoints = {},
        breakpoint_sequence = 0,
        listeners = {},
        memory = PCSX.getMemoryAsFile(),
        event_sender = nil,
        vblank_target = nil,
        watches = {},
    }, Host)
    return self
end

function Host:json_codec() return self.json end

function Host:writer()
    local owner = self
    return {
        write = function(_, data)
            if owner.closed then return end
            if owner.connected then
                luv.write(owner.client, data, function(error)
                    if error then owner.dropped = owner.dropped + 1 end
                end)
            elseif #owner.outgoing < 64 then
                owner.outgoing[#owner.outgoing + 1] = data
            else
                owner.dropped = owner.dropped + 1
            end
        end,
        flush = function(_) end,
    }
end

function Host:set_event_sender(sender) self.event_sender = sender end

function Host:_emit(message)
    if self.event_sender then self.event_sender(message) end
end

function Host:_close_socket()
    if self.closed then return end
    self.closed = true
    self.connected = false
    pcall(function() luv.read_stop(self.client) end)
    pcall(function() luv.close(self.client) end)
    pcall(function() self.memory:close() end)
end

function Host:_reject_protocol(message)
    self:_emit({ kind = 'event', event = 'protocol_error', message = tostring(message) })
    self:_close_socket()
end

function Host:_handle_chunk(chunk, callback)
    print('R4 AutoLab IPC received ' .. tostring(#chunk) .. ' bytes')
    self.incoming = self.incoming .. chunk
    if #self.incoming > MAX_MESSAGE_BYTES and not self.incoming:find('\n', 1, true) then
        return self:_reject_protocol('unterminated message exceeds size limit')
    end
    while true do
        local newline = self.incoming:find('\n', 1, true)
        if not newline then return end
        local line = self.incoming:sub(1, newline - 1)
        self.incoming = self.incoming:sub(newline + 1)
        if #line > MAX_MESSAGE_BYTES then return self:_reject_protocol('message exceeds size limit') end
        if #line > 0 then
            local ok, request = pcall(self.json.decode, line)
            if not ok or type(request) ~= 'table' then return self:_reject_protocol(request) end
            if request.protocol_version ~= 1 or request.kind ~= 'request' or type(request.request_id) ~= 'string' or type(request.operation) ~= 'string' then
                return self:_reject_protocol('invalid request envelope')
            end
            if type(request.sequence) ~= 'number' or request.sequence <= self.incoming_sequence then
                return self:_reject_protocol('duplicate or out-of-order sequence')
            end
            self.incoming_sequence = request.sequence
            print('R4 AutoLab IPC dispatching ' .. request.operation)
            callback(request)
        end
    end
end

function Host:request_loop(callback)
    luv.tcp_connect(self.client, self.ipc_host, self.ipc_port, function(error)
        print('R4 AutoLab IPC connect callback')
        PCSX.nextTick(function()
            if error then
                printError('R4 AutoLab IPC connect failed: ' .. tostring(error))
                return self:_close_socket()
            end
            self.connected = true
            print('R4 AutoLab IPC connected to 127.0.0.1')
            luv.read_start(self.client, function(read_error, chunk)
                print('R4 AutoLab IPC read callback')
                PCSX.nextTick(function()
                    if read_error then
                        printError('R4 AutoLab IPC read failed: ' .. tostring(read_error))
                        return self:_close_socket()
                    end
                    if not chunk then return self:_close_socket() end
                    local ok, message = pcall(function() self:_handle_chunk(chunk, callback) end)
                    if not ok then self:_reject_protocol(message) end
                end)
            end)
            for _, data in ipairs(self.outgoing) do luv.write(self.client, data) end
            self.outgoing = {}
        end)
    end)
end

function Host:on_vblank(callback)
    local listener = PCSX.Events.createEventListener('GPU::Vsync', function()
        self.vblank_count = self.vblank_count + 1
        local current = self.vblank_count
        PCSX.nextTick(function()
            local ok, message = pcall(callback)
            if not ok then
                self.dropped = self.dropped + 1
                printError('R4 AutoLab VBlank callback failed: ' .. tostring(message))
            end
            if self.vblank_target and current >= self.vblank_target then
                self.vblank_target = nil
                PCSX.pauseEmulator()
                self:_emit({ kind = 'event', event = 'vblank_target_reached', vblank_index = current })
            end
        end)
    end)
    self.listeners[#self.listeners + 1] = listener
end

function Host:install_quitting_listener()
    local listener = PCSX.Events.createEventListener('Quitting', function() self:_close_socket() end)
    self.listeners[#self.listeners + 1] = listener
end

function Host:monotonic_time() return tonumber(luv.hrtime()) / 1000000000 end
function Host:wall_time() return os.date('!%Y-%m-%dT%H:%M:%SZ') end
function Host:sample_watches()
    local values = {}
    for _, watch in ipairs(self.watches) do
        local ok, value = pcall(function()
            if watch.width == 1 then return self:read_u8(watch.address) end
            if watch.width == 2 then return self:read_u16(watch.address) end
            if watch.width == 4 then return self:read_u32(watch.address) end
            error('unsupported watch width')
        end)
        values[watch.name] = ok and value or ('ERROR:' .. tostring(value))
    end
    return values
end
function Host:display_buffer() return -1 end
function Host:gpu_hash() return 'unavailable-phase-3a' end
function Host:dropped_event_count() return self.dropped end
function Host:get_registers() return register_snapshot() end

function Host:read_memory(address, size)
    address, size = safe_memory_range(address, size)
    local buffer = self.memory:readAt(size, address)
    local data = tostring(buffer)
    assert(#data == size, 'short memory read')
    return data
end

function Host:read_u8(address)
    return self:read_memory(address, 1):byte(1)
end

function Host:read_u16(address)
    local a, b = self:read_memory(address, 2):byte(1, 2)
    return a + b * 0x100
end

function Host:read_u32(address)
    local a, b, c, d = self:read_memory(address, 4):byte(1, 4)
    return a + b * 0x100 + c * 0x10000 + d * 0x1000000
end

function Host:write_memory(address, data)
    assert(type(data) == 'string', 'memory data must be a byte string')
    address = safe_memory_range(address, #data)
    local written = self.memory:writeAt(data, address)
    assert(tonumber(written) == #data, 'short memory write')
end

function Host:set_breakpoint(specification)
    assert(os.getenv('R4_AUTOLAB_INTERPRETER') == '1' and os.getenv('R4_AUTOLAB_DEBUGGER') == '1', 'breakpoints require interpreter and debugger')
    local access = ({ execute = 'Exec', read = 'Read', write = 'Write' })[specification.access]
    assert(access, 'breakpoint access must be execute, read, or write')
    local address = integer(specification.address, 'breakpoint address')
    local width = integer(specification.width or 4, 'breakpoint width')
    assert(width > 0 and width <= MAX_MEMORY_BYTES, 'invalid breakpoint width')
    local max_hits = specification.max_hits
    if max_hits ~= nil then max_hits = integer(max_hits, 'breakpoint max hits'); assert(max_hits > 0, 'max hits must be positive') end
    local hit_count = 0
    self.breakpoint_sequence = self.breakpoint_sequence + 1
    local identifier = 'bp-' .. tostring(self.breakpoint_sequence)
    local breakpoint = PCSX.addBreakpoint(address, access, width, 'R4 AutoLab ' .. identifier, function(actual_address, actual_width, cause)
        hit_count = hit_count + 1
        local ok, message = pcall(function()
            local snapshot = register_snapshot()
            PCSX.nextTick(function()
                self:_emit({
                    kind = 'event', event = 'breakpoint', breakpoint_id = identifier,
                    access = specification.access,
                    pc = snapshot.pc, ra = snapshot.ra, sp = snapshot.sp,
                    accessed_address = tonumber(actual_address), access_width = tonumber(actual_width), cause = tostring(cause),
                })
            end)
        end)
        if not ok then printError('R4 AutoLab breakpoint callback failed: ' .. tostring(message)) end
        if max_hits and hit_count >= max_hits then return false end
    end)
    self.breakpoints[identifier] = breakpoint
    return identifier
end

function Host:clear_breakpoint(identifier)
    local breakpoint = self.breakpoints[identifier]
    assert(breakpoint, 'unknown breakpoint id')
    breakpoint:remove()
    self.breakpoints[identifier] = nil
end

function Host:_safe_output_path(path)
    assert(type(path) == 'string' and path:sub(1, #self.output_directory + 1) == self.output_directory .. '/', 'output path is outside capability run directory')
    assert(not path:find('/../', 1, true) and path:sub(-3) ~= '/..', 'output path traversal rejected')
    return path
end

function Host:capture_screenshot(raw_path)
    raw_path = self:_safe_output_path(raw_path)
    local screenshot = PCSX.GPU.takeScreenShot()
    local width = tonumber(screenshot.width)
    local height = tonumber(screenshot.height)
    local size = tonumber(screenshot.data.size)
    assert(width > 0 and height > 0 and size > 0, 'empty screenshot')
    local bytes_per_pixel = size / (width * height)
    assert(bytes_per_pixel == 2 or bytes_per_pixel == 3, 'unsupported screenshot pixel depth')
    local output = Support.File.open(raw_path, 'TRUNCATE')
    assert(output and not output:failed(), 'unable to open screenshot output')
    output:writeMoveSlice(screenshot.data)
    output:close()
    return { raw_path = raw_path, width = width, height = height, bits_per_pixel = bytes_per_pixel * 8, size = size }
end

function Host:load_state(path, format)
    assert(format == 'raw-protobuf', 'only uncompressed raw-protobuf save states are supported')
    assert(path:lower():match('%.rawstate$'), 'only explicitly uncompressed .rawstate files are accepted; UI gzip states are unsupported')
    local state = Support.extra.open(path)
    assert(state and not state:failed(), 'unable to open raw save state')
    PCSX.loadSaveState(state)
    state:close()
end

function Host:create_save_state(path, format)
    assert(format == 'raw-protobuf', 'only uncompressed raw-protobuf save states are supported')
    path = self:_safe_output_path(path)
    assert(path:lower():match('%.rawstate$'), 'raw save states must use the .rawstate extension')
    local state = PCSX.createSaveState()
    local size = tonumber(state.size)
    assert(size > 0, 'empty save state')
    local output = Support.File.open(path, 'TRUNCATE')
    assert(output and not output:failed(), 'unable to open raw save-state output')
    output:writeMoveSlice(state)
    output:close()
    return { path = path, format = format, size = size }
end

function Host:dispatch(operation, payload)
    if operation == 'handshake' then
        assert(type(self.expected_token) == 'string' and payload.session_token == self.expected_token, 'session token mismatch')
        return {
            protocol_version = 1, lua_version = tostring(_VERSION), jit_version = tostring(jit and jit.version),
            interpreter = os.getenv('R4_AUTOLAB_INTERPRETER') == '1', debugger = os.getenv('R4_AUTOLAB_DEBUGGER') == '1',
        }
    elseif operation == 'pause' then PCSX.pauseEmulator(); return { paused = true }
    elseif operation == 'resume' then PCSX.resumeEmulator(); return { resumed = true }
    elseif operation == 'shutdown' then PCSX.quit(0); return { shutting_down = true }
    elseif operation == 'get_cpu_cycles' then return { cycles = tonumber(PCSX.getCPUCycles()) }
    elseif operation == 'get_vblank_count' then return { count = self.vblank_count }
    elseif operation == 'run_vblanks' then
        local count = integer(payload.count, 'VBlank count')
        assert(count > 0, 'VBlank count must be positive')
        self.vblank_target = self.vblank_count + count
        PCSX.resumeEmulator()
        return { target = self.vblank_target }
    elseif operation == 'get_registers' then return register_snapshot()
    elseif operation == 'configure_watches' then
        assert(type(payload.watches) == 'table' and #payload.watches <= 64, 'invalid watch list')
        self.watches = {}
        for _, watch in ipairs(payload.watches) do
            local address = integer(watch.address, 'watch address')
            local width = integer(watch.width, 'watch width')
            assert(width == 1 or width == 2 or width == 4, 'watch width must be 1, 2, or 4')
            safe_memory_range(address, width)
            assert(type(watch.name) == 'string' and #watch.name > 0, 'watch name is required')
            self.watches[#self.watches + 1] = { name = watch.name, address = address, width = width }
        end
        return { configured = #self.watches }
    elseif operation == 'read_memory' then
        return { data_base64 = self.base64.encode(self:read_memory(payload.address, payload.size)) }
    elseif operation == 'write_memory' then
        self:write_memory(payload.address, self.base64.decode(payload.data_base64)); return { written = true }
    elseif operation == 'set_breakpoint' then return { breakpoint_id = self:set_breakpoint(payload) }
    elseif operation == 'clear_breakpoint' then self:clear_breakpoint(payload.breakpoint_id); return { removed = true }
    elseif operation == 'load_state' then self:load_state(payload.path, payload.format); return { loaded = true, format = payload.format }
    elseif operation == 'create_save_state' then return self:create_save_state(payload.path, payload.format)
    elseif operation == 'capture_screenshot' then return self:capture_screenshot(payload.raw_path)
    end
    error('unsupported operation: ' .. tostring(operation))
end

return Host
