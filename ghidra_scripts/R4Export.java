// @category R4AutoLab
// Asset-safe JSON metadata export for headless analysis.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.block.BasicBlockModel;
import ghidra.program.model.block.CodeBlock;
import ghidra.program.model.block.CodeBlockIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.File;
import java.io.PrintWriter;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class R4Export extends GhidraScript {
    private static String quote(String value) {
        StringBuilder escaped = new StringBuilder("\"");
        for (int index = 0; index < value.length(); index++) {
            char item = value.charAt(index);
            switch (item) {
                case '\\': escaped.append("\\\\"); break;
                case '"': escaped.append("\\\""); break;
                case '\b': escaped.append("\\b"); break;
                case '\f': escaped.append("\\f"); break;
                case '\n': escaped.append("\\n"); break;
                case '\r': escaped.append("\\r"); break;
                case '\t': escaped.append("\\t"); break;
                default:
                    if (item < 0x20) escaped.append(String.format("\\u%04x", (int)item));
                    else escaped.append(item);
            }
        }
        return escaped.append('"').toString();
    }

    private static String hex(Address address) { return String.format("0x%08X", address.getOffset()); }

    private static String fileOffset(Address address, MemoryBlock payload, long sourceFileOffset) {
        if (payload == null || !payload.contains(address)) return "unknown";
        return String.format("0x%X", sourceFileOffset + address.subtract(payload.getStart()));
    }

    private static String objects(Object[] values) {
        StringBuilder result = new StringBuilder("[");
        for (int index = 0; index < values.length; index++) {
            if (index > 0) result.append(',');
            result.append(quote(String.valueOf(values[index])));
        }
        return result.append(']').toString();
    }

    private String inputHash() throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        String executable = currentProgram.getExecutablePath();
        try (java.io.InputStream stream = new java.io.FileInputStream(executable)) {
            byte[] buffer = new byte[1024 * 1024];
            int count;
            while ((count = stream.read(buffer)) > 0) digest.update(buffer, 0, count);
        }
        StringBuilder result = new StringBuilder();
        for (byte item : digest.digest()) result.append(String.format("%02x", item));
        return result.toString();
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) throw new IllegalArgumentException("output JSON path is required");
        List<String> requested = new ArrayList<>();
        for (int index = 1; index < args.length; index++) requested.add(args[index]);
        MemoryBlock payload = currentProgram.getMemory().getBlock("R4_PAYLOAD");
        long sourceFileOffset = 0x800;
        if (payload == null) {
            payload = currentProgram.getMemory().getBlock("R4_OVERLAY");
            sourceFileOffset = 0;
        }
        if (payload == null && !requested.isEmpty()) {
            payload = currentProgram.getMemory().getBlock(toAddr(requested.get(0)));
            sourceFileOffset = 0;
        }
        Address analysisBase = payload == null ? currentProgram.getImageBase() : payload.getStart();
        try (PrintWriter out = new PrintWriter(new File(args[0]), "UTF-8")) {
            out.println("{");
            out.println("  \"input_sha256\": " + quote(inputHash()) + ",");
            out.println("  \"language_id\": " + quote(currentProgram.getLanguageID().toString()) + ",");
            out.println("  \"image_base\": " + quote(hex(analysisBase)) + ",");
            out.println("  \"program_image_base\": " + quote(hex(currentProgram.getImageBase())) + ",");
            out.print("  \"requested_addresses\": [");
            for (int i = 0; i < requested.size(); i++) { if (i > 0) out.print(","); out.print(quote(requested.get(i))); }
            out.println("],");
            out.println("  \"functions\": [");
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            boolean first = true;
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function function = functions.next();
                if (!first) out.println(",");
                first = false;
                out.print("    {\"name\":" + quote(function.getName()) +
                    ",\"entry\":" + quote(hex(function.getEntryPoint())) +
                    ",\"file_offset\":" + quote(fileOffset(function.getEntryPoint(), payload, sourceFileOffset)) +
                    ",\"start\":" + quote(hex(function.getBody().getMinAddress())) +
                    ",\"end\":" + quote(hex(function.getBody().getMaxAddress())) + "}");
            }
            out.println("\n  ],");
            out.println("  \"basic_blocks\": [");
            first = true;
            BasicBlockModel blockModel = new BasicBlockModel(currentProgram);
            functions = currentProgram.getFunctionManager().getFunctions(true);
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function function = functions.next();
                CodeBlockIterator blocks = blockModel.getCodeBlocksContaining(function.getBody(), monitor);
                while (blocks.hasNext()) {
                    CodeBlock block = blocks.next();
                    if (!first) out.println(",");
                    first = false;
                    out.print("    {\"function\":" + quote(function.getName()) + ",\"start\":" + quote(hex(block.getFirstStartAddress())) + "}");
                }
            }
            out.println("\n  ],");
            out.println("  \"calls\": [");
            first = true;
            functions = currentProgram.getFunctionManager().getFunctions(true);
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function caller = functions.next();
                Set<Function> callees = caller.getCalledFunctions(monitor);
                for (Function callee : callees) {
                    if (!first) out.println(",");
                    first = false;
                    out.print("    {\"caller\":" + quote(hex(caller.getEntryPoint())) + ",\"callee\":" + quote(hex(callee.getEntryPoint())) + "}");
                }
            }
            out.println("\n  ],");
            out.println("  \"xrefs\": [");
            first = true;
            for (String value : requested) {
                Address address = toAddr(value);
                ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(address);
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    if (!first) out.println(",");
                    first = false;
                    out.print("    {\"from\":" + quote(hex(ref.getFromAddress())) + ",\"to\":" + quote(hex(address)) + ",\"type\":" + quote(ref.getReferenceType().toString()) + "}");
                }
            }
            out.println("\n  ],");
            out.println("  \"strings\": [");
            first = true;
            DataIterator definedData = currentProgram.getListing().getDefinedData(true);
            while (definedData.hasNext()) {
                Data data = definedData.next();
                if (!data.hasStringValue()) continue;
                if (!first) out.println(",");
                first = false;
                out.print("    {\"address\":" + quote(hex(data.getAddress())) + ",\"value\":" + quote(String.valueOf(data.getValue())) + "}");
            }
            out.println("\n  ],");
            out.println("  \"overlays\": [");
            first = true;
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                if (!block.isOverlay()) continue;
                if (!first) out.println(",");
                first = false;
                out.print("    {\"name\":" + quote(block.getName()) + ",\"start\":" + quote(hex(block.getStart())) + ",\"end\":" + quote(hex(block.getEnd())) + "}");
            }
            out.println("\n  ],");
            out.println("  \"memory_blocks\": [");
            first = true;
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                if (!first) out.println(",");
                first = false;
                out.print("    {\"name\":" + quote(block.getName()) +
                    ",\"start\":" + quote(hex(block.getStart())) +
                    ",\"end\":" + quote(hex(block.getEnd())) +
                    ",\"size\":" + block.getSize() +
                    ",\"overlay\":" + block.isOverlay() + "}");
            }
            out.println("\n  ],");
            out.println("  \"disassembly\": [");
            first = true;
            for (String value : requested) {
                Address address = toAddr(value);
                Instruction instruction = getInstructionContaining(address);
                for (int back = 0; back < 4 && instruction != null; back++) {
                    Instruction previous = getInstructionBefore(instruction.getAddress());
                    if (previous == null) break;
                    instruction = previous;
                }
                for (int count = 0; count < 12 && instruction != null; count++) {
                    if (!first) out.println(",");
                    first = false;
                    out.print("    {\"requested\":" + quote(value) +
                        ",\"address\":" + quote(hex(instruction.getAddress())) +
                        ",\"file_offset\":" + quote(fileOffset(instruction.getAddress(), payload, sourceFileOffset)) +
                        ",\"text\":" + quote(instruction.toString()) +
                        ",\"delay_slot\":" + instruction.isInDelaySlot() +
                        ",\"flow_type\":" + quote(instruction.getFlowType().toString()) + "}");
                    instruction = getInstructionAfter(instruction.getAddress());
                }
            }
            out.println("\n  ],");
            out.println("  \"branches\": [");
            first = true;
            Set<String> requestedFunctions = new HashSet<>();
            for (String value : requested) {
                Function function = currentProgram.getFunctionManager().getFunctionContaining(toAddr(value));
                if (function == null || !requestedFunctions.add(hex(function.getEntryPoint()))) continue;
                InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction item = instructions.next();
                    if (!item.getFlowType().isConditional()) continue;
                    Address[] flows = item.getFlows();
                    Address fallThrough = item.getFallThrough();
                    Instruction previous = getInstructionBefore(item.getAddress());
                    Instruction delay = item.getDelaySlotDepth() > 0
                        ? getInstructionAfter(item.getAddress()) : null;
                    if (!first) out.println(",");
                    first = false;
                    out.print("    {\"function\":" + quote(function.getName()) +
                        ",\"function_entry\":" + quote(hex(function.getEntryPoint())) +
                        ",\"address\":" + quote(hex(item.getAddress())) +
                        ",\"file_offset\":" + quote(fileOffset(item.getAddress(), payload, sourceFileOffset)) +
                        ",\"text\":" + quote(item.toString()) +
                        ",\"inputs\":" + objects(item.getInputObjects()) +
                        ",\"outputs\":" + objects(item.getResultObjects()) +
                        ",\"target\":" + (flows.length > 0 ? quote(hex(flows[0])) : "null") +
                        ",\"fall_through\":" + (fallThrough != null ? quote(hex(fallThrough)) : "null") +
                        ",\"previous_address\":" + (previous != null ? quote(hex(previous.getAddress())) : "null") +
                        ",\"previous_text\":" + (previous != null ? quote(previous.toString()) : "null") +
                        ",\"delay_slot_address\":" + (delay != null ? quote(hex(delay.getAddress())) : "null") +
                        ",\"delay_slot_text\":" + (delay != null ? quote(delay.toString()) : "null") + "}");
                }
            }
            out.println("\n  ],");
            out.println("  \"indirect_jumps\": [");
            first = true;
            requestedFunctions.clear();
            for (String value : requested) {
                Function function = currentProgram.getFunctionManager().getFunctionContaining(toAddr(value));
                if (function == null || !requestedFunctions.add(hex(function.getEntryPoint()))) continue;
                InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction item = instructions.next();
                    if (!item.getFlowType().isComputed()) continue;
                    if (!first) out.println(",");
                    first = false;
                    out.print("    {\"function\":" + quote(function.getName()) +
                        ",\"function_entry\":" + quote(hex(function.getEntryPoint())) +
                        ",\"address\":" + quote(hex(item.getAddress())) +
                        ",\"text\":" + quote(item.toString()) + "}");
                }
            }
            out.println("\n  ],");
            out.println("  \"decompiler\": [");
            first = true;
            requestedFunctions.clear();
            DecompInterface decompiler = new DecompInterface();
            decompiler.openProgram(currentProgram);
            for (String value : requested) {
                Function function = currentProgram.getFunctionManager().getFunctionContaining(toAddr(value));
                if (function == null || !requestedFunctions.add(hex(function.getEntryPoint()))) continue;
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                String code = result.decompileCompleted() && result.getDecompiledFunction() != null
                    ? result.getDecompiledFunction().getC() : "";
                if (!first) out.println(",");
                first = false;
                out.print("    {\"function\":" + quote(function.getName()) +
                    ",\"entry\":" + quote(hex(function.getEntryPoint())) +
                    ",\"file_offset\":" + quote(fileOffset(function.getEntryPoint(), payload, sourceFileOffset)) +
                    ",\"completed\":" + result.decompileCompleted() +
                    ",\"c\":" + quote(code) + "}");
            }
            decompiler.dispose();
            out.println("\n  ]");
            out.println("}");
        }
    }
}
