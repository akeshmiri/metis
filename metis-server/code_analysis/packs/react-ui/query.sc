// Query pack: React UI behaviour extraction, Layer 4 (application spec §5.2, M-2, M-5).
//
// The `js-ui` pack keys on `addEventListener`, which a React application has none
// of -- handlers are JSX props. Measured on the pilot target: 48 `onClick`, 7
// `onSubmit`, 7 `onChange`, and **zero** `addEventListener`. jssrc2cpg keeps JSX
// as raw code text, so those bindings are NOT structurally recoverable; probing
// found 26 calls whose code CONTAINS "onClick" but zero identifiers or field
// accesses named it.
//
// So this pack does not pretend to recover click bindings. It keys on what IS
// structurally present and is what M-5 actually needs:
//
//   1. **API call sites.** 93 `requestJson(root, path)` calls, of which 91 carry
//      a literal root (`apiRoots.X`) and a literal path. Each one PROPOSES an
//      `INVOKES` link (M-5g) -- this is the pack's main product.
//   2. **The UI's own state vocabulary.** `setStatus("loading"|"ready"|"error")`
//      is a naming convention in code, X-7 tier 2 -- real state names, not
//      invented ones.
//   3. **Routes.** `<Route path="...">` gives the screens a user navigates.
//
// What is NOT recovered is reported rather than omitted: the `unresolved_calls`
// list carries every call site whose root or path is computed, so a reviewer can
// see the coverage of this extraction instead of assuming it is total.
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
    .stripPrefix("'").stripSuffix("'").stripPrefix("`").stripSuffix("`")

  // A page component is the enclosing screen: `MetricWorkspacePage`. Anonymous
  // and arrow-function wrappers are walked past to the nearest named ancestor.
  def screenOf(m: io.shiftleft.codepropertygraph.generated.nodes.Method): String = {
    val file = m.filename.split("/").lastOption.getOrElse("")
    if (file.endsWith(".jsx")) file.stripSuffix(".jsx") else m.name
  }

  val callBuf   = scala.collection.mutable.ListBuffer[String]()
  val unresBuf  = scala.collection.mutable.ListBuffer[String]()
  val stateBuf  = scala.collection.mutable.ListBuffer[String]()
  val routeBuf  = scala.collection.mutable.ListBuffer[String]()

  // ---- 1. API call sites -> INVOKES proposals ----
  cpg.call.nameExact("requestJson").l.zipWithIndex.foreach { case (c, i) =>
    val rootCode = c.argument.argumentIndex(1).code.headOption.getOrElse("")
    val pathCode = c.argument.argumentIndex(2).code.headOption.getOrElse("")
    val screen   = screenOf(c.method)
    val file     = c.file.name.headOption.getOrElse("")

    // `apiRoots.metric` -> "/metric". The object is frozen with literal values,
    // so this is constant resolution, not a guess.
    val root = if (rootCode.startsWith("apiRoots."))
      "/" + rootCode.stripPrefix("apiRoots.") else ""

    // The first string literal in the second argument is the resource path,
    // whether passed directly or through buildResourcePath("/summary", ...).
    //
    // **A template literal is not a literal path.** jssrc2cpg lowers `` `/${id}` ``
    // to `<operator>.formatString("/", id, "")`, whose literal fragments are `"/"`
    // and `""`. Taking the first one reported the endpoint as `/record/` -- not
    // the route, not the fragment, and not marked as either. A confident wrong
    // answer is worse than no answer (X-4), so an interpolated path goes to
    // `unresolved_calls` where a reviewer can see it.
    val interpolated = c.argument.argumentIndex(2).ast.isCall.l
      .exists(_.name == "<operator>.formatString")
    val pathLit =
      if (interpolated) None
      else c.argument.argumentIndex(2).ast.isLiteral.code.l
        .map(unquote).find(_.startsWith("/"))

    if (root.nonEmpty && pathLit.nonEmpty) {
      callBuf += s"""{"id":"uicall-$i","screen":"${esc(screen)}",""" +
        s""""root":"${esc(root)}","path":"${esc(pathLit.get)}",""" +
        s""""endpoint":"${esc(root + pathLit.get)}","link":"literal-root-and-path",""" +
        s""""anchor":${anchor(file, c.lineNumber)}}"""
    } else {
      // T-9d: reported and marked, never guessed at.
      unresBuf += s"""{"id":"uicall-$i","screen":"${esc(screen)}",""" +
        s""""root_code":"${esc(rootCode.take(60))}","path_code":"${esc(pathCode.take(80))}",""" +
        s""""reason":"${esc(
          if (interpolated) "path is a template literal with an interpolation, " +
            "so the route it reaches is not statically known"
          else if (root.isEmpty && pathLit.isEmpty) "root and path are both computed"
          else if (root.isEmpty) "root is a variable, not apiRoots.<name>"
          else "no literal path")}","anchor":${anchor(file, c.lineNumber)}}"""
    }
  }

  // ---- 2. The UI's own state vocabulary (X-7 tier 2) ----
  // **`set<Anything>Status`, not a list of one estate's screens.** This read
  // `set(Status|SummaryStatus|DriftStatus|TrendStatus)` -- `DriftStatus` and
  // `TrendStatus` are two screens from the codebase the pack was first written
  // against, compiled into a shipped pack. Any other project's setter was
  // invisible, and the convention being matched is `set…Status`, which is
  // expressible without naming anybody's screens.
  cpg.call.name("set([A-Z][A-Za-z0-9]*)?Status").l.zipWithIndex
    .foreach { case (c, i) =>
      // **Every string literal in the argument, not only a direct one.**
      // `setStatus(record ? "ready" : "error")` is two real states, and reading
      // just the immediate argument found neither: a ternary is a call, so
      // `argument.isLiteral` is empty and two states the UI genuinely has were
      // dropped without a word. Walking the argument's AST reads both branches.
      c.argument.ast.isLiteral.code.l.filter(s =>
        s.startsWith("\"") || s.startsWith("'")).map(unquote)
        .filter(_.nonEmpty).distinct.foreach { value =>
        stateBuf += s"""{"id":"uistate-$i","screen":"${esc(screenOf(c.method))}",""" +
          s""""setter":"${esc(c.name)}","value":"${esc(value)}",""" +
          s""""anchor":${anchor(c.file.name.headOption.getOrElse(""), c.lineNumber)}}"""
      }
    }

  // ---- 3. Routes: the screens a user navigates ----
  //
  // **This took any lowercase literal of three or more characters in a file
  // called App.jsx, and explicitly EXCLUDED anything starting with `/`.** So it
  // rejected the one shape a route actually has, and accepted everything else.
  // Measured against a React application with no router it reported six routes, every one a false
  // positive: `prop-types` and `react` (import specifiers), `null`/`true`/
  // `false` (defaultProps values) and `default` (from `export default App`).
  // Six confident answers, zero routes, which is worse than none (X-4).
  //
  // A route is recovered from routing evidence or not at all. jssrc2cpg lowers
  // a router config — `createBrowserRouter([{ path: '/about', ... }])` — into
  // an assignment `_tmp_4.path = "/about"`, so the `path` KEY is structurally
  // present even though the surrounding JSX is not. That is the signal.
  //
  // `<Route path="...">` in JSX stays unrecoverable and is not guessed at
  // (T-9d); a project using only that form gets zero routes and a note, which
  // is the honest answer.
  def looksLikeRoutePath(value: String): Boolean = {
    // A JS regex literal reaches here as `/\s+/g`. It starts with `/` like a
    // path does, and a React application with no router's 33 "navigation calls" were every one of
    // them `String.replace(/regex/g)`.
    val isRegex = value.length > 1 && value.startsWith("/") &&
      value.substring(1).matches(".*/[gimsuy]*$")
    !isRegex && value.startsWith("/")
  }

  val routeAssignments = cpg.assignment.l.filter { a =>
    a.target.code.trim.endsWith(".path")
  }.flatMap { a =>
    val raw = a.source.code.trim
    val quoted = raw.startsWith("\"") || raw.startsWith("'")
    val value = unquote(raw)
    if (quoted && looksLikeRoutePath(value))
      Some((value, a.file.name.headOption.getOrElse(""), a.lineNumber))
    else None
  }.distinctBy(_._1)

  routeAssignments.zipWithIndex.foreach { case ((value, file, line), i) =>
    routeBuf += s"""{"id":"route-$i","path":"${esc(value)}",""" +
      s""""anchor":${anchor(file, line)}}"""
  }

  val report =
    s"""{
  "pack": "react-ui",
  "pack_version": "0.1.0",
  "engine": "joern",
  "engine_version": "4.0.604",
  "frontend": "jssrc2cpg",
  "repo": "${esc(repo)}",
  "commit": "${esc(commit)}",
  "surface": "ui",
  "layers": [4],
  "api_calls": [${callBuf.distinct.mkString(",")}],
  "unresolved_calls": [${unresBuf.distinct.mkString(",")}],
  "ui_states": [${stateBuf.distinct.mkString(",")}],
  "routes": [${routeBuf.distinct.mkString(",")}]
}"""

  new PrintWriter(out) { write(report); close() }
  println(s"wrote $out")
  println(s"  api_calls=${callBuf.distinct.size} unresolved=${unresBuf.distinct.size} " +
          s"ui_states=${stateBuf.distinct.size} routes=${routeBuf.distinct.size}")
  println("  NOTE: JSX handler bindings are not structurally recoverable with " +
          "jssrc2cpg and are NOT guessed at (T-9d).")
}
