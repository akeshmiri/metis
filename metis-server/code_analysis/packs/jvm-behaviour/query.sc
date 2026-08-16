// Query pack: JVM behaviour extraction, Layer 4 (application spec §5.2-§5.4)
//
// Recovers the three things a user-perspective transition needs from an API
// surface (spec M-2): the trigger (an endpoint), the observable outcome (a
// response condition), and the guard selecting between outcomes.
//
// Two measured facts shape this pack, both established by probing the real
// pilot target rather than assumed:
//
//   1. Response construction is delegated to a shared utility. Analysed as one
//      module the helper is invisible; the analysis unit must be the
//      multi-module build (spec O-2c).
//   2. Even combined, `callee()` yields <unresolvedSignature> for generic
//      helpers, because javasrc2cpg cannot resolve them without dependencies.
//      Linking therefore falls back to **name matching**, which is a heuristic
//      and is reported as one -- `link` records how each edge was resolved so a
//      reviewer can weigh it (spec T-9d: mark, never guess silently).
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

  val verbs = Map("GetMapping" -> "GET", "PostMapping" -> "POST", "PutMapping" -> "PUT",
                  "DeleteMapping" -> "DELETE", "PatchMapping" -> "PATCH")

  // ---- terminal outcome helpers -> status codes ------------------------
  // A helper whose body constructs a ResponseEntity with a recognisable status.
  // Anything unrecognised stays unmapped rather than being assigned a guess.
  val statusPatterns = List(
    ("noContent", 204), ("ok", 200), ("created", 201),
    ("conflicted", 409), ("alreadyReported", 208), ("updated", 200))

  val outcomeHelpers: Map[String, Int] = cpg.method.isExternal(false).l.flatMap { m =>
    statusPatterns.collectFirst { case (n, code) if m.name == n => m.name -> code }
  }.toMap

  // ---- Layer 4: per handler, the outcomes and their guards -------------
  val handlers = cpg.method.isExternal(false)
    .filter(_.annotation.name.exists(verbs.contains)).l

  var checkId = 0
  val checkBuf = scala.collection.mutable.ListBuffer[String]()
  val outcomeBuf = scala.collection.mutable.ListBuffer[String]()

  handlers.foreach { m =>
    val verb = m.annotation.name.l.flatMap(verbs.get).headOption.getOrElse("ANY")
    val endpointId = s"${m.fullName}::${verb}"

    // Declared outcomes: @ApiResponse(responseCode = "NNN"). These are a real
    // code fact, not intent -- they are compiled annotations on the handler.
    val declaredBlob = m.annotation.name("Operation").parameterAssign.code.l.mkString(" ")
    val declared = "responseCode = \"(\\d+)\"".r.findAllMatchIn(declaredBlob)
      .map(_.group(1).toInt).toList.distinct

    // Constructed outcomes: follow the return expression into a helper, by name
    // (see the header note on why callee() is insufficient here).
    val returnCalls = m.ast.isReturn.astChildren.isCall.l
    returnCalls.foreach { rc =>
      val helperName = rc.name
      val helperMethods = cpg.method.isExternal(false).nameExact(helperName).l

      helperMethods.foreach { h =>
        // A ternary in the helper is the branch point: (cond, whenTrue, whenFalse).
        val conditionals = h.call.nameExact("<operator>.conditional").l
        conditionals.foreach { c =>
          val args = c.argument.code.l
          if (args.size == 3) {
            checkId += 1
            val cid = s"chk-$checkId"
            checkBuf += s"""{"id":"${esc(cid)}","expression":"${esc(args(0))}",""" +
              s""""order":$checkId,"dimension_class":null,""" +
              s""""anchor":${anchor(h.filename, c.lineNumber)}}"""

            // whenTrue / whenFalse each name a terminal helper -> a status code
            List((args(1), true), (args(2), false)).foreach { case (branch, isTrue) =>
              val fn = branch.takeWhile(_ != '(').split("\\.").last.trim
              outcomeHelpers.get(fn).foreach { status =>
                val sense = if (isTrue) "" else "!"
                outcomeBuf += s"""{"id":"${esc(endpointId)}::$status","endpoint_id":"${esc(endpointId)}",""" +
                  s""""signature":"$status/${esc(fn)}","status":$status,""" +
                  s""""discriminator":"${esc(fn)}","guarding_check_ids":["${esc(cid)}"],""" +
                  s""""guard_sense":"$sense","link":"name-match",""" +
                  s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
              }
            }
          }
        }

        // A helper with no branch produces exactly one outcome unconditionally.
        if (conditionals.isEmpty) {
          outcomeHelpers.get(helperName).foreach { status =>
            outcomeBuf += s"""{"id":"${esc(endpointId)}::$status","endpoint_id":"${esc(endpointId)}",""" +
              s""""signature":"$status/${esc(helperName)}","status":$status,""" +
              s""""discriminator":"${esc(helperName)}","guarding_check_ids":[],""" +
              s""""guard_sense":"","link":"name-match",""" +
              s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
          }
        }
      }

      // ---- Pass 2: guards from enclosing control structures ----
      //
      // The ternary pass above recovers `okOrNoContent`-style helpers. It cannot
      // see the other dominant shape in this estate: try/catch with nested ifs,
      // where a handler returns 201 on the happy path, 208 when a constraint
      // violation finds an existing row, and 409 otherwise. Those returns have
      // no ternary and no recovered guard at all, which left them mutually
      // ambiguous and blocked generation (M-18) for 18 real endpoints.
      //
      // **This is AST enclosure, not control dependence, and it is labelled as
      // such.** `controlledBy` returns empty for these methods under
      // javasrc2cpg -- the CDG is not linked -- so the guard is derived from
      // which control structures lexically CONTAIN the return. That is a weaker
      // claim: it is exact for the structured code here, and it would misread a
      // `break`/`continue` that escapes a block. `link` records
      // `ast-enclosure` so a reviewer can weigh it (T-9d), never `cdg`.
      val enclosed = returnCalls.map { rc =>
        val chain = rc.inAst.isControlStructure.l.reverse
        val conds = chain.flatMap { cs =>
          val c = cs.condition.code.headOption.getOrElse("")
          if (c.nonEmpty) Some(c)
          else if (cs.controlStructureType == "CATCH") Some("an exception is thrown")
          else None
        }
        (rc, chain.map(_.controlStructureType), conds)
      }
      // Returns with NO enclosing control structure are NOT discarded: a handler
      // that returns early inside an `if` and then falls through to a final
      // return has an unenclosed fall-through whose guard is the negation of its
      // guarded siblings. Filtering those out made the pass see one branch,
      // skip the method entirely, and leave both outcomes unguarded.

      if (enclosed.size > 1) {
        // GD-2's prefix rule: within one catch block, the return guarded by MORE
        // conditions is the specific case; the one guarded by fewer is the
        // fall-through and carries the negation of the specific case. Without
        // this the two overlap and determinism fails on a model that is in fact
        // deterministic.
        val maxDepth = enclosed.map(_._3.size).max
        enclosed.foreach { case (rc, kinds, conds) =>
          val fn = rc.name
          outcomeHelpers.get(fn).foreach { status =>
            val inTry = kinds.contains("TRY") && !kinds.contains("CATCH")
            val positive =
              if (inTry) List("no exception is thrown")
              else conds
            val specific = enclosed.filter(e => e._3.size == maxDepth && e._1 != rc)
              .flatMap(_._3).filterNot(positive.contains).distinct
            val expression =
              if (conds.size < maxDepth && specific.nonEmpty)
                (positive.filterNot(_ == "no exception is thrown")
                  ::: specific.map(c => s"NOT ($c)")).mkString(" AND ")
              else positive.mkString(" AND ")

            if (expression.nonEmpty) {
              checkId += 1
              val cid = s"chk-$checkId"
              checkBuf += s"""{"id":"${esc(cid)}","expression":"${esc(expression)}",""" +
                s""""order":$checkId,"dimension_class":null,""" +
                s""""anchor":${anchor(m.filename, rc.lineNumber)}}"""
              outcomeBuf += s"""{"id":"${esc(endpointId)}::$status","endpoint_id":"${esc(endpointId)}",""" +
                s""""signature":"$status/${esc(fn)}","status":$status,""" +
                s""""discriminator":"${esc(fn)}","guarding_check_ids":["${esc(cid)}"],""" +
                s""""guard_sense":"","link":"ast-enclosure",""" +
                s""""anchor":${anchor(m.filename, rc.lineNumber)}}"""
            }
          }
        }
      }

      // Declared-but-not-constructed: recorded so the mapper can compare the two
      // and report a divergence rather than silently preferring one.
      declared.foreach { code =>
        outcomeBuf += s"""{"id":"${esc(endpointId)}::declared-$code","endpoint_id":"${esc(endpointId)}",""" +
          s""""signature":"$code/declared","status":$code,"discriminator":"declared",""" +
          s""""guarding_check_ids":[],"guard_sense":"","link":"declared",""" +
          s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
      }
    }
  }

  val json =
    s"""{
  "contract_version": "metis.cpg-extract/1",
  "pack": "jvm-behaviour",
  "pack_version": "0.1.0",
  "engine": "joern",
  "engine_version": "4.0.604",
  "repo": "${esc(repo)}",
  "commit": "${esc(commit)}",
  "frontend": "javasrc2cpg",
  "layers": [4],
  "methods": [], "calls": [], "endpoints": [], "members": [],
  "checks": [${checkBuf.distinct.mkString(",")}],
  "outcomes": [${outcomeBuf.distinct.mkString(",")}],
  "parse_errors": [],
  "partial": false
}"""

  new PrintWriter(out) { write(json); close() }
  println(s"wrote $out")
  println(s"  handlers=${handlers.size} checks=${checkBuf.distinct.size} outcomes=${outcomeBuf.distinct.size}")
}
