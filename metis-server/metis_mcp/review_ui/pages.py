"""
The rendered decision pages — the half of §9.3 that was designed and not drawn.

**What was here before.** The evidence layer (`evidence.py`) decided what each
screen must show, the JSON endpoints served all of it, and `decisions.py` applied
the answers. What did not exist was a page: `/model` rendered a static SVG and
carried no `<button>`, `<form>` or `<script>` — the CSP omits `script-src`
deliberately — so §9.2's "Primary. All six decisions" was true of the API and
false of the surface a person opens. A reviewer could look at the model and had
no way to decide anything in it, which is why every gate's halt message sends
them to the CLI.

**Forms, not scripting.** A plain `<form method="post">` needs no JavaScript, so
the CSP stays exactly as strict as it was and the credential never enters
anything a page can read. That is the whole reason `sessions.py` exists: the
alternative was relaxing the CSP so a script could hold a bearer token.

**Nothing here decides.** These functions render; `server.py` routes and the same
`review.decisions.apply` the CLI calls does the work. A page that computed its
own idea of what an approval means would be a second definition of the gate.

**A screen that cannot show its evidence renders the refusal, not the form**
(N-4). `Screen.can_decide` is false and `blocked_reason` says what is absent;
this draws that instead of a submit button, because a disabled control invites
somebody to look for the enabling trick.
"""
from __future__ import annotations

import html

from metis_mcp.review_ui.view import _CSS

# One extra rule set, appended rather than forked: the model view and the
# decision pages must not drift into two looks, and a second copy of the base
# CSS is how that starts.
_FORM_CSS = """
.card { border: 1px solid #e2e2e2; border-radius: 8px; padding: 16px 18px;
        margin: 0 0 18px; max-width: 60rem; }
.card h2 { font-size: 15px; margin: 0 0 10px; }
.ev { margin: 0 0 14px; font-size: 13px; }
.ev dt { font-weight: 600; color: #444; margin-top: 8px; }
.ev dd { margin: 2px 0 0; }
.blocked { border-left: 3px solid #a3352b; background: #fbecea; padding: 12px 14px;
           margin: 0 0 18px; font-size: 13px; }
.actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
           margin-top: 14px; }
button { font: inherit; padding: 7px 16px; border-radius: 6px; cursor: pointer;
         border: 1px solid #1f6851; background: #1f6851; color: #fff; }
button.secondary { background: transparent; color: inherit; border-color: #999; }
input[type=text], input[type=password], textarea, select {
    font: inherit; padding: 7px 9px; border: 1px solid #ccc; border-radius: 6px;
    background: #fff; color: #111; width: 100%; max-width: 44rem; }
textarea { min-height: 4.5em; }
label { display: block; margin: 12px 0 0; font-size: 13px; font-weight: 600; }
label .hint { display: block; font-weight: 400; color: #666; margin-top: 2px; }
nav { margin: 0 0 20px; font-size: 13px; display: flex; gap: 14px; }
nav a { color: #2c5a8c; }
.cmd { background: #f4f6f9; border: 1px solid #dce1e8; border-radius: 3px;
       padding: 10px 12px; overflow-x: auto; font-size: 13px; white-space: pre-wrap;
       word-break: break-word; }
.picks { list-style: none; padding: 0; margin: 10px 0; display: grid; gap: 6px; }
.picks li { font-size: 14px; }
.pick { display: flex; align-items: baseline; gap: 8px; cursor: pointer; }
.pick .kind { font-size: 12px; text-transform: uppercase; letter-spacing: .06em;
              color: #666; min-width: 5.5em; }
.who { color: #555; font-size: 13px; margin: 0 0 18px; }
.ok { border-left: 3px solid #1f6851; background: #e9f3ef; padding: 12px 14px;
      margin: 0 0 18px; font-size: 13px; }
@media (prefers-color-scheme: dark) {
  .card { border-color: #2c3038; }
  .card h2, .ev dt { color: #cfcfcf; }
  .blocked { background: #2a1614; border-left-color: #c4574a; }
  .ok { background: #12241d; }
  input[type=text], input[type=password], textarea, select {
      background: #1b1e24; color: #e8e8e8; border-color: #383d47; }
  button.secondary { border-color: #555; }
  .who, label .hint { color: #a8a8a8; }
  nav a { color: #7fa8d6; }
  .cmd { background: #14171c; border-color: #383d47; }
  .pick .kind { color: #a8a8a8; }
}
"""


def page(title: str, body: str, identity=None) -> str:
    """The shell every decision page shares."""
    who = ""
    if identity is not None:
        who = (f'<p class="who">Signed in as <strong>{html.escape(identity.name)}</strong> '
               f'({html.escape(identity.role)}) · '
               f'<a href="/logout">sign out</a></p>')
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        f"<style>{_CSS}{_FORM_CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>{who}{body}</body></html>")


def nav(model_id: str) -> str:
    return ('<nav><a href="/queue">decisions waiting</a>'
            '<a href="/model">model view</a>'
            '<a href="/decide/approve">approve the model</a>'
            '<a href="/decide/name-state">name a state</a>'
            '<a href="/audit">audit trail</a></nav>')


def login_page(message: str = "", next_path: str = "/model") -> str:
    """The token form.

    The field is `type=password` so a shoulder-glance does not read the
    credential, and the form posts rather than putting it in a query string
    where it would land in the server log and the browser history.
    """
    warning = f'<div class="blocked">{html.escape(message)}</div>' if message else ""
    return page("Sign in to review", f"""
{warning}
<div class="card">
  <p class="ev">A decision records <strong>who</strong> made it, so it needs a
  credential rather than a name. Paste the token your administrator issued; it is
  checked against the digest store named by <code>METIS_API_TOKENS</code> and is
  never stored in the page.</p>
  <form method="post" action="/login">
    <input type="hidden" name="next" value="{html.escape(next_path)}">
    <label>Token
      <span class="hint">Reading the model needs no token — only deciding does.</span>
      <input type="password" name="token" autocomplete="current-password" autofocus>
    </label>
    <div class="actions">
      <button type="submit">Sign in</button>
      <a href="/model">continue read-only</a>
    </div>
  </form>
</div>""")


def _evidence(evidence: dict) -> str:
    """Every key the screen carried, in the order it carried it.

    Rendered whole rather than summarised: N-3 requires the reviewer to see what
    the decision rests on, and choosing which parts to show would be this layer
    deciding what matters.
    """
    if not evidence:
        return ""
    rows = []
    for key, value in evidence.items():
        label = key.replace("_", " ")
        if isinstance(value, (list, tuple)):
            if not value:
                shown = "<em>none</em>"
            else:
                shown = "<ul>" + "".join(
                    f"<li>{html.escape(str(v))}</li>" for v in value) + "</ul>"
        elif isinstance(value, dict):
            shown = "<ul>" + "".join(
                f"<li><code>{html.escape(str(k))}</code>: {html.escape(str(v))}</li>"
                for k, v in value.items()) + "</ul>"
        else:
            shown = html.escape(str(value))
        rows.append(f"<dt>{html.escape(label)}</dt><dd>{shown}</dd>")
    return f'<dl class="ev">{"".join(rows)}</dl>'


def blocked(screen) -> str:
    """N-4 rendered: what is missing, and no control to proceed anyway."""
    return (f'<div class="blocked"><strong>This decision is blocked.</strong> '
            f"{html.escape(screen.blocked_reason or 'evidence is missing')}"
            f"</div>{_evidence(screen.evidence)}")


def unfillable_page(decision: str, subject: str, missing, sentence: str,
                    identity) -> str:
    """The refusal, when the half a decision needs could not be reached.

    **This is a real screen, not an error page.** `Screen.require()` already
    blocks a decision whose evidence is incomplete; what it could not do is say
    *which* input is absent and *who holds it*, because by then the caller had
    already failed to supply it. The resolver knows both, so the refusal is
    finally actionable: a reviewer can go and get the thing rather than
    concluding the surface is broken.
    """
    items = "".join(
        "<li><code>{}</code></li>".format(html.escape(str(m))) for m in missing)
    body = [nav("")]
    body.append("""
<div class="card">
  <h2>{decision} · {subject}</h2>
  <div class="blocked">
    <p><strong>This decision cannot be drawn yet.</strong></p>
    <p>{sentence}</p>
  </div>
  <p class="ev">Still needed:</p>
  <ul class="picks">{items}</ul>
  <p class="ev">Nothing was decided and nothing was recorded. Métis will not
  render a decision over a value it substituted — a page drawn that way asks you
  to judge evidence nobody gathered.</p>
</div>""".format(
        decision=html.escape(decision.replace("_", " ")),
        subject=html.escape(subject),
        sentence=html.escape(sentence),
        items=items))
    return page("Cannot decide yet", "".join(body), identity)


def confirm_match_page(ac_id, transition_id, provided, identity,
                       result: str = "") -> str:
    """Does this criterion really validate that behaviour?

    Shows the criterion's own words, the transition tuple, and **why the match
    was proposed** — which pre-filter evidence matched. X-17 says the pre-filter
    narrows without deciding, and a reviewer has to be able to see that a match
    rests on a route and a status rather than on wording similarity, which is
    never sufficient on its own.
    """
    body = [nav("")]
    if result:
        body.append('<div class="ok">{}</div>'.format(html.escape(result)))

    why = provided.get("why_proposed") or {}
    evidence = why.get("evidence") or {}
    rows = "".join(
        "<li><code>{}</code> {}</li>".format(html.escape(str(k)), html.escape(str(v)))
        for k, v in sorted(evidence.items()))
    if not rows:
        rows = '<li class="ev">no pre-filter evidence for this pairing</li>'

    tuple_ = provided.get("transition_tuple") or {}
    tuple_rows = "".join(
        "<dt>{}</dt><dd><code>{}</code></dd>".format(
            html.escape(str(k)), html.escape(str(v)))
        for k, v in tuple_.items() if v is not None)

    body.append("""
<div class="card">
  <h2>Confirm a match</h2>
  <p class="ev">Does <code>{ac}</code> really validate <code>{tid}</code>?
  Confirming writes the only traceability edge Métis has.</p>
</div>
<div class="card">
  <h2>The criterion</h2>
  <p>{text}</p>
</div>
<div class="card">
  <h2>The behaviour it would validate</h2>
  <dl class="ev">{tuple_rows}</dl>
  {anchor}
</div>
<div class="card">
  <h2>Why this was proposed</h2>
  <p class="ev">The pre-filter narrows candidates; it does not decide (X-17).
  A match resting on wording alone is not a match.</p>
  <ul class="picks">{rows}</ul>
  <p class="ev">{note}</p>
</div>
<div class="card">
  <h2>Record the decision</h2>
  <form method="post" action="/decide/confirm-match">
    <input type="hidden" name="ac_id" value="{ac}">
    <input type="hidden" name="transition_id" value="{tid}">
    <label>Decision
      <select name="confirmed">
        <option value="yes">Confirm — this criterion validates this behaviour</option>
        <option value="no">Reject — it does not</option>
      </select>
    </label>
    <label>Why
      <span class="hint">Recorded with the decision.</span>
      <textarea name="rationale" required></textarea>
    </label>
    <div class="actions"><button type="submit">Record</button></div>
  </form>
</div>""".format(
        ac=html.escape(str(ac_id)),
        tid=html.escape(str(transition_id)),
        text=html.escape(str(provided.get("ac_text", ""))),
        tuple_rows=tuple_rows,
        anchor=('<p class="ev">anchor <code>{}</code></p>'.format(
            html.escape(str(provided["code_anchor"])))
            if provided.get("code_anchor") else ""),
        rows=rows,
        note=html.escape(str(why.get("note", "")))))
    return page("Confirm a match", "".join(body), identity)


def queue_page(entries, identity, by_workflow=None) -> str:
    """Every run stopped at a gate, as one card each.

    **The question no surface answered.** `run_status` tells you where a run got
    to if you already have its id, which you only do if you started it. Nobody
    could ask what was waiting on them, so a gate reached on Tuesday was
    attended to when somebody happened to remember it.

    Each card renders the gate's own `outstanding` and `next_command`. Neither
    is composed here: the engine authored both, and a surface that rewrote
    either would be giving the reviewer its own account of what is blocking.

    **No decision is taken from this page.** It links to the surface that owns
    each decision, because a queue that could also approve is a queue somebody
    works through without reading — and the evidence gate lives on the decision
    page, not here.
    """
    body = [nav("")]

    if not entries:
        body.append(
            '<div class="card"><h2>Nothing is waiting</h2>'
            '<p class="ev">No run is stopped at a gate. That is not the same as '
            'nothing being in progress — a failed run needs fixing and does not '
            'appear here, by design.</p></div>')
        return page("Decisions waiting", "".join(body), identity)

    counts = ", ".join(f"{n} {w}" for w, n in sorted((by_workflow or {}).items()))
    body.append(
        '<div class="card"><h2>{n} decision(s) waiting</h2>'
        '<p class="ev">{counts}. Each one is a run that stopped for a person; '
        'nothing here has failed and nothing is still running.</p></div>'
        .format(n=len(entries), counts=html.escape(counts or "across all workflows")))

    for entry in entries:
        outstanding = entry.get("outstanding") or []
        shown = outstanding[:8]
        more = len(outstanding) - len(shown)
        items = "".join(
            "<li><code>{}</code></li>".format(html.escape(str(line)))
            for line in shown)
        if more > 0:
            items += '<li class="ev">… and {} more</li>'.format(more)

        body.append("""
<div class="card">
  <h2>{workflow} · {scope}</h2>
  <p class="ev">Stopped at <strong>{gate}</strong> since {since}.</p>
  <p class="ev"><strong>{detail}</strong></p>
  <ul class="picks">{items}</ul>
  <p class="ev">The engine's own resolution for this gate:</p>
  <pre class="cmd">{command}</pre>
  {link}
</div>""".format(
            workflow=html.escape(str(entry.get("workflow", ""))),
            scope=html.escape(str(entry.get("scope", ""))),
            gate=html.escape(str(entry.get("blocked_on", ""))),
            since=html.escape(str(entry.get("waiting_since", ""))[:16]),
            detail=html.escape(str(entry.get("detail", ""))),
            items=items,
            command=html.escape(str(entry.get("next_command", ""))),
            link=_gate_link(entry)))

    return page("Decisions waiting", "".join(body), identity)


def _gate_link(entry) -> str:
    """A link to the surface that owns this gate, where one is rendered.

    Only `model-approval` has a page today. Saying so beats linking somewhere
    that cannot draw the decision — the four JSON-only decisions are JSON-only
    because the review context does not hold what they are about, and a link
    into a 409 teaches people the queue is unreliable.
    """
    if entry.get("blocked_on") == "model-approval":
        return '<div class="actions"><a href="/decide/approve">Open the approval screen</a></div>'
    return ('<p class="ev"><em>This gate has no rendered screen yet — the '
            'command above is the surface that owns it.</em></p>')


def approve_page(model, screen, identity, outstanding, result: str = "") -> str:
    """G1. The whole model, or one element of it."""
    body = [nav(model.id)]
    if result:
        body.append(f'<div class="ok">{html.escape(result)}</div>')

    if not screen.can_decide:
        body.append(blocked(screen))
        return page(f"Approve {model.id}", "".join(body), identity)

    # **Every outstanding element, visible and selectable.**
    #
    # This was a `<select>` offering one element or the whole model, and that
    # shape had a consequence nobody chose: a reviewer content with thirty of
    # forty had to submit thirty times, with thirty rationales, while approving
    # all forty took one click. The blanket decision was the cheapest action on
    # the page and the considered one the most expensive -- backwards for a
    # gate, whose whole purpose is to make the considered path the easy one.
    #
    # Checkboxes, pre-checked. The default is still "all of it", so nothing got
    # harder; what changed is that dissent costs one click instead of
    # twenty-nine submissions, and the ids are readable while deciding rather
    # than hidden behind a dropdown.
    #
    # **No tick-all button, and that is a decision.** It would need inline
    # script, and `test_the_pages_add_no_script_and_the_policy_still_forbids_one`
    # is where that trade gets made rather than discovered: relaxing the CSP on
    # the decision surface is how a credential ends up somewhere a page can read
    # it. Pre-checking gives the same one-click approve-all without it, so the
    # convenience was never worth the exception.
    rows = "".join(
        '<li><label class="pick">'
        '<input type="checkbox" name="element_ids" value="{v}" checked>'
        '<span class="kind">{k}</span> <code>{v}</code>'
        '</label></li>'.format(v=html.escape(eid), k=html.escape(kind))
        for kind, eid, _ in outstanding)

    body.append(f"""
<div class="card">
  <h2>The evidence this decision rests on</h2>
  {_evidence(screen.evidence)}
  {"".join(f'<p class="ev"><em>{html.escape(n)}</em></p>' for n in screen.notes)}
</div>
<div class="card">
  <h2>Record the decision</h2>
  <p class="ev"><strong>{len(outstanding)}</strong> element(s) are outstanding.
  Everything ticked below is covered by one decision, and the record names each
  one (N-5: a batch decision must show its contents).</p>
  <form method="post" action="/decide/approve">
    <ul class="picks">{rows}</ul>
    <label>Decision
      <span class="hint">Defer is what makes approving the rest safe: say so on the
      few you are unsure about and decide the others now, rather than blessing
      everything or grinding through them one at a time.</span>
      <select name="decision">
        <option value="approve">Approve the ticked elements</option>
        <option value="defer">Defer the ticked elements</option>
        <option value="reject">Reject the ticked elements</option>
      </select>
    </label>
    <label>Why
      <span class="hint">Recorded with the decision. A resolution with no reason is
      indistinguishable afterwards from an automatic rule attributed to you.</span>
      <textarea name="rationale" required></textarea>
    </label>
    <div class="actions"><button type="submit">Record</button></div>
  </form>
</div>""")
    return page(f"Approve {model.id}", "".join(body), identity)


def name_state_page(model, state_id, screen, identity, result: str = "") -> str:
    """Naming is not agreement (M-14): this records a name and approves nothing."""
    body = [nav(model.id)]
    if result:
        body.append(f'<div class="ok">{html.escape(result)}</div>')

    unnamed = [(sid, s) for sid, s in model.states.items()]
    options = "".join(
        f'<option value="{html.escape(sid)}"'
        f'{" selected" if sid == state_id else ""}>{html.escape(sid)}</option>'
        for sid, _ in unnamed)
    body.append(f"""
<div class="card">
  <h2>Which state</h2>
  <form method="get" action="/decide/name-state">
    <label>State
      <select name="state">{options}</select>
    </label>
    <div class="actions"><button class="secondary" type="submit">Show its evidence</button></div>
  </form>
</div>""")

    if not state_id:
        body.append('<p class="ev">Choose a state to see what is known about it.</p>')
        return page(f"Name a state — {model.id}", "".join(body), identity)

    if not screen.can_decide:
        body.append(blocked(screen))
        return page(f"Name a state — {model.id}", "".join(body), identity)

    body.append(f"""
<div class="card">
  <h2>What is known about <code>{html.escape(state_id)}</code></h2>
  {_evidence(screen.evidence)}
  {"".join(f'<p class="ev"><em>{html.escape(n)}</em></p>' for n in screen.notes)}
  <form method="post" action="/decide/name-state">
    <input type="hidden" name="state_id" value="{html.escape(state_id)}">
    <label>Name
      <span class="hint">Métis proposes and never assumes. Giving a state a
      sensible name does not approve it (M-14).</span>
      <input type="text" name="name" required>
    </label>
    <label>Why<textarea name="rationale"></textarea></label>
    <div class="actions"><button type="submit">Record the name</button></div>
  </form>
</div>""")
    return page(f"Name a state — {model.id}", "".join(body), identity)


def audit_page(entries, self_approvals, identity, model_id) -> str:
    """A-27: a self-approval is visible, never silent."""
    if not entries:
        rows = '<tr><td colspan="6"><em>no decision has been recorded in this session</em></td></tr>'
    else:
        rows = "".join(
            f"<tr><td>{html.escape(str(e.get('at', '')))}</td>"
            f"<td>{html.escape(str(e.get('actor', '')))} "
            f"<span class=\"hint\">{html.escape(str(e.get('role', '')))}</span></td>"
            f"<td>{html.escape(str(e.get('capability', '')))}</td>"
            f"<td><code>{html.escape(str(e.get('element_id', '')))}</code></td>"
            f"<td>{html.escape(str(e.get('rationale', '')))}"
            f"{' <strong>(self-approval)</strong>' if e.get('self_approval') else ''}"
            f"</td>"
            # N-13/N-14: the record carries the evidence PRESENTED, not merely
            # the outcome. Without this column a later reader cannot tell a
            # careless approval from a reasonable decision made on what was
            # then available -- which is the whole reason the field is stored.
            f"<td><code>{html.escape(str(e.get('evidence_fingerprint', '')))}</code></td>"
            f"</tr>" for e in entries)
    note = ""
    if self_approvals:
        note = (f'<div class="blocked">{len(self_approvals)} self-approval(s) in '
                f"this session. N-11's override is recorded and visible, never "
                f"silent (A-27).</div>")
    return page(f"Audit — {model_id}",
                f"{nav(model_id)}{note}<table><thead><tr><th>when</th><th>who</th>"
                f"<th>what</th><th>element</th><th>why</th>"
                f"<th>evidence seen</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
                f'<p class="caveat">The last column is a fingerprint of what was '
                f"<strong>shown</strong> to the reviewer, not of what existed. "
                f"That is what makes the record answerable later: a decision "
                f"cannot be defended with information the decider never saw "
                f"(N-13, N-14).</p>", identity)
