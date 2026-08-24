// Query pack: browser-UI behaviour extraction, Layer 4 (application spec §5.2, M-2).
//
// Recovers the three things a user-perspective transition needs from a UI
// surface: the trigger (an interaction a person performs), the observable
// outcome (what changes on screen), and -- where one exists -- the API call the
// handler makes, which is what proposes an `INVOKES` link (M-5a, M-5g).
//
// Measured facts about the pilot target, established by probing the real CPG
// before this pack was written rather than assumed:
//
//   1. Handlers are registered with `addEventListener(<literal>, <closure>)`.
//      The event name is a literal in 11 of 11 cases, so the trigger is
//      recoverable without inference.
//   2. Outcomes are DOM mutations: `classList.add/remove/toggle`, `setAttribute`
//      (notably `aria-expanded`), and `hidden`. These ARE the observable
//      signature on a UI surface (M-2) -- a screen state, not a status code.
//   3. **Zero network calls.** `fetch`, `XMLHttpRequest`, `axios` and `ajax`
//      appear nowhere. Every transition this pack recovers is therefore
//      client-side only, has no `INVOKES` link by design (M-5d), and is NOT a
//      gap against any API model (A-17d). That absence is reported as a real
//      finding, not passed over in silence.
//
// The selector a handler is bound to is frequently NOT recoverable: the element
// comes from a variable assigned elsewhere. Per T-9d it is marked
// `__unrecoverable__` rather than guessed -- a fabricated selector is worse than
// an absent one, because it looks usable.
//
// Usage:
//   joern --script query.sc --param cpgPath=<cpg> --param commit=<sha> \
//         --param repo=<name> --param out=<file.json>

import java.io.PrintWriter

@main def main(cpgPath: String, commit: String, repo: String, out: String) = {
  importCpg(cpgPath)

  def esc(s: String): String =
    if (s == null) "" else s.replace("\\", "\\\\").replace("\"", "\\\"")
      .replace("\n", " ").replace("\r", " ").replace("\t", " ")

  def anchor(file: String, line: Option[Int]): String =
    s"""{"file":"${esc(file)}","line":${line.getOrElse(0)},"commit":"${esc(commit)}"}"""

  def unquote(s: String): String = s.trim.stripPrefix("\"").stripSuffix("\"")
    .stripPrefix("'").stripSuffix("'")

  // ---- 0. Selectors, resolved from the code that looks the element up ----
  //
  // **A selector is extracted, never authored and never guessed.** It was going
  // to be a field somebody filled in by hand, which is the wrong source: a
  // plain-DOM page names its elements in code —
  // `const archiveButton = document.getElementById("archive")` — and that
  // literal is structurally recoverable in a way a JSX prop is not.
  //
  // So the binding is followed: the receiver of `addEventListener` is a
  // variable, and the assignment that defined it carries the selector.
  //
  // An element reached by walking the DOM
  // (`rows.querySelector("tr").children[2].firstElementChild`) has **no**
  // literal naming it, and the walk's own `"tr"` is emphatically not its
  // selector. Those resolve to nothing and are reported, because a wrong
  // selector in a generated Page Object fails at run time against the wrong
  // element, which is worse than a stub that refuses to run.
  val lookups = Set("getElementById", "querySelector", "querySelectorAll",
                    "getElementsByClassName", "getElementsByName", "closest")

  def selectorForm(call: io.shiftleft.codepropertygraph.generated.nodes.Call,
                   raw: String): String =
    if (call.name == "getElementById") "#" + raw
    else if (call.name == "getElementsByClassName") "." + raw
    else if (call.name == "getElementsByName") s"[name='$raw']"
    else raw

  // `variable -> selector`, and only where the assignment is a DIRECT lookup.
  // A chained expression is excluded by requiring the lookup to be the whole
  // right-hand side rather than a step inside it.
  val selectorOf: Map[String, String] = cpg.assignment.l.flatMap { a =>
    val target = a.target.code.trim
    val source = a.source
    val direct = source.start.isCall.l.filter(c => lookups.contains(c.name))
      .filter(c => c.code.trim == source.code.trim)
    direct.headOption.flatMap { c =>
      c.argument.isLiteral.code.headOption.map(unquote).map(selectorForm(c, _))
        .filter(_.nonEmpty).map(target -> _)
    }
  }.toMap

  // ---- 1. Triggers: addEventListener(<event>, <handler>) ----
  val registrations = cpg.call.nameExact("addEventListener").l

  val triggerBuf = scala.collection.mutable.ListBuffer[String]()
  val outcomeBuf = scala.collection.mutable.ListBuffer[String]()
  val invokeBuf  = scala.collection.mutable.ListBuffer[String]()

  registrations.zipWithIndex.foreach { case (reg, i) =>
    val eventLit = reg.argument.argumentIndex(1).isLiteral.code.headOption
    val event = eventLit.map(unquote).getOrElse("__unrecoverable__")

    // The receiver: `toggle.addEventListener(...)` -> "toggle". A variable name
    // is evidence of WHICH element, not a selector; recorded as-is and marked
    // when it cannot be recovered at all.
    val receiver = reg.receiver.code.headOption
      .map(c => c.split("\\.").headOption.getOrElse(c))
      .getOrElse("__unrecoverable__")

    val file = reg.file.name.headOption.getOrElse("")
    val line = reg.lineNumber
    val id = s"ui-$i-$event"

    // An inline closure resolves through isMethodRef. A NAMED handler --
    // `addEventListener("scroll", syncScrollState)` -- does not: the second
    // argument is an identifier, so it is resolved by name instead.
    //
    // The fallback to the enclosing method is deliberately NARROW. An earlier
    // version fell back to it whenever isMethodRef missed, which for a
    // module-level registration made the enclosing "method" the whole file and
    // attributed all 51 mutations in it to one scroll handler. The model looked
    // precise and was not. Attribution is now recorded in `link` so a reviewer
    // can weigh it, exactly as the JVM pack does for its name-match heuristic.
    val inline = reg.argument.argumentIndex(2).isMethodRef.referencedMethod.l
    val namedRef = reg.argument.argumentIndex(2).isIdentifier.name.l
    val byName = namedRef.flatMap(n => cpg.method.nameExact(n).l)
    val (bodies, link) =
      if (inline.nonEmpty) (inline, "inline-closure")
      else if (byName.nonEmpty) (byName, "named-handler")
      else (List.empty, "unresolved")

    // The selector this receiver was bound to, or nothing. `selector_link`
    // records which: a Page Object built on a guess fails against the wrong
    // element, so "unresolved" has to be distinguishable from "not looked for".
    val selector = selectorOf.getOrElse(receiver, "")
    triggerBuf += s"""{"id":"${esc(id)}","event":"${esc(event)}","link":"${esc(link)}",""" +
      s""""element":"${esc(receiver)}","selector":"${esc(selector)}",""" +
      s""""selector_link":"${esc(
        if (selector.nonEmpty) "dom-lookup"
        else "unresolved: no literal lookup binds this element — it is reached " +
             "by walking the DOM, so nothing in the code names it")}",""" +
      s""""enclosing":"${esc(reg.method.name)}",""" +
      s""""anchor":${anchor(file, line)}}"""

    // ---- 2. Outcomes reachable from this handler ----
    // The handler closure is the 2nd argument. Its body's DOM mutations are the
    // observable outcome (M-2). Scoped to the enclosing method rather than a
    // full data-flow walk: this pack reports what it can see, and says so.

    val mutations = bodies.flatMap { m =>
      m.ast.isCall.l.filter { c =>
        val code = c.code
        c.name == "setAttribute" || code.contains("classList.add") ||
        code.contains("classList.remove") || code.contains("classList.toggle") ||
        code.contains(".hidden") || c.name == "pushState" || c.name == "replaceState"
      }
    }.distinct

    mutations.zipWithIndex.foreach { case (mut, j) =>
      val kind =
        if (mut.name == "setAttribute") "attribute"
        else if (mut.code.contains("classList")) "class"
        else if (mut.code.contains("pushState") || mut.code.contains("replaceState")) "route"
        else "visibility"
      // The signature is what a user can actually distinguish (M-3). When no
      // literal is present the class or attribute name is computed at runtime
      // and is genuinely not recoverable statically. It is MARKED, never
      // replaced by the call's internal name: an earlier version fell back to
      // `mut.name` and emitted `<operator>.assignment` and `forEach` as if they
      // were observable states, which is exactly the fabricated-detail failure
      // T-9d prohibits -- caught by reading the output, not by a test.
      val detail = mut.argument.isLiteral.code.l.map(unquote)
        .filterNot(_.startsWith("<operator>")).mkString("|")
      val signature = if (detail.nonEmpty) detail else "__unrecoverable__"
      outcomeBuf += s"""{"id":"${esc(id)}-out-$j","trigger_id":"${esc(id)}",""" +
        s""""kind":"${esc(kind)}","signature":"${esc(signature)}","link":"${esc(link)}",""" +
        s""""code":"${esc(mut.code.take(120))}","anchor":${anchor(
          mut.file.name.headOption.getOrElse(""), mut.lineNumber)}}"""
    }

    // ---- 3. API calls: the evidence that PROPOSES an INVOKES link (M-5g) ----
    val networkCalls = bodies.flatMap { m =>
      m.ast.isCall.l.filter { c =>
        c.name == "fetch" || c.name == "open" || c.name == "send" ||
        c.code.contains("XMLHttpRequest") || c.code.contains("axios")
      }
    }.distinct

    networkCalls.foreach { call =>
      val url = call.argument.isLiteral.code.headOption.map(unquote).getOrElse("__unrecoverable__")
      invokeBuf += s"""{"trigger_id":"${esc(id)}","call":"${esc(call.name)}",""" +
        s""""url":"${esc(url)}","anchor":${anchor(
          call.file.name.headOption.getOrElse(""), call.lineNumber)}}"""
    }
  }

  val report =
    s"""{
  "pack": "js-ui",
  "pack_version": "0.1.0",
  "engine": "joern",
  "engine_version": "4.0.604",
  "frontend": "jssrc2cpg",
  "repo": "${esc(repo)}",
  "commit": "${esc(commit)}",
  "surface": "ui",
  "layers": [4],
  "triggers": [${triggerBuf.distinct.mkString(",")}],
  "outcomes": [${outcomeBuf.distinct.mkString(",")}],
  "api_calls": [${invokeBuf.distinct.mkString(",")}]
}"""

  new PrintWriter(out) { write(report); close() }
  println(s"wrote $out")
  println(s"  triggers=${triggerBuf.distinct.size} outcomes=${outcomeBuf.distinct.size} api_calls=${invokeBuf.distinct.size}")
  if (invokeBuf.isEmpty)
    println("  NOTE: zero API calls found. Every transition is client-side only " +
            "(M-5d); no INVOKES link is proposed, and none is a gap (A-17d).")
}
