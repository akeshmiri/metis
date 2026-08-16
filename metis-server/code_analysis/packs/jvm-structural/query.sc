// Query pack: JVM structural extraction, Layers 1-3 (application spec §13.4-13.7)
//
// Emits code_analysis.contract's `metis.cpg-extract/1` shape as JSON. The
// contract is the boundary: nothing downstream sees Joern's own types, so an
// engine upgrade touches this file and nothing else (spec X-3).
//
// Three rules are enforced *here*, in the pack, rather than downstream:
//   * REQ-CGA-010  external methods are filtered, never emitted as stubs
//   * X-6          every fact carries file:line@commit
//   * X-5          a partial parse is reported so the report can be refused
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

  // ---- Layer 1: methods and calls -------------------------------------
  // isExternal(false) is REQ-CGA-010: a stub for a third-party callee would be
  // a fabricated node, so it is excluded at the source.
  val internal = cpg.method.isExternal(false).filterNot(_.name.startsWith("<")).l

  val methods = internal.map { m =>
    s"""{"id":"${esc(m.fullName)}","name":"${esc(m.name)}",""" +
    s""""type_name":"${esc(m.typeDecl.name.headOption.getOrElse(""))}",""" +
    s""""signature":"${esc(m.signature)}","is_external":false,""" +
    s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
  }

  val internalNames = internal.map(_.fullName).toSet
  val calls = cpg.call
    .filter(c => internalNames.contains(c.methodFullName))
    .filter(c => c.method.fullName != null && internalNames.contains(c.method.fullName))
    .map { c =>
      s"""{"caller_id":"${esc(c.method.fullName)}","callee_id":"${esc(c.methodFullName)}",""" +
      s""""anchor":${anchor(c.method.filename, c.lineNumber)}}"""
    }.l.distinct

  // ---- Layer 2: endpoints ---------------------------------------------
  // Annotation names come from configuration (spec X-10b/X-4); an unrecognised
  // framework yields nothing here, which the mapper reports as a config problem
  // rather than as an empty service.
  val verbs = Map(
    "GetMapping" -> "GET", "PostMapping" -> "POST", "PutMapping" -> "PUT",
    "DeleteMapping" -> "DELETE", "PatchMapping" -> "PATCH", "RequestMapping" -> "ANY")

  // Real Spring code routes through constants far more often than string
  // literals -- `@GetMapping(COMMIT)` where `COMMIT = "/commit"`. An earlier
  // draft assumed literals and silently emitted mangled source text as the path.
  // Resolve what is resolvable; MARK what is not (spec T-9d, X-4). A guessed
  // route is worse than an absent one, because it looks usable.
  val UNRESOLVED = "__unresolved__"

  // String constants, keyed BOTH by declaring type and by simple name.
  // `.target`/`.source` are single nodes, so work on their `code` property
  // rather than treating them as traversals.
  //
  // Scoping by declaring type is load-bearing, not tidiness. Two TMS controllers
  // each declare a constant named `TMS_STATUS`: StatusController's is "/status",
  // PriorityController's is "/priority". A global simple-name map resolved BOTH
  // to "/status", so PriorityController's POST was extracted at the wrong route
  // and collided with StatusController's -- surfacing as a phantom determinism
  // failure on a model that was correct. Found by chasing that finding to the
  // source, not by a test.
  case class Const(owner: String, name: String, value: String)
  val declared: List[Const] = cpg.assignment.l.flatMap { a =>
    val lhs = a.target.code
    val rhs = a.source.code
    if (rhs.startsWith("\"")) {
      val owner = a.method.typeDecl.name.headOption.getOrElse("")
      Some(Const(owner, lhs.split("\\.").last.replaceAll("[^A-Za-z0-9_]", ""),
                 rhs.stripPrefix("\"").stripSuffix("\"")))
    } else None
  }
  val byOwner: Map[(String, String), String] =
    declared.map(c => (c.owner, c.name) -> c.value).toMap
  // A simple name is only usable globally when it is UNAMBIGUOUS.
  val globalConstants: Map[String, String] =
    declared.groupBy(_.name).collect {
      case (n, cs) if cs.map(_.value).distinct.size == 1 => n -> cs.head.value
    }

  def resolvePath(raw: String, owner: String = ""): String = {
    val expr = raw.replaceFirst("^[A-Za-z_]+\\s*=\\s*", "").trim
    if (expr.startsWith("\""))
      expr.replaceAll("^\"|\"$", "")
    else {
      // Concatenation: `CONSTANT + "/{id}"`. Every real @GetMapping("/{id}")
      // in this estate is written that way, so a resolver that handled only a
      // bare constant left 13 of 91 endpoints at `__unresolved__` -- and those
      // 13 then shared one trigger, producing 62 phantom determinism failures
      // on endpoints that are in fact distinct.
      //
      // Each operand is resolved independently and the results joined. An
      // operand that resolves to nothing makes the WHOLE path unresolved: a
      // partially-resolved route is a wrong route, and a wrong route is worse
      // than an admitted gap (§5.8).
      def resolveOperand(part: String): String = {
        val t = part.trim
        if (t.startsWith("\"")) t.replaceAll("^\"|\"$", "")
        else {
          val parts = t.split("\\.").map(_.replaceAll("[^A-Za-z0-9_]", "")).filter(_.nonEmpty)
          val simple = parts.lastOption.getOrElse("")
          val qualifier = if (parts.length > 1) parts(parts.length - 2) else owner
          byOwner.get((qualifier, simple))
            .orElse(byOwner.get((owner, simple)))
            .orElse(globalConstants.get(simple))
            .getOrElse(UNRESOLVED)
        }
      }

      // Split on `+` only outside string literals.
      val operands = scala.collection.mutable.ListBuffer[String]()
      var buf = new StringBuilder
      var inString = false
      expr.foreach { ch =>
        if (ch == '"') { inString = !inString; buf.append(ch) }
        else if (ch == '+' && !inString) { operands += buf.toString; buf = new StringBuilder }
        else buf.append(ch)
      }
      operands += buf.toString

      val resolvedParts = operands.toList.map(_.trim).filter(_.nonEmpty).map(resolveOperand)
      if (resolvedParts.isEmpty || resolvedParts.contains(UNRESOLVED)) UNRESOLVED
      else resolvedParts.mkString("")
    }
  }

  def classPrefix(m: Method): String = {
    val owner = m.typeDecl.name.headOption.getOrElse("")
    m.typeDecl.headOption.toList
      .flatMap(_.annotation.name("RequestMapping").parameterAssign.code.l)
      .headOption.map(r => resolvePath(r, owner)).filterNot(_ == UNRESOLVED).getOrElse("")
  }

  val endpoints = internal.flatMap { m =>
    m.annotation.l.flatMap { a =>
      verbs.get(a.name).map { verb =>
        val rawParam = a.parameterAssign.code.l.headOption
        val owner = m.typeDecl.name.headOption.getOrElse("")
        val resolved = rawParam.map(r => resolvePath(r, owner)).getOrElse("")
        val path =
          if (resolved == UNRESOLVED) UNRESOLVED
          else classPrefix(m) + resolved
        s"""{"id":"${esc(m.fullName)}::${esc(a.name)}","http_method":"$verb",""" +
        s""""path":"${esc(path)}","path_source":"${esc(rawParam.getOrElse(""))}",""" +
        s""""handler_method_id":"${esc(m.fullName)}",""" +
        s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
      }
    }
  }

  // ---- Layer 3: the verified type registry ----------------------------
  // This is what makes REQ-TST-008 mechanical: a field absent here fails
  // generation instead of producing a warning nobody reads.
  val members = cpg.typeDecl.isExternal(false).flatMap { t =>
    t.member.map { mem =>
      s"""{"type_name":"${esc(t.name)}","name":"${esc(mem.name)}",""" +
      s""""type_full_name":"${esc(mem.typeFullName)}",""" +
      s""""anchor":${anchor(t.filename, mem.lineNumber)}}"""
    }
  }.l

  // ---- X-5: partial-parse detection -----------------------------------
  // A file that produced no type declaration usually means the frontend failed
  // on it. Reporting it lets the contract refuse the whole report rather than
  // silently under-reporting.
  val parsedFiles = cpg.typeDecl.isExternal(false).filename.toSet.filter(_.nonEmpty)
  val allFiles = cpg.file.name.toSet.filter(n => n.endsWith(".java"))
  val unparsed = (allFiles -- parsedFiles).toList.sorted

  val json =
    s"""{
  "contract_version": "metis.cpg-extract/1",
  "pack": "jvm-structural",
  "pack_version": "0.1.0",
  "engine": "joern",
  "engine_version": "4.0.604",
  "repo": "${esc(repo)}",
  "commit": "${esc(commit)}",
  "frontend": "javasrc2cpg",
  "layers": [1, 2, 3],
  "methods": [${methods.mkString(",")}],
  "calls": [${calls.mkString(",")}],
  "endpoints": [${endpoints.mkString(",")}],
  "members": [${members.mkString(",")}],
  "checks": [],
  "outcomes": [],
  "parse_errors": [${unparsed.map(f => "\"" + esc(f) + "\"").mkString(",")}],
  "partial": ${unparsed.nonEmpty}
}"""

  new PrintWriter(out) { write(json); close() }
  println(s"wrote $out")
  println(s"  methods=${methods.size} calls=${calls.size} endpoints=${endpoints.size} members=${members.size}")
  println(s"  unparsed=${unparsed.size}")
}
