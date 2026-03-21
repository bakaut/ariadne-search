from __future__ import annotations

import ast
from pathlib import Path

from kb_worker.models import SymbolArtifact, SymbolLinkArtifact


class CodeParser:
    def parse(self, path: Path, language: str | None) -> tuple[list[SymbolArtifact], list[SymbolLinkArtifact]]:
        if language != "python":
            return [], []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            return [], []

        symbols: list[SymbolArtifact] = []
        links: list[SymbolLinkArtifact] = []
        module_name = path.stem

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fq_name = f"{module_name}.{node.name}"
                symbols.append(
                    SymbolArtifact(
                        symbol_name=node.name,
                        symbol_kind="function",
                        fq_name=fq_name,
                        language=language,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        signature=f"def {node.name}(...)",
                    )
                )
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                        links.append(
                            SymbolLinkArtifact(
                                from_symbol_fq_name=fq_name,
                                to_symbol_fq_name=inner.func.id,
                                link_type="CALLS",
                            )
                        )
            elif isinstance(node, ast.ClassDef):
                symbols.append(
                    SymbolArtifact(
                        symbol_name=node.name,
                        symbol_kind="class",
                        fq_name=f"{module_name}.{node.name}",
                        language=language,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        signature=f"class {node.name}",
                    )
                )
        return symbols, links
