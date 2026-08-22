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

  // Split on `sep`, but only outside string literals. Shared by the
  // concatenation resolver and the array-initialiser reader below.
  def splitOutside(expr: String, sep: Char): List[String] = {
    val out = scala.collection.mutable.ListBuffer[String]()
    var buf = new StringBuilder
    var inString = false
    expr.foreach { ch =>
      if (ch == '"') { inString = !inString; buf.append(ch) }
      else if (ch == sep && !inString) { out += buf.toString; buf = new StringBuilder }
      else buf.append(ch)
    }
    out += buf.toString
    out.toList
  }

  // An annotation's arguments, as (name, value). `@RequestMapping(value = {"",
  // "/metric"}, produces = X)` has two named ones; `@GetMapping("/all")` has a
  // single positional one, whose name is "".
  def argPairs(a: Annotation): List[(String, String)] =
    a.parameterAssign.code.l.map { c =>
      "^([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*)$".r.findFirstMatchIn(c)
        .map(x => (x.group(1), x.group(2).trim))
        .getOrElse(("", c.trim))
    }

  // The argument carrying the ROUTE -- Spring's `value` or `path`, or a bare
  // positional argument.
  //
  // This pack used to take `.parameterAssign.code.l.headOption`, i.e. whichever
  // argument came first. On `@RequestMapping(produces = APPLICATION_JSON_VALUE)`
  // that is `produces`, which resolves to nothing, and the endpoint silently
  // lost its class prefix.
  def routeArg(a: Annotation): Option[String] = {
    val pairs = argPairs(a)
    pairs.find(p => p._1 == "value" || p._1 == "path").map(_._2)
      .orElse(pairs.find(_._1 == "").map(_._2))
  }

  // `{"", "/metric"}` -- Spring mounts the controller on BOTH paths. The
  // non-empty member is the route a caller actually uses; the empty one exists
  // because the gateway strips the prefix before forwarding.
  //
  // Previously this initialiser did not parse, produced `__unresolved__`, and
  // `classPrefix` then swallowed that into "" -- so every endpoint of every
  // dual-mounted controller lost its prefix, and `POST /metric` was modelled as
  // the trigger `"POST "`. Silence where T-9d requires a mark.
  def arrayMembers(expr: String): Option[List[String]] = {
    val t = expr.trim
    if (t.startsWith("{") && t.endsWith("}"))
      Some(splitOutside(t.substring(1, t.length - 1), ',').map(_.trim).filter(_.nonEmpty))
    else None
  }

  def resolvePath(raw: String, owner: String = ""): String = {
    val expr = raw.replaceFirst("^[A-Za-z_]+\\s*=\\s*", "").trim
    arrayMembers(expr) match {
      case Some(members) =>
        val resolved = members.map(m => resolveSingle(m, owner))
        if (resolved.contains(UNRESOLVED)) UNRESOLVED
        else resolved.find(_.nonEmpty).getOrElse("")
      case None => resolveSingle(expr, owner)
    }
  }

  def resolveSingle(rawExpr: String, owner: String = ""): String = {
    val expr = rawExpr.trim
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
      val operands = splitOutside(expr, '+')
      val resolvedParts = operands.map(_.trim).filter(_.nonEmpty).map(resolveOperand)
      if (resolvedParts.isEmpty || resolvedParts.contains(UNRESOLVED)) UNRESOLVED
      else resolvedParts.mkString("")
    }
  }

  // ---- Layer 2b: what a caller must send -------------------------------
  // Without these an endpoint is a door with no indication of what to bring:
  // a generated case can assert a status and can never issue the request.
  //
  // Everything here is a FACT from the signature. There is deliberately no
  // example or sample value -- M-9 makes Métis state the requirement on the
  // data, never solve it.

  // Where a parameter rides, from its Spring annotation. Names match
  // `contract.PARAMETER_LOCATIONS`.
  val paramLocations = Map(
    "PathVariable"  -> "path",
    "RequestParam"  -> "query",
    "RequestHeader" -> "header",
    "RequestBody"   -> "body",
    "RequestPart"   -> "form",
    "ModelAttribute" -> "form"
  )

  // Constraints worth carrying: they are the test-data conditions a fixture has
  // to satisfy. Quoted verbatim rather than parsed -- a half-understood
  // constraint asserted as structure is worse than one reported honestly.
  val constraintAnnotations =
    Set("NotNull", "NotBlank", "NotEmpty", "Size", "Min", "Max", "Pattern", "Email", "Positive")

  // `@Valid`/`@Validated` are not constraints -- they are the switch that makes
  // the constraints on a DTO run at all. `pack.yaml` has declared them as the
  // validation matcher since day one and this query never read them, so the one
  // fact that separates "this 400 is bean validation" from "this 400 is some
  // other exception mapped to 400" was invisible.
  val validationTriggers = Set("Valid", "Validated")

  def argValue(a: Annotation, name: String): Option[String] =
    argPairs(a).find(_._1 == name).map(_._2.trim)

  def paramJson(p: MethodParameterIn): Option[String] = {
    // `@io.swagger...parameters.RequestBody` documents; Spring's binds. Only the
    // binding one describes what the caller must send, and matching on the
    // simple name alone would conflate them.
    val binding = p.annotation.l.filter(a => paramLocations.contains(a.name))
      .filterNot(_.fullName.startsWith("io.swagger"))
    binding.headOption.map { a =>
      val location = paramLocations(a.name)
      // Spring: a parameter is required unless it says otherwise, and a
      // defaultValue makes it optional in practice.
      val declaredRequired = argValue(a, "required").map(_ == "true")
      val hasDefault = argValue(a, "defaultValue").isDefined
      val required = declaredRequired.getOrElse(!hasDefault)
      val constraints = p.annotation.l
        .filter(x => constraintAnnotations.contains(x.name))
        .map(_.code).distinct
      val declaredName = argValue(a, "value").orElse(argValue(a, "name"))
        .map(_.replaceAll("^\"|\"$", "")).filter(_.nonEmpty).getOrElse(p.name)
      s"""{"name":"${esc(declaredName)}","location":"$location",""" +
      s""""type_name":"${esc(p.typeFullName)}","required":$required,""" +
      s""""constraints":[${constraints.map(c => "\"" + esc(c) + "\"").mkString(",")}]}"""
    }
  }

  def parametersJson(m: Method): String =
    "[" + m.parameter.l.sortBy(_.index).flatMap(paramJson).mkString(",") + "]"

  // Bean validation is on if any bound parameter carries `@Valid`/`@Validated`,
  // or the controller class does. Both are real Spring configurations and either
  // one runs the DTO's constraints in the argument resolver -- strictly before
  // the handler body, which is why the validation dimension gets order 0.
  // ---- what the caller gets back ---------------------------------------
  //
  // The CPG's type information is **erased** here: `methodReturn.typeFullName`
  // is a bare `org.springframework.http.ResponseEntity` for all 91 handlers, and
  // `signature` agrees, so neither can say whether a 200 carries an
  // `EnvironmentDto`, a `PageDto<ProjectDto>` or nothing at all.
  //
  // `m.code` keeps the declaration verbatim, generics intact, so the type is
  // read from there. Method-level annotations are not part of `code` and every
  // parameter annotation lives inside the parameter list, so splitting at the
  // first `(` isolates the declaration cleanly.
  val modifiers =
    Set("public", "protected", "private", "static", "final", "abstract",
        "synchronized", "native", "strictfp", "default")

  def declaredReturnType(m: Method): String = {
    val decl = m.code.split("\\(")(0).replace("\n", " ").trim
    val cut = decl.lastIndexOf(' ')
    if (cut < 0) return ""
    // Everything before the method name, minus modifiers. Split on whitespace is
    // safe only AFTER the name is removed -- `Map<String, Object>` contains one.
    val head = decl.substring(0, cut).trim
    head.split("\\s+").filterNot(modifiers.contains).mkString(" ").trim
  }

  // Spring convention, and named as one: `ResponseEntity<X>` is a carrier, and
  // `X` is what the caller actually receives. `Void` means the response has no
  // body -- a fact worth stating, not an absence of information.
  val CARRIERS = Set("ResponseEntity", "HttpEntity", "Mono", "Flux", "Callable")

  def responseBody(returnType: String): String = {
    val t = returnType.trim
    val open = t.indexOf('<')
    if (open < 0) return if (t == "void" || t.isEmpty) "" else t
    val outer = t.substring(0, open).split("\\.").last
    if (!CARRIERS.contains(outer)) return t
    val inner = t.substring(open + 1, t.lastIndexOf('>')).trim
    if (inner == "Void" || inner == "java.lang.Void") "" else inner
  }

  def isValidated(m: Method): Boolean = {
    val onParam = m.parameter.l.exists(p =>
      p.annotation.l.exists(a => validationTriggers.contains(a.name)))
    val onClass = m.typeDecl.headOption.toList
      .flatMap(_.annotation.l).exists(a => validationTriggers.contains(a.name))
    onParam || onClass
  }

  // Declarative security only. An endpoint with no entry here means **nothing
  // was declared on it** -- never that it is open. Security enforced in a filter
  // chain or at a gateway is invisible to this pack, and the two claims are not
  // the same.
  val securityAnnotations = Map(
    "PreAuthorize" -> "expression", "PostAuthorize" -> "expression",
    "Secured" -> "role", "RolesAllowed" -> "role", "DenyAll" -> "role",
    "PermitAll" -> "role"
  )

  def securityJson(m: Method): String = {
    val own = m.annotation.l ++ m.typeDecl.headOption.toList.flatMap(_.annotation.l)
    val facts = own.filter(a => securityAnnotations.contains(a.name)).map { a =>
      val roles = argPairs(a).map(_._2).flatMap(v => arrayMembers(v).getOrElse(List(v)))
        .map(_.replaceAll("^\"|\"$", "").trim).filter(_.nonEmpty).distinct
      s"""{"scheme":"${esc(securityAnnotations(a.name))}",""" +
      s""""expression":"${esc(a.code)}",""" +
      s""""roles":[${roles.map(r => "\"" + esc(r) + "\"").mkString(",")}]}"""
    }.distinct
    "[" + facts.mkString(",") + "]"
  }

  def classAnnotation(m: Method): Option[Annotation] =
    m.typeDecl.headOption.toList.flatMap(_.annotation.name("RequestMapping").l).headOption

  // `consumes`/`produces`, method-level first, falling back to the class.
  def mediaTypes(a: Annotation, key: String, fallback: Option[Annotation] = None): String = {
    val raw = argValue(a, key).orElse(fallback.flatMap(f => argValue(f, key)))
    val values = raw.toList.flatMap(v => arrayMembers(v).getOrElse(List(v)))
      .map(v => resolveSingle(v, "")).filter(v => v.nonEmpty && v != UNRESOLVED).distinct
    "[" + values.map(v => "\"" + esc(v) + "\"").mkString(",") + "]"
  }

  // The class-level prefix, or `__unresolved__` if there is one and it could not
  // be read. **A controller with no `@RequestMapping` at all returns "", which is
  // a fact; a `@RequestMapping` this resolver cannot parse returns the marker.**
  // Collapsing those two into "" is what hid the dual-mount defect.
  def classPrefix(m: Method): String = {
    val owner = m.typeDecl.name.headOption.getOrElse("")
    m.typeDecl.headOption.toList
      .flatMap(_.annotation.name("RequestMapping").l)
      .headOption
      .map(a => routeArg(a).map(r => resolvePath(r, owner)).getOrElse(""))
      .getOrElse("")
  }

  val endpoints = internal.flatMap { m =>
    m.annotation.l.flatMap { a =>
      verbs.get(a.name).map { verb =>
        val rawParam = routeArg(a)
        val owner = m.typeDecl.name.headOption.getOrElse("")
        val resolved = rawParam.map(r => resolvePath(r, owner)).getOrElse("")
        val prefix = classPrefix(m)
        val path =
          if (resolved == UNRESOLVED || prefix == UNRESOLVED) UNRESOLVED
          else prefix + resolved
        s"""{"id":"${esc(m.fullName)}::${esc(a.name)}","http_method":"$verb",""" +
        s""""path":"${esc(path)}","path_source":"${esc(rawParam.getOrElse(""))}",""" +
        s""""handler_method_id":"${esc(m.fullName)}",""" +
        s""""parameters":${parametersJson(m)},""" +
        s""""security":${securityJson(m)},""" +
        s""""consumes":${mediaTypes(a, "consumes")},""" +
        s""""produces":${mediaTypes(a, "produces", classAnnotation(m))},""" +
        s""""validated":${isValidated(m)},""" +
        s""""handler_type":"${esc(owner)}",""" +
        s""""handler_name":"${esc(m.name)}",""" +
        s""""response_type":"${esc(declaredReturnType(m))}",""" +
        s""""response_body":"${esc(responseBody(declaredReturnType(m)))}",""" +
        s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
      }
    }
  }

  // ---- Layer 3: the verified type registry ----------------------------
  // This is what makes REQ-TST-008 mechanical: a field absent here fails
  // generation instead of producing a warning nobody reads.
  // `mem.annotation` was never walked, so every `@NotNull`/`@Size` on every DTO
  // field was invisible -- and those declarations are the whole data requirement
  // behind a validation rejection. Quoted verbatim, same discipline as the
  // parameter constraints: a half-parsed `@Size(min=2, max=64)` asserted as
  // structure is worse than the source text reported honestly.
  // `mem.annotation` does not exist on a `Member` in Joern 4.0.604 -- unlike
  // `Method` and `MethodParameterIn`, which both have the accessor. The
  // annotations ARE there, as AST children; only the convenience step is
  // missing, so they are collected directly.
  val members = cpg.typeDecl.isExternal(false).flatMap { t =>
    t.member.map { mem =>
      val constraints = mem.astChildren.collectAll[Annotation].l
        .filter(a => constraintAnnotations.contains(a.name))
        .map(_.code).distinct
      s"""{"type_name":"${esc(t.name)}","name":"${esc(mem.name)}",""" +
      s""""owner_full_name":"${esc(t.fullName)}",""" +
      s""""type_full_name":"${esc(mem.typeFullName)}",""" +
      s""""constraints":[${constraints.map(c => "\"" + esc(c) + "\"").mkString(",")}],""" +
      s""""anchor":${anchor(t.filename, mem.lineNumber)}}"""
    }
  }.l

  // ---- Layer 2c: which exception becomes which status ------------------
  // `@ExceptionHandler(X.class)` + `@ResponseStatus(HttpStatus.BAD_REQUEST)`.
  //
  // Without this the pack can see that an endpoint declares a 400 and cannot see
  // *why*. athena maps FOUR exceptions onto 400 and only one of them is bean
  // validation, so labelling every declared 400 "payload invalid" would be
  // affirmatively wrong on the other three -- a fixture built from it sets up the
  // wrong precondition and never reaches the path.
  //
  // The declaring class is carried because two `@ControllerAdvice` beans may
  // handle the same exception. Resolving that precedence is not this pack's job;
  // reporting both so it can be resolved honestly is (see
  // `contract.exception_status_map`).
  val httpStatusCodes = Map(
    "OK" -> 200, "CREATED" -> 201, "ACCEPTED" -> 202, "NO_CONTENT" -> 204,
    "ALREADY_REPORTED" -> 208, "BAD_REQUEST" -> 400, "UNAUTHORIZED" -> 401,
    "FORBIDDEN" -> 403, "NOT_FOUND" -> 404, "CONFLICT" -> 409,
    "UNPROCESSABLE_ENTITY" -> 422, "INTERNAL_SERVER_ERROR" -> 500
  )

  def statusOf(a: Annotation): Option[Int] = {
    val raw = argValue(a, "value").orElse(argValue(a, "code"))
      .orElse(argPairs(a).find(_._1 == "").map(_._2)).getOrElse("")
    val simple = raw.split("\\.").last.replaceAll("[^A-Za-z0-9_]", "").trim
    httpStatusCodes.get(simple).orElse(scala.util.Try(simple.toInt).toOption)
  }

  val exceptionMappings = cpg.method.isExternal(false).l.flatMap { m =>
    val handled = m.annotation.name("ExceptionHandler").l
    val status = m.annotation.name("ResponseStatus").l.flatMap(statusOf).headOption
    val advice = m.typeDecl.name.headOption.getOrElse("")
    handled.flatMap { a =>
      val types = argPairs(a).map(_._2)
        .flatMap(v => arrayMembers(v).getOrElse(List(v)))
        .map(_.trim.stripSuffix(".class").split("\\.").last.trim)
        .filter(_.nonEmpty).distinct
      status.toList.flatMap { s =>
        types.map { t =>
          s"""{"exception_type":"${esc(t)}","status":$s,""" +
          s""""advice_type":"${esc(advice)}",""" +
          s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
        }
      }
    }
  }.distinct

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
  "exception_mappings": [${exceptionMappings.mkString(",")}],
  "checks": [],
  "outcomes": [],
  "parse_errors": [${unparsed.map(f => "\"" + esc(f) + "\"").mkString(",")}],
  "partial": ${unparsed.nonEmpty}
}"""

  new PrintWriter(out) { write(json); close() }
  println(s"wrote $out")
  println(s"  methods=${methods.size} calls=${calls.size} endpoints=${endpoints.size} members=${members.size}")
  println(s"  exception_mappings=${exceptionMappings.size}")
  println(s"  unparsed=${unparsed.size}")
}
