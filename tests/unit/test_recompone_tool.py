from pathlib import Path

from r4_autolab.recompone import tool as module
from r4_autolab.recompone.tool import PINNED_RECOMPONE_COMMIT, discover_recompone, dotnet_is_supported


def test_dotnet_version_requires_major_ten_or_newer() -> None:
    assert dotnet_is_supported("10.0.201")
    assert dotnet_is_supported("11.0.0-preview.1")
    assert not dotnet_is_supported("9.0.999")
    assert not dotnet_is_supported("unexpected")
    assert not dotnet_is_supported(None)


def test_discovers_built_checkout_from_environment(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    root = tmp_path / "RecompOne"
    binary = root / "RecompOne.Recompiler/bin/Release/net10.0/recompone.dll"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"assembly")
    (root / "RecompOne.sln").write_text("solution", encoding="utf-8")
    (root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    monkeypatch.setenv("R4_AUTOLAB_RECOMPONE", str(root))  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        module, "query_dotnet", lambda: (Path("/usr/local/bin/dotnet"), "10.0.201")
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        module, "_git_metadata", lambda source: (PINNED_RECOMPONE_COMMIT, False)
    )
    found = discover_recompone()
    assert found is not None
    assert found.path == binary.resolve()
    assert found.launcher == ("/usr/local/bin/dotnet", str(binary.resolve()))
    assert found.pinned
    assert found.source_dirty is False
    assert found.license_name == "MIT"
