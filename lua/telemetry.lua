local Telemetry = {}

function Telemetry.vblank(index, host)
    local registers = host:get_registers()
    return {
        kind = "event",
        event = "vblank",
        vblank_index = index,
        monotonic_timestamp = host:monotonic_time(),
        wall_clock_timestamp = host:wall_time(),
        pc = registers.pc,
        ra = registers.ra,
        sp = registers.sp,
        gprs = registers.gprs,
        cpu_cycles = host:get_cpu_cycles(),
        watch_values = host:sample_watches(),
        display_buffer = host:display_buffer(),
        gpu_hash = host:gpu_hash(),
        emulator_status = "running",
        dropped_event_count = host:dropped_event_count(),
    }
end

return Telemetry
