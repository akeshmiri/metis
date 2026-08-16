// Query pack: existing-test inventory (application spec REQ-METIS-PG-01).
//
// Answers one question: **what do the tests that already exist cover?** Without
// it, generation is not additive -- Métis emits a case per transition regardless,
// and on the pilot target 5 of 6 cases generated for one service duplicated an
// integration test that was already passing.
//
// The join is NOT the obvious one, and the obvious one is wrong:
//
//   * There are **no `CALLS` edges from an integration test to a controller.**
//     The hop is HTTP at runtime, so nothing links them statically.
//   * **Method-name matching does not work.** The real test for `GET /metric/all`
//     is called `shallReturnInventoryPageWhenValidFiltersProvided` -- it shares
//     no word with the route it exercises.
//
// The join that does work, verified against the real CPG before this pack was
// written, is the **Feign client**:
//
//     MetricControllerIT.shallReturnInventoryPage…
//        --calls-->  MetricFeignClient.getAll
//        --@RequestLine("GET /metric/all?…")-->  GET /all
//
// The Feign interface is the one place where a test's intent is written down as
// a route. 18 `*ControllerIT` classes and 143 `@RequestLine` methods were found
// this way on the pilot estate.
//
// **What this pack does NOT claim.** Reaching an endpoint is evidence for that
// endpoint's happy path, not for every outcome it can produce. A test that calls
// `GET /{id}` and asserts 200 says nothing about the 204 path. The `asserts`
// field carries whatever status literals the test body contains so the caller can
// grade outcome coverage separately; this pack never concludes "covered".
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

  def unquote(s: String): String =
    s.trim.stripPrefix("\"").stripSuffix("\"").trim

  // ---- 1. Index every Feign method by the route it declares ----
  // `@RequestLine("GET /metric/all?page={page}")` -> ("GET", "/metric/all")
  val routeOf = scala.collection.mutable.Map[String, (String, String)]()
  cpg.method.where(_.annotation.name("RequestLine")).l.foreach { m =>
    val raw = m.annotation.name("RequestLine").parameterAssign.code.l.headOption
      .map(unquote).getOrElse("")
    val cleaned = raw.replaceFirst("^[A-Za-z_]+\\s*=\\s*", "").trim
      .stripPrefix("\"").stripSuffix("\"")
    val parts = cleaned.split("\\s+", 2)
    if (parts.length == 2) {
      val verb = parts(0).toUpperCase
      val path = parts(1).split("\\?")(0).trim
      if (verb.nonEmpty && path.startsWith("/")) routeOf(m.fullName) = (verb, path)
    }
  }

  // Spring `@GetMapping` on a Feign interface is the other convention in use.
  val verbs = Map("GetMapping" -> "GET", "PostMapping" -> "POST", "PutMapping" -> "PUT",
                  "DeleteMapping" -> "DELETE", "PatchMapping" -> "PATCH")
  cpg.method.l.foreach { m =>
    if (!routeOf.contains(m.fullName)) {
      m.annotation.l.foreach { a =>
        verbs.get(a.name).foreach { verb =>
          val p = a.parameterAssign.code.l.headOption.map(unquote)
            .map(_.replaceFirst("^[A-Za-z_]+\\s*=\\s*", "").trim
              .stripPrefix("\"").stripSuffix("\"")).getOrElse("")
          if (p.startsWith("/")) routeOf(m.fullName) = (verb, p.split("\\?")(0))
        }
      }
    }
  }

  // ---- 2. Every test method, and the routes it reaches through Feign ----
  val testBuf = scala.collection.mutable.ListBuffer[String]()
  val unresolvedBuf = scala.collection.mutable.ListBuffer[String]()

  // A test is a method carrying @Test. Its owning class decides the LEVEL:
  // `*IT` is an integration/api_functional suite; anything else is a unit test.
  val tests = cpg.method.where(_.annotation.name("Test")).l

  tests.zipWithIndex.foreach { case (t, i) =>
    val owner = t.typeDecl.name.headOption.getOrElse("")
    val file = t.filename
    val isIT = owner.endsWith("IT") || file.contains("/it/")
    val isController = owner.contains("Controller")
    val level =
      if (isIT && isController) "api_functional"
      else if (isIT) "integration"
      else "unit"

    // Routes reached DIRECTLY, and one hop through a helper in the same class --
    // `saveAndVerifyMetric` is a helper the real tests call, and the endpoint it
    // exercises belongs to its callers.
    val direct = t.call.callee.fullName.l
    val viaHelper = t.call.callee.filter(_.typeDecl.name.headOption.contains(owner))
      .call.callee.fullName.l
    val reached = (direct ++ viaHelper).distinct.flatMap(routeOf.get).distinct

    // Status literals asserted in the body OR in a same-class helper it calls.
    // The helper hop is not optional: the real assertion for POST is
    // `assertThat(response.status(), equalTo(201))` inside `saveAndVerifyMetric`,
    // a private helper -- collecting literals from the test method alone found
    // nothing and graded a genuinely covered outcome as unproven.
    //
    // Deliberately raw: deciding what a literal PROVES is the caller's job, not
    // this pack's.
    val helperBodies = t.call.callee
      .filter(_.typeDecl.name.headOption.contains(owner)).l
    val statuses = (t.ast.isLiteral.code.l ++ helperBodies.flatMap(_.ast.isLiteral.code.l))
      .map(_.trim).filter(s => s.matches("[1-5]\\d{2}")).distinct

    if (reached.nonEmpty) {
      val routes = reached.map { case (v, p) =>
        s"""{"verb":"${esc(v)}","path":"${esc(p)}"}""" }.mkString(",")
      testBuf += s"""{"id":"test-$i","name":"${esc(t.name)}","owner":"${esc(owner)}",""" +
        s""""level":"${esc(level)}","routes":[$routes],""" +
        s""""asserts":[${statuses.map(s => s""""$s"""").mkString(",")}],""" +
        s""""anchor":${anchor(file, t.lineNumber)}}"""
    } else {
      // Reported, never silently dropped: a test whose target cannot be resolved
      // must not be counted as covering anything, and must not vanish either.
      unresolvedBuf += s"""{"name":"${esc(t.name)}","owner":"${esc(owner)}",""" +
        s""""level":"${esc(level)}","reason":"no Feign route reached from this test",""" +
        s""""anchor":${anchor(file, t.lineNumber)}}"""
    }
  }

  val report =
    s"""{
  "pack": "jvm-test-inventory",
  "pack_version": "0.1.0",
  "engine": "joern",
  "engine_version": "4.0.604",
  "frontend": "javasrc2cpg",
  "repo": "${esc(repo)}",
  "commit": "${esc(commit)}",
  "layers": [3],
  "feign_routes_indexed": ${routeOf.size},
  "tests": [${testBuf.distinct.mkString(",")}],
  "unresolved": [${unresolvedBuf.distinct.mkString(",")}]
}"""

  new PrintWriter(out) { write(report); close() }
  println(s"wrote $out")
  println(s"  feign_routes=${routeOf.size} tests_with_routes=${testBuf.distinct.size} " +
          s"unresolved=${unresolvedBuf.distinct.size}")
  println("  NOTE: reaching an endpoint evidences its HAPPY PATH only. This pack " +
          "never concludes 'covered' -- see test_levels.py for the grading.")
}
