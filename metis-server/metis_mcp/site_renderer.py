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
) + ' | <a href="changelog.html">Changelog</a></nav>')


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
    index_file = render_index(out, session=session)
    return {"output_dir": str(out), "index": index_file, "academy_pages": academy_files,
            "changelog": changelog_file}
