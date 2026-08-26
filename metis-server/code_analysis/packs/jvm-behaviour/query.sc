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
//         --param repo=<name> --param out=<file.json> \
//         [--param constructors=ResponseEntity.ok:200,ResponseEntity.created:201]
//
// `constructors` is HOW THIS FRAMEWORK BUILDS A RESPONSE, supplied by
// `code_analysis.framework_config`'s `response_constructors`. It used to be a
// list in this file matching INTERNAL methods named ok/created/conflicted --
// one estate's response helpers. A codebase using Spring's own
// `ResponseEntity.ok(...)` matched nothing, so no construction was recovered
// and synthesis produced an empty model from eleven handlers. The default below
// keeps this script runnable by hand; the engine always passes the real set.

import java.io.PrintWriter

@main def main(cpgPath: String, commit: String, repo: String, out: String,
               constructors: String = "", annotations: String = "") = {
  importCpg(cpgPath)

  // ---- the annotation table (see code_analysis/annotations.py) -----------
  //
  // `name<TAB>role<TAB>detail`, merged from the framework config and the
  // project profile by `engine.annotation_table`. The tables below used to be
  // literals here, which meant an annotation nobody had thought of was
  // invisible — `@ProjectSecured` on every endpoint recovered no security fact and
  // reported nothing missing.
  //
  // The built-in defaults survive so this script stays runnable by hand against
  // a plain Spring codebase; when the engine runs it, the file wins.
  val annotationRoles: Map[String, (String, String)] =
    if (annotations.trim.isEmpty) Map.empty
    else scala.io.Source.fromFile(annotations).getLines()
      .filterNot(_.startsWith("#")).filter(_.contains("\t"))
      .map { line =>
        val parts = line.split("\t", -1)
        parts(0).trim -> (parts(1).trim,
                          if (parts.length > 2) parts(2).trim else "")
      }.toMap

  def named(role: String): Map[String, String] =
    annotationRoles.collect { case (n, (r, d)) if r == role => n -> d }

  def hasRole(name: String, role: String): Boolean =
    annotationRoles.get(name).exists(_._1 == role)


  def esc(s: String): String =
    if (s == null) "" else s.replace("\\", "\\\\").replace("\"", "\\\"")
      .replace("\n", " ").replace("\r", " ").replace("\t", " ")

  def anchor(file: String, line: Option[Int]): String =
    s"""{"file":"${esc(file)}","line":${line.getOrElse(0)},"commit":"${esc(commit)}"}"""

  val declaredVerbs = named("entry_point")
  val verbs = if (declaredVerbs.nonEmpty) declaredVerbs else
    Map("GetMapping" -> "GET", "PostMapping" -> "POST", "PutMapping" -> "PUT",
        "DeleteMapping" -> "DELETE", "PatchMapping" -> "PATCH",
        // `RequestMapping` was absent here while jvm-structural carried it, so a
        // stereotype composing it resolved to a handler there and to nothing
        // here. The two packs must agree on what a handler IS or the join in
        // `synthesis` silently falls back to a bare verb for its trigger.
        "RequestMapping" -> "ANY")

  // ---- Annotation composition, overrides, controller identity ----------
  //
  // Duplicated from jvm-structural because a pack is a standalone script. The
  // two must agree: `synthesis` joins an outcome to its endpoint on the handler
  // method's fullName, and when they disagree the outcome does not join and the
  // transition gets a bare verb ("GET") with no route as its trigger. Measured:
  // three such transitions appeared the moment jvm-structural learned to resolve
  // composition and this pack had not.
  //
  // Ported from github/codeql (MIT, (c) GitHub, Inc.).
  val annotationDecls: Map[String, List[Annotation]] =
    cpg.typeDecl
      .filter(_.annotation.name.l.exists(n => n == "Retention" || n == "Target"))
      .map(td => td.name -> td.annotation.l)
      .toMap

  def composedWith(a: Annotation, seen: Set[String] = Set.empty): List[Annotation] =
    if (seen.contains(a.name)) Nil
    else a :: annotationDecls.getOrElse(a.name, Nil)
      .flatMap(meta => composedWith(meta, seen + a.name))

  def verbOf(a: Annotation): Option[String] =
    composedWith(a).flatMap { c =>
      verbs.get(c.name).map {
        case "ANY" =>
          c.parameterAssign.code.l
            .flatMap("^\\s*method\\s*=\\s*(.+)$".r.findFirstMatchIn(_))
            .map(_.group(1).split("\\.").last.replaceAll("[^A-Za-z]", "").toUpperCase)
            .find(_.nonEmpty).getOrElse("ANY")
        case verb => verb
      }
    }.headOption

  def supertypesOf(td: TypeDecl, depth: Int = 0): List[TypeDecl] =
    if (depth > 8) Nil
    else td.inheritsFromTypeFullName.toList
      .filterNot(_ == "java.lang.Object")
      .flatMap(fn => cpg.typeDecl.fullNameExact(fn).l)
      .flatMap(sup => sup :: supertypesOf(sup, depth + 1))

  def overridden(m: Method): List[Method] =
    m.typeDecl.headOption.toList
      .flatMap(supertypesOf(_))
      .flatMap(_.method.nameExact(m.name).l)
      .filter(_.signature == m.signature)

  def mappingAnnotations(m: Method): List[Annotation] =
    (m :: overridden(m)).flatMap(_.annotation.l)

  def ownerAnnotations(m: Method): List[Annotation] =
    m.typeDecl.headOption.toList
      .flatMap(td => td :: supertypesOf(td))
      .flatMap(_.annotation.l)
      .flatMap(a => composedWith(a))

  def isController(m: Method): Boolean =
    ownerAnnotations(m).exists(a => a.name == "Controller" || a.name == "RestController")

  def returnsResponseBody(m: Method): Boolean =
    ownerAnnotations(m).exists(_.name == "RestController") ||
      (m :: overridden(m)).flatMap(_.annotation.l).exists(_.name == "ResponseBody") ||
      ownerAnnotations(m).exists(_.name == "ResponseBody")

  // `@ResponseStatus(HttpStatus.CREATED)` is written by name far more often than
  // by number. Only the ones a handler realistically declares -- an exhaustive
  // table would be inventing support for statuses nothing here has seen.
  // Kept in step with jvm-structural's table on purpose: two packs disagreeing
  // about what `HttpStatus.CONFLICT` means is a hazard of its own, and the 4xx
  // names are needed here now that `status(...)` arguments are resolved below.
  val httpStatusNames = List(
    "NO_CONTENT" -> 204, "CREATED" -> 201, "ACCEPTED" -> 202,
    "OK" -> 200, "RESET_CONTENT" -> 205, "PARTIAL_CONTENT" -> 206,
    "ALREADY_REPORTED" -> 208, "BAD_REQUEST" -> 400, "UNAUTHORIZED" -> 401,
    "PAYMENT_REQUIRED" -> 402, "FORBIDDEN" -> 403, "NOT_FOUND" -> 404,
    "METHOD_NOT_ALLOWED" -> 405, "NOT_ACCEPTABLE" -> 406, "REQUEST_TIMEOUT" -> 408,
    "CONFLICT" -> 409, "GONE" -> 410, "PRECONDITION_FAILED" -> 412,
    "PAYLOAD_TOO_LARGE" -> 413, "UNSUPPORTED_MEDIA_TYPE" -> 415,
    "UNPROCESSABLE_ENTITY" -> 422, "LOCKED" -> 423, "FAILED_DEPENDENCY" -> 424,
    "PRECONDITION_REQUIRED" -> 428, "TOO_MANY_REQUESTS" -> 429,
    "INTERNAL_SERVER_ERROR" -> 500, "NOT_IMPLEMENTED" -> 501,
    "BAD_GATEWAY" -> 502, "SERVICE_UNAVAILABLE" -> 503, "GATEWAY_TIMEOUT" -> 504)

  // ---- how a response is constructed -----------------------------------
  //
  // Two shapes, and both are real:
  //
  //   INTERNAL helper   `okOrNoContent(...)` -- a method in this codebase whose
  //                     body builds the response. The ternary inside it is the
  //                     branch point, which is how a guard is recovered.
  //   FRAMEWORK call    `ResponseEntity.ok(...)` -- the framework's own static
  //                     factory. External, so no method body to inspect, and
  //                     the status is the call itself.
  //
  // The pack used to see only the first, with a hardcoded list of helper names.
  // Anything unrecognised still stays unmapped rather than being assigned a
  // guess.
  val declaredConstructors: List[(String, Int)] =
    (if (constructors.trim.isEmpty)
       "ResponseEntity.ok:200,ResponseEntity.created:201,ResponseEntity.accepted:202," +
       "ResponseEntity.noContent:204,ResponseEntity.badRequest:400," +
       "ResponseEntity.notFound:404"
     else constructors)
      .split(",").toList.map(_.trim).filter(_.nonEmpty).flatMap { pair =>
        pair.split(":").toList match {
          case expr :: code :: Nil => scala.util.Try(code.trim.toInt).toOption
                                        .map(c => (expr.trim, c))
          case _ => None
        }
      }

  // The bare method name of each declared constructor: `ResponseEntity.ok` -> `ok`.
  val statusPatterns: List[(String, Int)] =
    declaredConstructors.map { case (expr, code) => (expr.split("\\.").last, code) }

  val internalFullNames: Set[String] = cpg.method.isExternal(false).fullName.toSet

  val outcomeHelpers: Map[String, Int] = cpg.method.isExternal(false).l.flatMap { m =>
    statusPatterns.collectFirst { case (n, code) if m.name == n => m.name -> code }
  }.toMap

  // A call ON the framework, rather than a call INTO this codebase.
  //
  // **Matched on `methodFullName`, not on `code`.** javasrc2cpg writes the call
  // site with the receiver STRIPPED -- `ResponseEntity.ok(x)` has
  // `code = "ok(x)"` -- so matching the written expression finds nothing, while
  // `methodFullName` carries `org.springframework.http.ResponseEntity.ok:...`
  // in full. Using `code` would also credit any local method called `ok`.
  def frameworkStatus(fullName: String): Option[Int] =
    declaredConstructors.collectFirst {
      case (expr, status) if fullName.contains("." + expr + ":") ||
                             fullName.startsWith(expr + ":") => status
    }

  def constructedStatus(fullName: String, name: String): Option[Int] =
    outcomeHelpers.get(name).orElse(frameworkStatus(fullName))

  // **A builder chain puts the status on an INNER call.** `returnCalls` takes the
  // direct child of `return`, which for the two commonest Spring idioms is the
  // wrong node:
  //
  //     return ResponseEntity.noContent().build();          // outermost: build
  //     return ResponseEntity.status(CREATED).body(saved);  // outermost: body
  //
  // Neither `build` nor `body` carries a status, so both fell through to the
  // spring-serialisation default and were reported as **200**. Measured on the
  // demo corpus: a 201 handler and a 204 handler, both reported 200. Only the
  // single-call form `ResponseEntity.ok(x)` ever matched.
  //
  // So the whole return expression is searched, outermost first. `status(...)`
  // is resolved from its argument, which is the only form that can carry a body
  // with a 4xx and therefore the one every error handler uses.
  // Returns the status AND the call that carried it. The name matters: it becomes
  // the outcome's `discriminator`, which landing turns into a state name a person
  // reads. Naming it after the trailing builder call gave `RecordCreateBody201`
  // and `RecordRemoveBuild204` -- `body` and `build` say nothing about the
  // outcome. Named after what set the status they read `...Created201` and
  // `...NoContent204`.
  def chainStatus(rc: Call): Option[(Int, String)] = {
    val inner = rc.ast.isCall.l
    def lowerCamel(constant: String): String = {
      val parts = constant.split("_").toList.map(_.toLowerCase)
      (parts.headOption.getOrElse("") ::
        parts.drop(1).map(w => w.take(1).toUpperCase + w.drop(1))).mkString
    }
    constructedStatus(rc.methodFullName, rc.name).map(s => (s, rc.name))
      .orElse(inner.flatMap(c =>
        constructedStatus(c.methodFullName, c.name).map(s => (s, c.name))).headOption)
      .orElse(inner.filter(c => c.methodFullName.contains(".status:") ||
                                c.methodFullName.contains(".valueOf:"))
                .flatMap { c =>
                  c.argument.l.filterNot(_.argumentIndex == 0).flatMap { a =>
                    val simple = a.code.split("\\.").last
                      .replaceAll("[^A-Za-z0-9_]", "").trim
                    httpStatusNames.collectFirst { case (n, code) if n == simple =>
                      (code, lowerCamel(n)) }
                      .orElse(scala.util.Try(simple.toInt).toOption.map(i => (i, "status")))
                  }
                }.headOption)
  }

  // ---- Layer 4: per handler, the outcomes and their guards -------------
  // **A `@FeignClient` interface is not an API surface** — the same exclusion
  // `jvm-structural` makes, and it has to be made here too. Its `@PostMapping`s
  // declare calls this service MAKES of another one. It was harmless while this
  // pack recovered only constructed outcomes (a Feign interface has no body to
  // construct anything in); the moment Spring's serialisation contract was
  // recognised, every Feign declaration became a transition for an endpoint
  // this service does not serve — and one of them blocked validation.
  def isOutboundClient(m: Method): Boolean = {
    val markers = named("outbound_client").keys.toSet match {
      case s if s.nonEmpty => s
      case _ => Set("FeignClient")
    }
    // Through composition, matching jvm-structural: a house stereotype wrapping
    // `@FeignClient` used to escape this and become behaviour for a route the
    // service does not serve.
    m.typeDecl.headOption.toList.flatMap(_.annotation.l)
      .exists(a => composedWith(a).exists(c => markers.contains(c.name)))
  }

  // The same three conditions jvm-structural applies, in the same order. A
  // handler is a method ON A CONTROLLER whose mapping may be inherited, and
  // whose return value is a response body rather than a view name.
  val handlers = cpg.method.isExternal(false)
    .filter(m => mappingAnnotations(m).exists(a => verbOf(a).nonEmpty))
    .filterNot(isOutboundClient)
    .filter(isController)
    .filter(returnsResponseBody).l

  var checkId = 0
  val checkBuf = scala.collection.mutable.ListBuffer[String]()
  val outcomeBuf = scala.collection.mutable.ListBuffer[String]()

  handlers.foreach { m =>
    val verb = mappingAnnotations(m).flatMap(verbOf).headOption.getOrElse("ANY")
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
      // **Only when the call actually resolves INTO this codebase.** The lookup
      // is by bare name, which is deliberate -- `callee()` is insufficient here --
      // but it matched any internal method sharing the name, so a codebase
      // declaring its own `ok(...)` made every handler that calls
      // `ResponseEntity.ok(...)` emit a second, spurious outcome for the same
      // status. Measured on the demo corpus the moment such a helper existed:
      // `ScopedController` reported (200, name-match) beside (200, constructed).
      //
      // `ResponseEntity.ok` resolves to `org.springframework...`, which is not an
      // internal fullName; a real helper call resolves to one.
      val resolvesInternally = internalFullNames.contains(rc.methodFullName)
      val helperMethods =
        if (resolvesInternally) cpg.method.isExternal(false).nameExact(helperName).l
        else Nil

      helperMethods.foreach { h =>
        // A ternary in the helper is the branch point: (cond, whenTrue, whenFalse).
        val conditionals = h.call.nameExact("<operator>.conditional").l
        conditionals.foreach { c =>
          val args = c.argument.code.l
          if (args.size == 3) {
            checkId += 1
            val cid = s"chk-$checkId"
            // The endpoint whose handler this condition was found in. A check
            // whose branches resolve to a status is referenced by the outcome
            // emitted below; one whose branches do not is referenced by nothing,
            // and without this it lands connected to nothing at all. The
            // condition is real either way, so it is attached rather than dropped.
            checkBuf += s"""{"id":"${esc(cid)}","expression":"${esc(args(0))}",""" +
              s""""endpoint_id":"${esc(endpointId)}",""" +
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
        constructedStatus(rc.methodFullName, fn).map(s => (s, fn))
          .orElse(chainStatus(rc)).foreach { case (status, _) =>
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
              s""""endpoint_id":"${esc(endpointId)}",""" +
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

    // **A handler with ONE outcome is still a transition.**
    //
    // The guarded pass above only runs when a handler has more than one
    // return, because its whole job is to tell competing outcomes apart. A
    // handler that unconditionally returns `ResponseEntity.ok(...)` has
    // nothing to tell apart and was therefore emitted as nothing at all --
    // every one of demo_project/records-service's twelve endpoints, so synthesis saw no
    // constructed outcome anywhere and produced an empty model.
    //
    // The guard is empty, and that is the honest representation: three of the
    // login model's seventeen transitions are unguarded, and
    // `Transition.guard_expression` is in `may_be_empty` for exactly this.
    if (enclosed.size == 1) {
      val (rc, _, _) = enclosed.head
      chainStatus(rc).foreach { case (status, how) =>
        outcomeBuf += s"""{"id":"${esc(endpointId)}::$status","endpoint_id":"${esc(endpointId)}",""" +
          s""""signature":"$status/${esc(how)}","status":$status,""" +
          s""""discriminator":"${esc(how)}","guarding_check_ids":[],""" +
          s""""guard_sense":"","link":"constructed",""" +
          s""""anchor":${anchor(m.filename, rc.lineNumber)}}"""
      }
    }

    // ---- Spring's own contract: a returned VALUE is a 200 ---------------
    //
    // **The nine-of-twelve case.** A `@RestController` method that returns a
    // domain object rather than a `ResponseEntity` has no construction to
    // observe: Spring serialises the return value and answers 200 (or
    // whatever `@ResponseStatus` says). Nothing in the body builds a
    // response, so the passes above find nothing, and synthesis then reads
    // the bare `@ApiResponse` as a declaration it must not model — correctly,
    // because its rule is written for a MISSING helper, not for a handler
    // that never had one.
    //
    // So this is recovered from the framework's contract instead, and marked
    // as such: `link: "spring-serialisation"` and a `serialised`
    // discriminator, never `constructed`. It is an inference — a sound one,
    // and the reviewer can see that it is one. §5.8 asks for the limit to be
    // visible, not for the behaviour to be dropped.
    //
    // Only when nothing else was recovered for this endpoint: a handler that
    // does build a ResponseEntity has already said what it returns.
    val alreadyRecovered = outcomeBuf.exists(o =>
      o.contains(s""""endpoint_id":"${esc(endpointId)}"""") &&
      !o.contains(""""discriminator":"declared""""))

    if (!alreadyRecovered) {
      val returnType = m.methodReturn.typeFullName
      val returnsValue =
        returnType != "void" && returnType != "<empty>" && returnType.nonEmpty
      // `@ResponseStatus(HttpStatus.CREATED)` on the handler is a BEHAVIOURAL
      // declaration, not documentation: Spring uses it. It was read only
      // inside the @ExceptionHandler path, so a 201-returning endpoint had
      // its status invisible.
      val annotated = m.annotation.name("ResponseStatus").l
        .flatMap(_.parameterAssign.code.l).flatMap { code =>
          "\\b(\\d{3})\\b".r.findFirstMatchIn(code).map(_.group(1).toInt)
            .orElse(httpStatusNames.collectFirst {
              case (n, c) if code.contains(n) => c })
        }.headOption

      // `returnsValue` OR an explicit `@ResponseStatus`. A void handler
      // annotated `@ResponseStatus(CREATED)` answers 201 with no body — that
      // is an observable outcome, and requiring a return value dropped
      // `POST /api/records/transactions`, the one endpoint in this service that
      // declares a status other than 200.
      if (returnsValue || annotated.isDefined) {
        val status = annotated.getOrElse(200)
        val how = if (annotated.isDefined) "response-status" else "spring-serialisation"
        outcomeBuf += s"""{"id":"${esc(endpointId)}::$status","endpoint_id":"${esc(endpointId)}",""" +
          s""""signature":"$status/serialised","status":$status,""" +
          s""""discriminator":"serialised","guarding_check_ids":[],""" +
          s""""guard_sense":"","link":"${esc(how)}",""" +
          s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
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
