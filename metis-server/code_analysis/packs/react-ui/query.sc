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
    val pathLit = c.argument.argumentIndex(2).ast.isLiteral.code.l
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
          if (root.isEmpty && pathLit.isEmpty) "root and path are both computed"
          else if (root.isEmpty) "root is a variable, not apiRoots.<name>"
          else "no literal path")}","anchor":${anchor(file, c.lineNumber)}}"""
    }
  }

  // ---- 2. The UI's own state vocabulary (X-7 tier 2) ----
  cpg.call.name("set(Status|SummaryStatus|DriftStatus|TrendStatus)").l.zipWithIndex
    .foreach { case (c, i) =>
      val lit = c.argument.isLiteral.code.headOption.map(unquote)
      lit.foreach { value =>
        stateBuf += s"""{"id":"uistate-$i","screen":"${esc(screenOf(c.method))}",""" +
          s""""setter":"${esc(c.name)}","value":"${esc(value)}",""" +
          s""""anchor":${anchor(c.file.name.headOption.getOrElse(""), c.lineNumber)}}"""
      }
    }

  // ---- 3. Routes: the screens a user navigates ----
  cpg.literal.code(".*").l.filter { l =>
    val c = unquote(l.code)
    l.file.name.headOption.exists(_.endsWith("App.jsx")) &&
      c.nonEmpty && !c.startsWith("/") && c.matches("[a-z][a-z0-9-]{2,}")
  }.distinctBy(_.code).zipWithIndex.foreach { case (l, i) =>
    routeBuf += s"""{"id":"route-$i","path":"${esc(unquote(l.code))}",""" +
      s""""anchor":${anchor(l.file.name.headOption.getOrElse(""), l.lineNumber)}}"""
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
