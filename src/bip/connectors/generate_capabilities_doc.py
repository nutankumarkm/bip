"""Generates docs/CAPABILITIES.md from src/bip/connectors/registry.yaml (ADR-002, section 8.8)."""

from __future__ import annotations

from pathlib import Path

import yaml


def generate_markdown(registry_path: Path, output_path: Path) -> str:
    content = registry_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    md = []
    md.append("# BIP Connector Capability Matrix\n")
    md.append("> Generated automatically from `src/bip/connectors/registry.yaml`.\n")
    md.append("## Status Definitions\n")
    md.append("- **declared**: Claimed by vendor or open-source protocol documentation.")
    md.append("- **probed**: Device successfully answered probe query at runtime.")
    md.append("- **verified**: Certified in hardware device lab against real physical hardware.")
    md.append("- **unsupported**: Known to be unsupported on this model family.\n")

    families = data.get("families", {})
    for fam_name, fam_info in families.items():
        desc = fam_info.get("description", "")
        mode = fam_info.get("mode", "")
        md.append(f"### `{fam_name}` ({mode.upper()})\n")
        md.append(f"**Description:** {desc}\n")

        models = fam_info.get("models", {})
        for model_pattern, model_info in models.items():
            m_desc = model_info.get("description", "")
            caps = model_info.get("capabilities", {})
            md.append(f"#### Model Pattern: `{model_pattern}`")
            md.append(f"*{m_desc}*\n")
            md.append("| Capability | Status |")
            md.append("|---|---|")
            for cap, status in caps.items():
                status_icon = "⚪"
                if status == "verified":
                    status_icon = "🟢"
                elif status == "probed":
                    status_icon = "🟡"
                elif status == "declared":
                    status_icon = "🔵"
                elif status == "unsupported":
                    status_icon = "❌"
                md.append(f"| `{cap}` | {status_icon} **{status}** |")
            md.append("")

    doc_str = "\n".join(md)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc_str, encoding="utf-8")
    return doc_str


if __name__ == "__main__":
    reg_path = Path(__file__).parent / "registry.yaml"
    out_path = Path(__file__).parents[3] / "docs" / "CAPABILITIES.md"
    generate_markdown(reg_path, out_path)
    print(f"Generated {out_path}")
