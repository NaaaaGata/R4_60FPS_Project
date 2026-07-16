// @category R4AutoLab
// Establish the verified PS-X EXE execution context before auto-analysis.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import java.math.BigInteger;

public class R4Prepare extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 5) {
            throw new IllegalArgumentException("entry, gp, load address, payload length, and block name are required");
        }
        Address entry = toAddr(args[0]);
        long gpValue = Long.decode(args[1]);
        Address loadAddress = toAddr(args[2]);
        long payloadLength = Long.parseLong(args[3]);
        String blockName = args[4];
        Memory memory = currentProgram.getMemory();
        MemoryBlock payload = memory.getBlock(blockName);
        if (payload == null) throw new IllegalStateException(blockName + " block was not created");
        if (!payload.getStart().equals(loadAddress)) {
            throw new IllegalStateException(
                "binary loader base mismatch: expected " + loadAddress + " got " + payload.getStart()
            );
        }
        long actualLength = payload.getSize();
        if (actualLength != payloadLength) {
            throw new IllegalStateException(
                "binary loader length mismatch: expected " + payloadLength + " got " + actualLength
            );
        }
        createLabel(entry, "_start", true);
        currentProgram.getSymbolTable().addExternalEntryPoint(entry);
        disassemble(entry);
        if (getFunctionAt(entry) == null) createFunction(entry, "_start");
        Register gp = currentProgram.getRegister("gp");
        if (gp != null && gpValue != 0) {
            currentProgram.getProgramContext().setValue(
                gp,
                payload.getStart(),
                payload.getEnd(),
                BigInteger.valueOf(gpValue)
            );
        }
        println("R4 prepare: entry=" + entry + " gp=" + args[1] + " payload=" + payload.getStart() + "-" + payload.getEnd());
    }
}
