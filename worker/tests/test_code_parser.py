from __future__ import annotations

from pathlib import Path

from kb_worker.parsers.code_parser import CodeParser


def test_code_parser_ignores_non_python_files(tmp_path: Path) -> None:
    path = tmp_path / "main.js"
    path.write_text("function x() {}", encoding="utf-8")

    symbols, links = CodeParser().parse(path, "javascript")

    assert symbols == []
    assert links == []


def test_code_parser_returns_empty_on_syntax_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")

    symbols, links = CodeParser().parse(path, "python")

    assert symbols == []
    assert links == []


def test_code_parser_extracts_symbols_and_simple_call_links(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text(
        """
class Example:
    pass

def callee():
    return 1

async def runner():
    callee()
    obj.method()
""".strip(),
        encoding="utf-8",
    )

    symbols, links = CodeParser().parse(path, "python")

    symbol_names = {(symbol.symbol_name, symbol.symbol_kind, symbol.fq_name) for symbol in symbols}
    assert ("Example", "class", "module.Example") in symbol_names
    assert ("callee", "function", "module.callee") in symbol_names
    assert ("runner", "function", "module.runner") in symbol_names
    assert any(symbol.signature == "def callee(...)" for symbol in symbols)
    assert any(symbol.signature == "class Example" for symbol in symbols)
    assert [(link.from_symbol_fq_name, link.to_symbol_fq_name, link.link_type) for link in links] == [
        ("module.runner", "callee", "CALLS")
    ]
