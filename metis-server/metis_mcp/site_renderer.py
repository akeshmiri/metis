"""
§12.5 Site renderer -- the second thin renderer over metis_mcp/academy.py's
single real content-assembly stage (REQ-METIS-ACD-07/08). "The Site
renderer follows the same skill-folder convention as §4.6.1 ... sharing
the steps/01-gather-content.md stage with the PPTX renderer rather than
duplicating it" -- both renderers call the same assemble_content(), never
re-gather content independently.

REQ-METIS-ACD-09: the Site should be regenerated on every relevant graph
change (or a short schedule) since it must stay current -- render_site()
itself is stateless/idempotent (always writes the full current state), so
"regenerate on a schedule" is just "call this function again"; no
incremental-diff machinery is needed or built here.
"""
import html
from pathlib import Path

import markdown as markdown_lib

from metis_mcp.academy import ACADEMY_PAGES, assemble_content

_CSS = """
body { font-family: -apple-system, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
nav { margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #ccc; }
nav a { margin-right: 1rem; }
code { background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; }
pre { background: #f4f4f4; padding: 1em; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.5em; text-align: left; }
footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #ccc; color: #666; font-size: 0.85em; }
"""

_NAV = ('<nav><a href="index.html">Index</a>' + "".join(
    f' | <a href="academy/{pid}.html">{ACADEMY_PAGES[pid]["title"]}</a>' for pid in ACADEMY_PAGES
) + ' | <a href="changelog.html">Changelog</a> | <a href="test-design-report.html">Test Design Report</a></nav>')


def _page_shell(title: str, body_html: str, content_version: str | None = None) -> str:
    # REQ-METIS-ACD-06: content versioned alongside the ontology -- the
    # version has to actually be visible to a reader, not just computed
    # and discarded (real gap this closes: assemble_content() already
    # returned `version`, but no renderer ever put it on the page).
    footer = f"<footer>Academy content version: {html.escape(content_version)}</footer>" if content_version else ""
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{_NAV}<h1>{html.escape(title)}</h1>{body_html}{footer}</body></html>"
    )


def render_academy_pages(output_dir: Path) -> list[str]:
    academy_out = output_dir / "academy"
    academy_out.mkdir(parents=True, exist_ok=True)
    written = []
    for page_id, entry in ACADEMY_PAGES.items():
        content = assemble_content(None, kind="academy_page", page_id=page_id)
        body_html = markdown_lib.markdown(content["content"], extensions=["extra", "toc"])
        page_path = academy_out / f"{page_id}.html"
        page_path.write_text(_page_shell(entry["title"], body_html, content["version"]), encoding="utf-8")
        written.append(str(page_path))
    return written


def render_changelog(output_dir: Path, session=None) -> str:
    """REQ-METIS-ACD-05: real changelog page. Real gap this closes:
    metis_mcp.academy.generate_changelog() existed and was tested, but no
    renderer ever actually called it -- a changelog function nobody could
    see isn't a real changelog. Sourced from the real :Constitution rule
    set's actual :Revision history (metis_mcp.constitution_gate.py) --
    "a running log of ontology/rule changes" is literally what Constitution
    rule revisions are."""
    if session is None:
        body = "<p>No graph session available -- changelog needs a real Neo4j connection.</p>"
    else:
        rule_ids = [r["id"] for r in session.run("MATCH (c:Constitution) RETURN c.id AS id").data()]
        content = assemble_content(session, kind="changelog", entity_ids=rule_ids)
        body = f"<pre>{html.escape(content['plain_language'])}</pre>" if rule_ids else \
            "<p>No :Constitution rules loaded yet -- run `python3 -m metis_mcp.constitution_gate` first.</p>"

    changelog_path = output_dir / "changelog.html"
    changelog_path.write_text(_page_shell("Changelog", body), encoding="utf-8")
    return str(changelog_path)


def render_test_design_report(output_dir: Path, session=None, scope: dict | None = None) -> str:
    """Session 10: "anyone can go and check this model" -- a browsable
    rendering of the real Intent/TestDesign backbone (metis_mcp/
    quality_report.py's build_test_design_report), not just an MCP-only
    JSON tool. Defaults to project_wide -- the whole graph's current
    Requirement/AcceptanceCriterion/TestDesign/TestCase state, same scope
    render_index()'s quality snapshot already uses."""
    scope = scope or {"project_wide": True}
    if session is None:
        body = "<p>No graph session available -- this report needs a real Neo4j connection.</p>"
    else:
        report = assemble_content(session, kind="test_design_report", scope=scope)
        rows = []
        for req in report["requirements"]:
            if not req["acceptance_criteria"]:
                continue  # honest: requirements outside the backbone yet aren't padded in
            for ac in req["acceptance_criteria"]:
                design = ac["test_design"]
                techniques = ", ".join(design["techniques"]) if design else "<em>no TestDesign yet</em>"
                levels = ", ".join(sorted({tc["type"] or "untyped" for tc in ac["test_cases"]})) or "<em>none</em>"
                # Real, disclosed data-quality finding, not a rendering
                # assumption: a small number of real AcceptanceCriterion
                # nodes carry no `text` property -- shown honestly rather
                # than crashing the whole report.
                ac_text = ac["text"] if ac["text"] is not None else "(no text recorded)"
                rows.append(
                    f"<tr><td>{html.escape(req['requirement_id'])}</td>"
                    f"<td>{html.escape(ac_text)}</td><td>{techniques}</td><td>{levels}</td></tr>"
                )
        table = (
            "<table><thead><tr><th>Requirement</th><th>Acceptance Criterion</th>"
            "<th>Test design technique(s)</th><th>Test levels</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>" if rows else
            "<p>No AcceptanceCriterion in this scope is covered by the real Intent/TestDesign "
            "backbone yet (Session 10) -- an honest gap, not an error.</p>"
        )
        body = (
            f"<p>Scope: {html.escape(report['scope_description'])}. "
            f"{report['acceptance_criteria_with_test_design']}/{report['total_acceptance_criteria']} "
            f"AcceptanceCriteria have a real TestDesign. "
            f"Techniques found: {', '.join(report['techniques_used']) or 'none'}.</p>{table}"
        )

    report_path = output_dir / "test-design-report.html"
    report_path.write_text(_page_shell("Test Design Report", body), encoding="utf-8")
    return str(report_path)


def render_index(output_dir: Path, session=None) -> str:
    links = "".join(
        f"<li><a href='academy/{pid}.html'>{html.escape(ACADEMY_PAGES[pid]['title'])}</a></li>"
        for pid in ACADEMY_PAGES
    )
    body = f"<h2>Academy pages</h2><ul>{links}</ul>"

    if session is not None:
        summary = assemble_content(session, kind="quality_summary")
        score = summary.get("quality_score")
        body += (
            f"<h2>Current quality snapshot</h2>"
            f"<p>Composite quality_score: <b>{score if score is not None else 'not computable'}</b> "
            f"(release gate: {'clear' if summary.get('release_gate_pass') else 'not clear / partial data'})</p>"
        )

    index_path = output_dir / "index.html"
    index_path.write_text(_page_shell("Métis Site", body), encoding="utf-8")
    return str(index_path)


def render_site(output_dir: str, session=None) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    academy_files = render_academy_pages(out)
    changelog_file = render_changelog(out, session=session)
    test_design_report_file = render_test_design_report(out, session=session)
    index_file = render_index(out, session=session)
    return {"output_dir": str(out), "index": index_file, "academy_pages": academy_files,
            "changelog": changelog_file, "test_design_report": test_design_report_file}
