// @category R4AutoLab
// Asset-safe JSON metadata export for headless analysis.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Data;
import ghidra.program.model.block.BasicBlockModel;
import ghidra.program.model.block.CodeBlock;
import ghidra.program.model.block.CodeBlockIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.util.DefinedDataIterator;
import java.io.File;
import java.io.PrintWriter;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class R4Export extends GhidraScript {
    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\"";
    }

    private static String hex(Address address) { return String.format("0x%08X", address.getOffset()); }

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
        try (PrintWriter out = new PrintWriter(new File(args[0]), "UTF-8")) {
            out.println("{");
            out.println("  \"input_sha256\": " + quote(inputHash()) + ",");
            out.println("  \"language_id\": " + quote(currentProgram.getLanguageID().toString()) + ",");
            out.println("  \"image_base\": " + quote(hex(currentProgram.getImageBase())) + ",");
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
                out.print("    {\"name\":" + quote(function.getName()) + ",\"entry\":" + quote(hex(function.getEntryPoint())) + "}");
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
            for (Data data : DefinedDataIterator.definedStrings(currentProgram)) {
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
            out.println("  \"disassembly\": [");
            first = true;
            for (String value : requested) {
                Address address = toAddr(value);
                Instruction instruction = getInstructionAt(address);
                if (instruction != null) {
                    if (!first) out.println(",");
                    first = false;
                    out.print("    {\"address\":" + quote(hex(address)) + ",\"text\":" + quote(instruction.toString()) + "}");
                }
            }
            out.println("\n  ]");
            out.println("}");
        }
    }
}
