-- Deployment boundary for PCSX-Redux. A small host shim must map the installed
-- emulator build's Lua API to the methods consumed by experiment_runner.lua.
-- Keeping this explicit prevents an unverified API guess from touching RAM.
local host = rawget(_G, "R4_AUTOLAB_HOST")
assert(host, "R4_AUTOLAB_HOST shim is not installed; see docs/SETUP.md")

local Protocol = require("protocol")
local Runner = require("experiment_runner")
local protocol = Protocol.new(host:writer(), host:json_codec())
local runner = Runner.new(host, protocol)

host:on_vblank(function() runner:on_vblank() end)
host:request_loop(function(request) runner:dispatch(request) end)
