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

@main def main(cpgPath: String, commit: String, repo: String, out: String,
               annotations: String = "", constructors: String = "",
               dropNoise: String = "yes") = {
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

  // ---- Layer 1: methods and calls -------------------------------------
  // isExternal(false) is REQ-CGA-010: a stub for a third-party callee would be
  // a fabricated node, so it is excluded at the source.
  val allMethods = cpg.method.isExternal(false).filterNot(_.name.startsWith("<")).l

  // ---- Noise: the accessors and the generated boilerplate (X-5a) -------
  //
  // A 12-endpoint service put **389 methods** into the graph and 189 of them
  // were `getUserId`, `setUserId`, `isEnablePhoneAuthenticationMethods`,
  // `equals`, `hashCode`, `toString`. Nothing in Métis reasons about any of
  // them: not entry points, no guard, they raise nothing, and no criterion can
  // reference one. They were 49% of the method nodes.
  //
  // **The axis is not visibility.** Measured on that service, `private` is only
  // 59 of 389 -- and two of those ARE reachable from a handler, one of them
  // guarding an endpoint and raising the exception an @ExceptionHandler maps.
  // Filtering on `private` deletes a rejection path and leaves all 166 getters
  // in place. Nor is it call-reachability: only 46 methods are reachable from a
  // handler, but that is largely javasrc2cpg not resolving interface dispatch,
  // so dropping the unreachable would delete a service implementation's 31
  // business methods.
  //
  // What makes an accessor safe to drop is that it is **provably** inert:
  //
  //   1. named `getX`/`setX`/`isX` where a field `x` exists, AND
  //   2. short, AND
  //   3. no control structure and no call but operators -- no branch, no throw,
  //      no delegation.
  //
  // Condition 3 separates `getTitle()` from `getDisplayLabel()`, which is named
  // like an accessor, has no field behind it, and branches. Verified on the same
  // service: **zero** dropped methods contained a control structure, and the
  // only annotation any of them carried was `@Override`.
  //
  // Fields are untouched. `@Schema`, `@NotBlank` and `@Size` sit on the field
  // rather than its getter, and they are test-design inputs -- which is also why
  // "drop private" would be exactly backwards for members.
  val fieldNames = cpg.member.name.l.toSet
  val boilerplateNames = Set("equals", "hashCode", "toString", "builder",
                             "canEqual", "clone", "compareTo", "iterator")

  def propertyOf(name: String): Option[String] = {
    def decap(s: String) = if (s.isEmpty) s else s.head.toLower + s.tail
    if (name.startsWith("get") && name.length > 3) Some(decap(name.substring(3)))
    else if (name.startsWith("set") && name.length > 3) Some(decap(name.substring(3)))
    else if (name.startsWith("is") && name.length > 2) Some(decap(name.substring(2)))
    else None
  }

  def isInertAccessor(m: Method): Boolean =
    propertyOf(m.name).exists(fieldNames.contains) &&
      m.numberOfLines <= 4 &&
      m.ast.isControlStructure.isEmpty &&
      m.call.l.forall(_.name.startsWith("<operator>"))

  def isNoise(m: Method): Boolean =
    dropNoise != "no" && (isInertAccessor(m) || boilerplateNames.contains(m.name))

  val droppedMethods = allMethods.filter(isNoise)
  val internal = allMethods.filterNot(isNoise)
  val droppedAccessors = droppedMethods.count(isInertAccessor)
  val droppedBoilerplate = droppedMethods.size - droppedAccessors

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
  val builtinVerbs = Map(
    "GetMapping" -> "GET", "PostMapping" -> "POST", "PutMapping" -> "PUT",
    "DeleteMapping" -> "DELETE", "PatchMapping" -> "PATCH", "RequestMapping" -> "ANY")

  // Profile-declarable, the way `outbound_client`, `security` and `schema`
  // already are. Its absence was an asymmetry: a project could declare its own
  // Feign marker but not its own mapping stereotype, so the one lookup with no
  // escape hatch was the one that silently recovered nothing.
  val verbs =
    if (named("mapping").nonEmpty) builtinVerbs ++ named("mapping") else builtinVerbs

  // ---- Annotation composition (Spring's own rule) ----------------------
  //
  // `@GetMapping` IS `@RequestMapping(method = GET)`, and a project's own
  // stereotype wraps one of those in turn. Spring resolves this recursively
  // (`AnnotationUtils.findAnnotation`); so does CodeQL, whose
  // `SpringControllerAnnotation` is defined in terms of itself:
  //
  //   this.hasQualifiedName("org.springframework.stereotype", "Controller")
  //   or this.getAnAnnotation().getType() instanceof SpringControllerAnnotation
  //
  // Matching the literal name instead failed in BOTH directions, and the second
  // is the dangerous one: a house stereotype wrapping `@GetMapping` recovered no
  // route at all, and one wrapping `@FeignClient` escaped the outbound-client
  // exclusion and INVENTED a route the service does not serve.
  //
  // **Bounded to what the CPG contains.** Only annotation types declared in the
  // analysed sources can be followed; a stereotype from a jar Métis never parsed
  // is not resolvable here, and is left alone rather than guessed at. Declaring
  // it in the project profile is the supported answer for that case.
  //
  // Ported from github/codeql (MIT, (c) GitHub, Inc.) -- the rule is theirs.
  // Identified by `@Retention`/`@Target`, NOT by the source text. javasrc2cpg
  // renders an annotation declaration's `code` as `public class GetJson` -- the
  // word `@interface` never appears -- so a text filter matched nothing and the
  // whole closure silently resolved to a single hop. Measured, not assumed.
  //
  // The idiom is also the right discriminator on its own terms: an annotation
  // Spring reads at runtime must carry `@Retention(RUNTIME)`, and an ordinary
  // class almost never carries either marker. That keeps a class from lending
  // its annotations to an unrelated annotation of the same simple name.
  val annotationDecls: Map[String, List[Annotation]] =
    cpg.typeDecl
      .filter(_.annotation.name.l.exists(n => n == "Retention" || n == "Target"))
      .map(td => td.name -> td.annotation.l)
      .toMap

  /** Every annotation reachable from `a` by composition, `a` itself first.
    *
    * `seen` is a cycle guard: annotations may legally reference one another
    * (`@Retention` carries `@Documented`, which carries `@Retention`), and an
    * unguarded walk does not terminate.
    */
  def composedWith(a: Annotation, seen: Set[String] = Set.empty): List[Annotation] =
    if (seen.contains(a.name)) Nil
    else a :: annotationDecls.getOrElse(a.name, Nil)
      .flatMap(meta => composedWith(meta, seen + a.name))

  // ---- Controller identity and inherited mappings ----------------------
  //
  // CodeQL makes the class stereotype a PRECONDITION of a request-mapping
  // method (`SpringControllerMethod` requires `getDeclaringType() instanceof
  // SpringController`) and then resolves the mapping through `overrides*`. Both
  // halves are needed together: requiring the stereotype alone deletes a route
  // whose mapping lives on an interface, and walking overrides alone still
  // counts a Spring MVC handler as a REST surface.

  /** Supertypes of `m`'s declaring type, transitively. Bounded: a cycle cannot
    * occur in legal Java, but a malformed CPG should not hang extraction. */
  def supertypesOf(td: TypeDecl, depth: Int = 0): List[TypeDecl] =
    if (depth > 8) Nil
    else td.inheritsFromTypeFullName.toList
      .filterNot(_ == "java.lang.Object")
      .flatMap(fn => cpg.typeDecl.fullNameExact(fn).l)
      .flatMap(sup => sup :: supertypesOf(sup, depth + 1))

  /** The methods `m` overrides -- matched on name AND signature, so an overload
    * does not lend its mapping to a sibling. */
  def overridden(m: Method): List[Method] =
    m.typeDecl.headOption.toList
      .flatMap(supertypesOf(_))
      .flatMap(_.method.nameExact(m.name).l)
      .filter(_.signature == m.signature)

  /** Mapping annotations on `m` or on anything it overrides (CodeQL:
    * `this.overrides*(superMethod)`). The shape springdoc generates and that
    * teams share between a client and the service serving it. */
  def mappingAnnotations(m: Method): List[Annotation] =
    (m :: overridden(m)).flatMap(_.annotation.l)

  /** Annotations on the declaring class and its supertypes, composition
    * resolved. */
  def ownerAnnotations(m: Method): List[Annotation] =
    m.typeDecl.headOption.toList
      .flatMap(td => td :: supertypesOf(td))
      .flatMap(_.annotation.l)
      .flatMap(a => composedWith(a))

  /** A Spring controller of any kind. `@RestController` is checked by name as
    * well as by composition: Spring's own annotations are not in the CPG, so
    * `@RestController` cannot be followed to the `@Controller` it carries. */
  def isController(m: Method): Boolean =
    ownerAnnotations(m).exists(a => a.name == "Controller" || a.name == "RestController")

  /** Whether the handler's return value is a RESPONSE BODY.
    *
    * `@RestController` implies `@ResponseBody`; plain `@Controller` does not --
    * there the String is a view name handed to a template resolver, and
    * modelling it as a body claims the caller receives text nobody ever sends.
    * That is the `@FeignClient` fault by another route: behaviour attributed to
    * a service that does not have it. */
  def returnsResponseBody(m: Method): Boolean =
    ownerAnnotations(m).exists(_.name == "RestController") ||
      (m :: overridden(m)).flatMap(_.annotation.l).exists(_.name == "ResponseBody") ||
      ownerAnnotations(m).exists(_.name == "ResponseBody")

  /** The HTTP verb this annotation declares, directly or by composition.
    *
    * `@RequestMapping` carries its verb in `method =`, so resolving a stereotype
    * to the NAME `RequestMapping` and stopping would report every composed
    * mapping as `ANY` -- turning a precise `GET` into "some verb", which reads
    * like recovered information and is not.
    */
  def verbOf(a: Annotation): Option[String] =
    composedWith(a).flatMap { c =>
      verbs.get(c.name).map {
        case "ANY" =>
          // Read straight off `parameterAssign` rather than through `argPairs`:
          // that helper is defined further down and a Scala script forbids the
          // forward reference across the vals in between.
          c.parameterAssign.code.l
            .flatMap("^\\s*method\\s*=\\s*(.+)$".r.findFirstMatchIn(_))
            .map(_.group(1).split("\\.").last.replaceAll("[^A-Za-z]", "").toUpperCase)
            .find(_.nonEmpty).getOrElse("ANY")
        case verb => verb
      }
    }.headOption

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
  // **The RAW initialiser is stored, and resolution happens on lookup.**
  //
  // This used to store `rhs.stripPrefix("\"").stripSuffix("\"")` behind a
  // `rhs.startsWith("\"")` guard meaning "this is a string literal". But
  // `"/api" + RESOURCE` also starts with a quote: it passed the guard, lost
  // its opening quote to stripPrefix, kept its closing one, and was stored as
  // the VALUE `/api" + RESOURCE`. Every route under that constant then came
  // out as a path containing a stray quote and a Java identifier -- a fabricated
  // route, emitted as fact, which is exactly what T-9d and this pack's own
  // known_limits forbid. Six of demo_project/records-service's twelve endpoints landed that way.
  //
  // Keeping the initialiser raw also fixes the other half: a constant defined in
  // terms of another (`ITEM = ITEMS + "/{id}"`) now
  // resolves, where before it was `__unresolved__` however simple the chain.
  case class Const(owner: String, name: String, value: String)
  val declared: List[Const] = cpg.assignment.l.flatMap { a =>
    val lhs = a.target.code
    val rhs = a.source.code.trim
    // Anything mentioning a string literal is a candidate route fragment. A
    // numeric or object initialiser is not, and is left out rather than stored
    // and later refused.
    if (rhs.contains("\"")) {
      val owner = a.method.typeDecl.name.headOption.getOrElse("")
      Some(Const(owner, lhs.split("\\.").last.replaceAll("[^A-Za-z0-9_]", ""), rhs))
    } else None
  }
  val byOwner: Map[(String, String), String] =
    declared.map(c => (c.owner, c.name) -> c.value).toMap
  // A simple name is only usable globally when it is UNAMBIGUOUS -- but
  // "unambiguous" is a fact about what the constants MEAN, not about how they
  // are spelled, and this used to compare the raw initialisers.
  //
  // demo_project/records-service declares the same names twice, once in the controller module
  // and once in the Feign-client module:
  //
  //   RouteConstants.RECORD_ROOT  = "/api" + RESOURCE + "/protected"
  //   InternalClients.PROTECTED_ROOT = RESOURCE_ROOT + "/protected"
  //
  // Two spellings of `/api/records/protected`. Compared as text they look like the
  // TMS_STATUS collision this guard exists for, so all three protected routes
  // came out `__unresolved__` -- a refusal that was right by its own rule and
  // wrong about the code.
  //
  // Resolution happens at lookup instead, in `constantsNamed`: every candidate
  // is resolved and the name is usable only if they agree on the ANSWER. Two
  // constants that genuinely differ still refuse, which is the case that
  // matters.
  val constantsNamed: Map[String, List[String]] =
    declared.groupBy(_.name).map { case (n, cs) => n -> cs.map(_.value).distinct }

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

  // A whole string literal, as opposed to an expression that merely begins with
  // one. Distinguishing the two is the entire bug described above.
  def isLiteral(t: String): Boolean =
    t.length >= 2 && t.startsWith("\"") && t.endsWith("\"")

  def resolveSingle(rawExpr: String, owner: String = "", depth: Int = 0): String = {
    val expr = rawExpr.trim
    // A constant chain longer than this is a cycle or a generated file; either
    // way `__unresolved__` is the honest answer and a stack overflow is not.
    if (depth > 8) UNRESOLVED
    else if (isLiteral(expr) && splitOutside(expr, '+').length == 1)
      expr.substring(1, expr.length - 1)
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
          // Resolved recursively: what the table holds is the initialiser, and
          // an initialiser can itself be a concatenation of other constants.
          def viaOwner: Option[String] =
            byOwner.get((qualifier, simple)).orElse(byOwner.get((owner, simple)))
              .map(raw => resolveSingle(raw, qualifier, depth + 1))
          def viaName: Option[String] = {
            val answers = constantsNamed.getOrElse(simple, Nil)
              .map(raw => resolveSingle(raw, "", depth + 1)).distinct
            // One answer, or none. Two different answers is the ambiguity the
            // old text comparison was reaching for, and it still refuses.
            if (answers.size == 1 && answers.head != UNRESOLVED) Some(answers.head)
            else None
          }
          viaOwner.orElse(viaName).getOrElse(UNRESOLVED)
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
    "ModelAttribute" -> "form",
    // `contract.IN_COOKIE` has existed since cookie parameters were found to be
    // "disclosed as unmappable and dropped"; the map that feeds it never named
    // the annotation. "send this in a cookie" and "send this in a header" build
    // different requests, which is the whole reason the location is separate.
    //
    // `@MatrixVariable` is the other name CodeQL binds and is deliberately NOT
    // added: it has no location in `PARAMETER_LOCATIONS`, and choosing one is an
    // ontology decision (D-2), not a pack fix.
    "CookieValue"   -> "cookie"
  )

  // Constraints worth carrying: they are the test-data conditions a fixture has
  // to satisfy. Quoted verbatim rather than parsed -- a half-understood
  // constraint asserted as structure is worse than one reported honestly.
  // The full JSR-380 set the typed vocabulary can honour, plus the two that are
  // constraints with no numeric content. Narrower than this, `typedConstraints`
  // handled cases the filter never admitted -- `@DecimalMin`, `@Digits` and
  // `@Past` were coded for and unreachable.
  val constraintAnnotations = Set(
    "NotNull", "NotBlank", "NotEmpty", "Size", "Min", "Max", "DecimalMin",
    "DecimalMax", "Pattern", "Email", "Positive", "PositiveOrZero", "Negative",
    "NegativeOrZero", "Digits", "Past", "PastOrPresent", "Future",
    "FutureOrPresent", "AssertTrue", "AssertFalse")

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
  val declaredSecurity = named("security")
  val securityAnnotations = if (declaredSecurity.nonEmpty) declaredSecurity else Map(
    "PreAuthorize" -> "expression", "PostAuthorize" -> "expression",
    "Secured" -> "role", "RolesAllowed" -> "role", "DenyAll" -> "role",
    "PermitAll" -> "role"
  )

  // ---- Security declared in the filter chain --------------------------
  //
  // Until now this pack read security from annotations only, and said so: an
  // endpoint with no fact meant "nothing was declared on it", never "it is
  // open". That stays true -- but a filter chain IS a declaration, and refusing
  // to read it left the commonest way of securing a Spring service invisible.
  //
  // CodeQL models the same builder (`SpringSecurity.qll`: `authorizeRequests` /
  // `authorizeHttpRequests`, `requestMatcher(s)`, `securityMatcher(s)`,
  // `permitAll`, `anyRequest`). Ported from github/codeql (MIT, (c) GitHub, Inc.).
  //
  // **`permitAll` is the one shape that licenses the word "open"**, and it gets
  // its own scheme for exactly that reason: "declared public" and "nothing
  // declared" are different facts, and collapsing them is the claim this pack
  // has always refused to make.
  val securityRules = Map(
    "permitAll" -> "public", "denyAll" -> "denied",
    "authenticated" -> "authenticated", "fullyAuthenticated" -> "authenticated",
    "hasRole" -> "role", "hasAnyRole" -> "role",
    "hasAuthority" -> "authority", "hasAnyAuthority" -> "authority")

  val QUOTED = "\"([^\"]*)\"".r

  def quotedStrings(s: String): List[String] =
    QUOTED.findAllMatchIn(s).map(_.group(1)).filter(_.nonEmpty).toList

  // Each call in a fluent chain carries the chain UP TO ITSELF as its `code`, so
  // the longest one in a method is the complete expression. Taken verbatim
  // rather than reassembled: the source text is the fact.
  val securityChains: List[String] =
    cpg.method.l.flatMap { m =>
      val codes = m.call.l.filter(c => securityRules.contains(c.name)).map(_.code)
        .filter(c => c.contains("requestMatchers") || c.contains("anyRequest") ||
                     c.contains("securityMatcher"))
      if (codes.isEmpty) None else Some(codes.maxBy(_.length))
    }.distinct

  val CHAIN_RULE =
    ("(requestMatchers|securityMatchers|securityMatcher|anyRequest)\\(([^)]*)\\)" +
     "\\.(permitAll|denyAll|authenticated|fullyAuthenticated|hasRole|hasAnyRole|" +
     "hasAuthority|hasAnyAuthority)\\(([^)]*)\\)").r

  /** `(patterns, rule, arguments)` in the order they are written. Order IS the
    * semantics: Spring applies the first matcher that matches, so a rule list
    * read out of order authorises the wrong thing. */
  def chainRules(chain: String): List[(List[String], String, List[String])] =
    CHAIN_RULE.findAllMatchIn(chain).map { mt =>
      val patterns =
        if (mt.group(1) == "anyRequest") List("/**") else quotedStrings(mt.group(2))
      (patterns, mt.group(3), quotedStrings(mt.group(4)))
    }.toList

  /** Ant-style path patterns as Spring means them: a slash followed by a double
    * star spans segments; a single star stops at one. Everything else is
    * literal. (Spelled out rather than shown, because Scala nests block
    * comments and the literal pattern opens one that never closes.) */
  def antMatches(pattern: String, path: String): Boolean = {
    // Via a sentinel, because the naive ordering corrupts itself: replacing the
    // multi-segment wildcard first inserts `.*`, and the single-star pass then
    // rewrites THAT star into `[^/]*`. Measured, not theorised -- it matched
    // `/record/{id}` and not `/record/{id}/archive`, and the catch-all matched
    // nothing at all.
    val SENTINEL = "\u0000"
    val rx = pattern.replace(".", "\\.")
      .replace("/**", SENTINEL)
      .replace("*", "[^/]*")
      .replace(SENTINEL, "(/.*)?")
    ("^" + rx + "$").r.findFirstIn(path).isDefined
  }

  /** The first chain rule whose matcher covers `path`. */
  def chainSecurityFor(path: String): Option[(String, String, List[String])] =
    securityChains.flatMap(chainRules).collectFirst {
      case (patterns, rule, args) if patterns.exists(antMatches(_, path)) =>
        (securityRules.getOrElse(rule, rule), rule, args)
    }

  def securityJson(m: Method, path: String = ""): String = {
    val own = m.annotation.l ++ m.typeDecl.headOption.toList.flatMap(_.annotation.l)
    val annotated = own.filter(a => securityAnnotations.contains(a.name)).map { a =>
      val roles = argPairs(a).map(_._2).flatMap(v => arrayMembers(v).getOrElse(List(v)))
        .map(_.replaceAll("^\"|\"$", "").trim).filter(_.nonEmpty).distinct
      s"""{"scheme":"${esc(securityAnnotations(a.name))}",""" +
      s""""expression":"${esc(a.code)}","source":"annotation",""" +
      s""""roles":[${roles.map(r => "\"" + esc(r) + "\"").mkString(",")}]}"""
    }.distinct
    // The filter chain, appended rather than merged: an endpoint may be
    // annotated AND matched by the chain, and those are two separate
    // declarations by two different mechanisms. Reporting one is losing the
    // other.
    val chained = chainSecurityFor(path).toList.map { case (scheme, rule, args) =>
      s"""{"scheme":"${esc(scheme)}",""" +
      s""""expression":"${esc(rule)}(${esc(args.mkString(", "))})","source":"filter-chain",""" +
      s""""roles":[${args.map(r => "\"" + esc(r) + "\"").mkString(",")}]}"""
    }
    "[" + (annotated ++ chained).mkString(",") + "]"
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
    // Supertypes too: a controller may carry no type-level mapping of its own
    // and inherit `@RequestMapping` from the API interface it implements, which
    // is where springdoc-shaped contracts put it.
    m.typeDecl.headOption.toList
      .flatMap(td => td :: supertypesOf(td))
      .flatMap(_.annotation.name("RequestMapping").l)
      .headOption
      .map(a => routeArg(a).map(r => resolvePath(r, owner)).getOrElse(""))
      .getOrElse("")
  }

  // **A `@FeignClient` interface is not an API surface.** Its `@GetMapping`s
  // declare calls this service MAKES of another one. Counting them as endpoints
  // put three of demo_project/records-service's fifteen "endpoints" on `UserClient` -- routes
  // this service serves nowhere, which would then be modelled as behaviour it
  // does not have and generated as test cases nobody can run.
  def isOutboundClient(m: Method): Boolean = {
    val markers = named("outbound_client").keys.toSet match {
      case s if s.nonEmpty => s
      case _ => Set("FeignClient")
    }
    // Through composition, for the same reason `verbOf` is: a house stereotype
    // wrapping `@FeignClient` used to escape this check, and the endpoint list
    // then carried routes this service calls rather than serves.
    m.typeDecl.headOption.toList.flatMap(_.annotation.l)
      .exists(a => composedWith(a).exists(c => markers.contains(c.name)))
  }

  // `isController` is a precondition, not a nicety: without it a Spring MVC
  // handler (`@Controller`, no `@ResponseBody`) is recovered as a REST endpoint
  // whose body is a view name. `returnsResponseBody` separates the two.
  val endpoints = internal
    .filterNot(isOutboundClient)
    .filter(isController)
    .filter(returnsResponseBody)
    .flatMap { m =>
    mappingAnnotations(m).flatMap { a =>
      verbOf(a).map { verb =>
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
        s""""security":${securityJson(m, path)},""" +
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
  // ---- the `schema` role: what springdoc says about a type ---------------
  //
  // **71 `@Schema` annotations in one service, and not one of them read.** They
  // carry the description a person wrote for a field, whether it is required,
  // and its allowed values — the last of which is a test-design input, because
  // an enum's values ARE its equivalence partitions. All of it was sitting in
  // the source while `Class.description` was null on every node.
  //
  // Read through the annotation table's `schema` role, so a project that wraps
  // springdoc in its own annotation declares that once rather than being
  // invisible.
  val schemaMarkers = named("schema").keys.toSet match {
    case s if s.nonEmpty => s
    case _ => Set("Schema", "ArraySchema", "Parameter")
  }

  def schemaArg(annotations: List[Annotation], key: String): String =
    annotations.filter(a => schemaMarkers.contains(a.name))
      .flatMap(a => argValue(a, key)).headOption
      .map(_.replaceAll("^\"|\"$", "")).getOrElse("")

  def requiredFlag(annotations: List[Annotation]): String = {
    val raw = annotations.filter(a => schemaMarkers.contains(a.name))
      .flatMap(a => argValue(a, "requiredMode").orElse(argValue(a, "required")))
      .headOption.getOrElse("")
    // `REQUIRED`/`NOT_REQUIRED` (springdoc 2) or `true`/`false` (springdoc 1).
    // Anything else is left empty rather than read as false: "not stated" and
    // "stated optional" are different facts about a payload.
    if (raw.contains("REQUIRED") && !raw.contains("NOT_REQUIRED")) "true"
    else if (raw.contains("NOT_REQUIRED") || raw.contains("false")) "false"
    else if (raw.contains("true")) "true"
    else ""
  }

  // **One `required`, from either source.** @Schema states it; a bean-validation
  // annotation implies it. A field carrying only `@NotNull` used to report
  // `required: ""` -- "not stated" -- when the code plainly states it, and a
  // generated case would then treat the field as optional and never build the
  // fixture that reaches the 400.
  val impliesRequired = Set("NotNull", "NotBlank", "NotEmpty")

  def requiredValue(annotations: List[Annotation]): String = {
    val declared = requiredFlag(annotations)
    if (declared.nonEmpty) declared
    else if (annotations.exists(a => impliesRequired.contains(a.name))) "true"
    else ""
  }

  def allowedValues(annotations: List[Annotation]): List[String] =
    annotations.filter(a => schemaMarkers.contains(a.name))
      .flatMap(a => argValue(a, "allowableValues"))
      .flatMap(v => arrayMembers(v).getOrElse(List(v)))
      .map(_.replaceAll("^\"|\"$", "").trim).filter(_.nonEmpty).distinct

  // ---- X-6b: validation as data, not as annotation text ----------------
  //
  // `constraints: ["@Size(max = 40)"]` is a string, and every consumer that
  // wants the bound has to re-parse it -- two consumers parsing it slightly
  // differently is a defect nobody can see. A boundary criterion needs the
  // number 40, so the number is what gets emitted.
  //
  // The vocabulary is **closed**, like the ontology and the annotation roles: an
  // annotation outside it stays in `constraints` and becomes no property, so it
  // reads as unhandled rather than vanishing (X-5a).
  //
  // `@Size` is length on a String and cardinality on a collection, and calling
  // both `max_length` would be a quiet lie about what a fixture has to build --
  // so the target type decides which pair of properties it lands in.
  def numArg(a: Annotation, keys: List[String]): Option[String] =
    keys.flatMap(k => argValue(a, k)).headOption
      .map(_.replaceAll("^\"|\"$", "").trim).filter(_.nonEmpty)

  def isCollection(typeFullName: String): Boolean = {
    val n = typeFullName
    n.startsWith("java.util.") &&
      List("List", "Set", "Collection", "Map", "Queue", "Deque")
        .exists(c => n.contains("." + c)) || n.endsWith("[]")
  }

  /** `(property -> value)` pairs for one constraint annotation, or nothing. */
  def typedConstraints(a: Annotation, typeFullName: String): List[(String, String)] = {
    val collection = isCollection(typeFullName)
    val sizeMin = if (collection) "expected_min_size" else "expected_min_length"
    val sizeMax = if (collection) "expected_max_size" else "expected_max_length"
    a.name match {
      // `required` is deliberately NOT emitted here: `requiredFlag` already
      // emits it from @Schema, and two `"required"` keys in one JSON object is
      // a collision whose winner is whichever the parser reads last. It is
      // folded into that single value below instead.
      case "NotNull" => Nil
      // Blank/Empty are stronger than NotNull: they also rule out "".
      case "NotBlank" | "NotEmpty" => List(sizeMin -> "1")
      case "Size" =>
        numArg(a, List("min")).map(sizeMin -> _).toList ++
          numArg(a, List("max")).map(sizeMax -> _).toList
      case "Min" | "DecimalMin" =>
        numArg(a, List("value")).map("expected_min" -> _).toList
      case "Max" | "DecimalMax" =>
        numArg(a, List("value")).map("expected_max" -> _).toList
      case "Positive" => List("expected_exclusive_min" -> "0")
      case "PositiveOrZero" => List("expected_min" -> "0")
      case "Negative" => List("expected_exclusive_max" -> "0")
      case "NegativeOrZero" => List("expected_max" -> "0")
      case "Pattern" =>
        numArg(a, List("regexp")).map("expected_pattern" -> _).toList
      case "Email" => List("expected_format" -> "email")
      case "Digits" =>
        numArg(a, List("integer")).map("expected_integer_digits" -> _).toList ++
          numArg(a, List("fraction")).map("expected_fraction_digits" -> _).toList
      case "Past" | "PastOrPresent" => List("expected_temporal" -> "past")
      case "Future" | "FutureOrPresent" => List("expected_temporal" -> "future")
      case _ => Nil   // recognised as a constraint, not honoured as a property
    }
  }

  // ---- The Enum specialisation, and why a field cares ------------------
  //
  // An enum is the one type whose value space is fully known from source: its
  // constants ARE the equivalence partitions of every field of that type. Before
  // this, `allowed_values` came only from `@Schema(allowableValues=...)`, so a
  // field typed by an enum had **no** partitions unless somebody had written them
  // out a second time by hand -- measured across a real service, zero fields
  // carried any.
  val enumConstants: Map[String, List[String]] = cpg.typeDecl.isExternal(false).l
    .filter(t => t.code.contains("enum ") || t.inheritsFromTypeFullName.exists(
      _ == "java.lang.Enum"))
    .map { t =>
      // A Java enum's constants are fields of the enum's own type -- **and so is
      // an instance field that happens to be self-typed.** A real enum declared
      // `private final MfaChallengeType legacyMfaChallengeType`, which the type
      // test alone reported as a fourth constant, so a field of that type
      // carried a partition the value space does not contain and a generated
      // case would have offered it as input.
      //
      // javasrc2cpg gives an enum constant NO modifiers and an instance field
      // `FINAL, PRIVATE`, so visibility separates them. Anything private or
      // protected is not part of the closed set of values a caller can send.
      val hidden = Set("PRIVATE", "PROTECTED")
      val constants = t.member.l
        .filter(m => m.typeFullName == t.fullName ||
                     m.typeFullName.endsWith("." + t.name))
        .filterNot(m => m.modifier.modifierType.l.exists(hidden.contains))
        .name.l.distinct
      t.fullName -> constants
    }.filter(_._2.nonEmpty).toMap

  val enumNames = enumConstants.keySet

  // **A Java record puts its component annotations on the constructor
  // parameter, not on the member.** Probed against `RecordDto`, whose four
  // components each carry `@Schema` and two of which carry `@NotBlank`/`@Size`:
  // every member reported `List()` and every constructor parameter reported the
  // real set. So a record DTO -- increasingly the default shape for Spring
  // payloads -- landed with **no** descriptions, no constraints and no
  // required-ness whatever, and nothing said so.
  //
  // Read as a fallback rather than a special case: prefer what is on the member,
  // fall back to the same-named constructor parameter. That covers a record and
  // a POJO without either needing to be detected.
  val ctorParamAnnotations: Map[(String, String), List[Annotation]] =
    cpg.typeDecl.isExternal(false).l.flatMap { t =>
      t.method.nameExact("<init>").l.flatMap(_.parameter.l)
        .filterNot(_.name == "this")
        .map(pp => (t.fullName, pp.name) -> pp.astChildren.collectAll[Annotation].l)
    }.filter(_._2.nonEmpty).toMap

  val members = cpg.typeDecl.isExternal(false).flatMap { t =>
    t.member.map { mem =>
      val onMember = mem.astChildren.collectAll[Annotation].l
      val own =
        if (onMember.nonEmpty) onMember
        else ctorParamAnnotations.getOrElse((t.fullName, mem.name), Nil)
      val constraints = own
        .filter(a => constraintAnnotations.contains(a.name))
        .map(_.code).distinct
      // Declared partitions first, the field's enum type second. A hand-written
      // @Schema(allowableValues) is a person's statement and outranks an
      // inference, even a sound one.
      // **`typeFullName` erases the generic**: a `List<RecordDto>` field reports
      // `java.util.List`, so the nested payload edge stopped at the collection
      // and the element type -- the thing a fixture actually builds -- was
      // unreachable. The member's `code` still carries `List<RecordDto>`, so the
      // element type is read from there and reported separately rather than
      // overwriting the declared type, which is genuinely `java.util.List`.
      val elementType = {
        val code = mem.code
        val open = code.indexOf('<')
        val close = code.lastIndexOf('>')
        if (open >= 0 && close > open) {
          val inner = code.substring(open + 1, close).split(",").last.trim
          // A simple name here; landing resolves it the same way it resolves a
          // response body, and omits it when the name is ambiguous.
          if (inner.nonEmpty && !inner.contains("<") && inner.head.isUpper) inner else ""
        } else ""
      }
      val declaredAllowed = allowedValues(own)
      val allowed =
        if (declaredAllowed.nonEmpty) declaredAllowed
        else enumConstants.getOrElse(mem.typeFullName, Nil)
      // **Overlapping bounds compose to the STRONGEST, because every constraint
      // has to hold.** `@NotBlank @Size(min = 3)` means length >= 3; taking the
      // first seen reported `expected_min_length: 1` from @NotBlank, which is
      // weaker than the code, so a boundary case would offer a 1-character value
      // as valid against a field that rejects it. Affirmatively wrong beats
      // missing, and this was affirmatively wrong.
      val minKeys = Set("expected_min_length", "expected_min_size", "expected_min",
                        "expected_integer_digits", "expected_fraction_digits")
      val typed = own.filter(a => constraintAnnotations.contains(a.name))
        .flatMap(a => typedConstraints(a, mem.typeFullName))
        .foldLeft(List.empty[(String, String)]) { case (acc, kv) =>
          acc.find(_._1 == kv._1) match {
            case None => acc :+ kv
            case Some((k, existing)) =>
              val pick = (scala.util.Try(existing.toDouble).toOption,
                          scala.util.Try(kv._2.toDouble).toOption) match {
                // A min bound: the larger is the stronger. A max bound: the
                // smaller. Non-numeric (a pattern, a format) keeps the first.
                case (Some(a), Some(b)) if minKeys.contains(k) => math.max(a, b)
                case (Some(a), Some(b)) => math.min(a, b)
                case _ => Double.NaN
              }
              if (pick.isNaN) acc
              else acc.map { case (kk, vv) =>
                if (kk == k) (kk, if (pick == pick.toLong.toDouble)
                  pick.toLong.toString else pick.toString) else (kk, vv) }
          }
        }
      val typedJson = typed.map { case (k, v) =>
        val literal = if (v.matches("-?\\d+(\\.\\d+)?") || v == "true" || v == "false")
          v else "\"" + esc(v) + "\""
        s""""$k":$literal"""
      }
      s"""{"type_name":"${esc(t.name)}","name":"${esc(mem.name)}",""" +
      s""""owner_full_name":"${esc(t.fullName)}",""" +
      s""""type_full_name":"${esc(mem.typeFullName)}",""" +
      s""""element_type":"${esc(elementType)}",""" +
      s""""type_is_enum":${enumNames.contains(mem.typeFullName)},""" +
      s""""owner_is_enum":${enumNames.contains(t.fullName)},""" +
      s""""constraints":[${constraints.map(c => "\"" + esc(c) + "\"").mkString(",")}],""" +
      (if (typedJson.nonEmpty) typedJson.mkString("", ",", ",") else "") +
      s""""description":"${esc(schemaArg(own, "description"))}",""" +
      s""""required":"${esc(requiredValue(own))}",""" +
      s""""allowed_values":[${allowed.map(v => "\"" + esc(v) + "\"").mkString(",")}],""" +
      s""""owner_description":"${esc(schemaArg(t.astChildren.collectAll[Annotation].l, "description"))}",""" +
      s""""anchor":${anchor(t.filename, mem.lineNumber)}}"""
    }
  }.l

  // ---- Layer 2c: which exception becomes which status ------------------
  // `@ExceptionHandler(X.class)` + `@ResponseStatus(HttpStatus.BAD_REQUEST)`.
  //
  // Without this the pack can see that an endpoint declares a 400 and cannot see
  // *why*. The pilot estate maps FOUR exceptions onto 400 and only one of them is bean
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
    "PAYMENT_REQUIRED" -> 402, "FORBIDDEN" -> 403, "NOT_FOUND" -> 404,
    "METHOD_NOT_ALLOWED" -> 405, "NOT_ACCEPTABLE" -> 406, "REQUEST_TIMEOUT" -> 408,
    "CONFLICT" -> 409, "GONE" -> 410, "PRECONDITION_FAILED" -> 412,
    "PAYLOAD_TOO_LARGE" -> 413, "UNSUPPORTED_MEDIA_TYPE" -> 415,
    "UNPROCESSABLE_ENTITY" -> 422, "LOCKED" -> 423, "FAILED_DEPENDENCY" -> 424,
    "PRECONDITION_REQUIRED" -> 428, "TOO_MANY_REQUESTS" -> 429,
    "INTERNAL_SERVER_ERROR" -> 500, "NOT_IMPLEMENTED" -> 501,
    "BAD_GATEWAY" -> 502, "SERVICE_UNAVAILABLE" -> 503, "GATEWAY_TIMEOUT" -> 504
  )

  def statusOf(a: Annotation): Option[Int] = {
    val raw = argValue(a, "value").orElse(argValue(a, "code"))
      .orElse(argPairs(a).find(_._1 == "").map(_._2)).getOrElse("")
    val simple = raw.split("\\.").last.replaceAll("[^A-Za-z0-9_]", "").trim
    httpStatusCodes.get(simple).orElse(scala.util.Try(simple.toInt).toOption)
  }

  // **A handler that BUILDS its response is as declarative as one that annotates
  // it.** This required `@ResponseStatus` and found nothing in demo_project/records-service,
  // which reported `exception_mappings=0` and therefore not a single rejection
  // path — twelve transitions, all 2xx, for a service that plainly returns 400s:
  //
  //     @ExceptionHandler(RecordConflictException.class)
  //     ... return ResponseEntity.badRequest().body(...)
  //
  // The status is in the construction. `response_constructors` already declares
  // what each one means (`ResponseEntity.badRequest -> 400`), so the same table
  // the behaviour pack uses answers it here. Annotation first: an explicit
  // `@ResponseStatus` is the stronger statement where both are present.
  val constructorStatus: Map[String, Int] =
    (if (constructors.trim.isEmpty)
       "ResponseEntity.ok:200,ResponseEntity.created:201,ResponseEntity.accepted:202," +
       "ResponseEntity.noContent:204,ResponseEntity.badRequest:400," +
       "ResponseEntity.notFound:404"
     else constructors)
      .split(",").toList.map(_.trim).filter(_.nonEmpty).flatMap { pair =>
        pair.split(":").toList match {
          case expr :: code :: Nil =>
            scala.util.Try(code.trim.toInt).toOption.map(c => (expr.trim, c))
          case _ => None
        }
      }.toMap

  // **`ResponseEntity.status(...)` is the only form that can carry a body with a
  // 4xx.** `notFound()` returns a HeadersBuilder, so any handler that wants to
  // return an `ErrorDto` with its 404 *must* write `status(HttpStatus.NOT_FOUND)`
  // -- which made the dominant real-world rejection idiom unreadable. The
  // constructor table matches on a bare method name and has no way to express
  // "whatever this call's argument resolves to", so the argument is read here.
  //
  // Measured on the demo corpus: four `@ExceptionHandler` methods, every one of
  // this shape, and `exception_mappings` came back **0**. The same symptom the
  // constructor table was added to fix, one idiom further along.
  def statusArgumentOf(c: Call): Option[Int] = {
    val args = c.argument.l.filterNot(_.argumentIndex == 0)
    args.flatMap { a =>
      val simple = a.code.split("\\.").last.replaceAll("[^A-Za-z0-9_]", "").trim
      httpStatusCodes.get(simple).orElse(scala.util.Try(simple.toInt).toOption)
    }.headOption
  }

  def constructedStatusIn(m: Method): Option[Int] = {
    val calls = m.ast.isCall.l
    // The named constructors first: `badRequest()` states its status outright,
    // where `status(x)` needs x resolved and may not resolve at all.
    val named = calls.flatMap { c =>
      constructorStatus.collectFirst {
        // Matched on methodFullName: javasrc2cpg strips the receiver from
        // `code`, so `ResponseEntity.badRequest()` reads as `badRequest()`.
        case (expr, status) if c.methodFullName.contains("." + expr + ":") => status
      }
    }.headOption
    named.orElse(
      calls.filter(c => c.methodFullName.contains(".status:") ||
                        c.methodFullName.contains(".valueOf:"))
        .flatMap(statusArgumentOf).headOption)
  }

  val exceptionMappings = cpg.method.isExternal(false).l.flatMap { m =>
    val handled = m.annotation.name("ExceptionHandler").l
    val status = m.annotation.name("ResponseStatus").l.flatMap(statusOf).headOption
      .orElse(if (handled.nonEmpty) constructedStatusIn(m) else None)
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
          // The handler itself, not just the class it lives in. `advice_type` is
          // a simple name and joins to nothing, so `ExceptionMapping-[:HANDLED_BY]
          // ->Method` -- catalogued, and named in EVIDENCE_LAYER as this label's
          // reader -- could not be written. Five mappings landed connected to
          // nothing on a real service while the catalogue said otherwise.
          s""""handler_method_id":"${esc(m.fullName)}",""" +
          // The handler's own return type is the rejection's body. Without it a
          // scoped 400 carried `response_body: ""`, which landing documents as
          // meaning NO body — so a generated case asserted an empty payload
          // against a populated `ErrorDto`. An empty string is a
          // claim here, not a gap.
          s""""response_body":"${esc(responseBody(declaredReturnType(m)))}",""" +
          s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
        }
      }
    }
  }.distinct

  // ---- Layer 2d: what the application asks the database (X-8a) ---------
  //
  // Measured on a real twelve-endpoint service before this was written:
  // `@Query`, `EntityManager`, `JdbcTemplate` and native SQL appeared in **zero**
  // files, and 11 used Spring Data **derived methods**. So the derived name is
  // the shape that matters and the rest are the tail.
  //
  // The entity comes from the method's RETURN TYPE, not from the repository's
  // generic parameter: `inheritsFromTypeFullName` is erased to
  // `org.springframework.data.jpa.repository.JpaRepository`, so
  // `List<RecordEntity>` is where the entity actually survives.
  //
  // The entity->table mapping is emitted where the source states it and OMITTED
  // where it does not. On that same service `@Entity`/`@Table`/`@Column` were in
  // zero files — the entities lived in a dependency jar — so a table name here is
  // frequently unknowable from code, and the database catalogue is what confirms
  // it (X-8). Guessing one here would put a plausible wrong table in the graph.
  val repositoryMarkers = Set("JpaRepository", "CrudRepository",
                              "PagingAndSortingRepository", "Repository",
                              "ReactiveCrudRepository", "MongoRepository")

  // **The generic is erased in `typeFullName` and survives in `code`.** A
  // repository method returns `java.util.List` as far as the type says, and
  // `abstract List<RecordEntity> findByOwner(...)` as far as the source does —
  // and the entity is the whole point of the row. The same erasure caught a
  // payload field earlier: `List<RecordDto>` reported `java.util.List`, true and
  // useless.
  def entityFrom(m: Method): String = {
    val code = m.code
    val open = code.indexOf('<')
    val close = code.indexOf('>')
    val inner =
      if (open >= 0 && close > open) code.substring(open + 1, close)
      else {
        // No generic: the return type IS the entity, e.g. `RecordEntity findOne(..)`.
        val head = code.replaceAll("^(public|abstract|final|static|protected)\\s+", "")
        head.split("\\s+").headOption.getOrElse("")
      }
    inner.split(",").last.trim.split("\\.").last.trim
      .replaceAll("[^A-Za-z0-9_$]", "")
  }

  val entities = cpg.typeDecl.isExternal(false).l.filter(t =>
    t.annotation.name("Entity").nonEmpty).map { t =>
      val table = t.annotation.name("Table").l.flatMap(a => argValue(a, "name"))
        .headOption.map(_.replaceAll("^\"|\"$", "")).getOrElse("")
      val columns = t.member.l.map { m =>
        val declared = m.astChildren.collectAll[Annotation].l
          .filter(_.name == "Column").flatMap(a => argValue(a, "name"))
          .headOption.map(_.replaceAll("^\"|\"$", "")).getOrElse("")
        s"""{"field":"${esc(m.name)}","column":"${esc(declared)}"}"""
      }
      // `table` empty means the source does not say. That is a fact, and the
      // catalogue is what settles it — never a naming-strategy guess written
      // here as though it were recovered.
      s"""{"entity":"${esc(t.name)}","full_name":"${esc(t.fullName)}",""" +
      s""""table":"${esc(table)}","columns":[${columns.mkString(",")}],""" +
      s""""anchor":${anchor(t.filename, t.lineNumber)}}"""
    }

  val repositoryQueries = cpg.typeDecl.isExternal(false).l.filter(t =>
    t.inheritsFromTypeFullName.exists(p =>
      repositoryMarkers.contains(p.split("\\.").last))).flatMap { t =>
      t.method.l.filterNot(_.name.startsWith("<")).map { m =>
        val q = m.annotation.name("Query").l
        val statement = q.flatMap(a => argValue(a, "value")
          .orElse(argPairs(a).find(_._1 == "").map(_._2)))
          .headOption.map(_.replaceAll("^\"|\"$", "")).getOrElse("")
        val native = q.flatMap(a => argValue(a, "nativeQuery")).headOption
          .exists(_.contains("true"))
        s"""{"repository":"${esc(t.name)}","method":"${esc(m.name)}",""" +
        s""""entity":"${esc(entityFrom(m))}",""" +
        s""""statement":"${esc(statement)}","native":$native,""" +
        s""""method_id":"${esc(m.fullName)}",""" +
        s""""anchor":${anchor(m.filename, m.lineNumber)}}"""
      }
    }

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
  "entities": [${entities.mkString(",")}],
  "repository_queries": [${repositoryQueries.mkString(",")}],
  "checks": [],
  "outcomes": [],
  "filtered": {"methods_declared": ${allMethods.size},
    "accessors_dropped": $droppedAccessors,
    "boilerplate_dropped": $droppedBoilerplate,
    "reason": "inert accessors and generated boilerplate: no entry point, no guard, no throw, nothing a criterion can reference. Fields are untouched. Pass --param dropNoise=no to keep them"},
  "parse_errors": [${unparsed.map(f => "\"" + esc(f) + "\"").mkString(",")}],
  "partial": ${unparsed.nonEmpty}
}"""

  new PrintWriter(out) { write(json); close() }
  println(s"wrote $out")
  println(s"  methods=${methods.size} calls=${calls.size} endpoints=${endpoints.size} members=${members.size}")
  println(s"  exception_mappings=${exceptionMappings.size}")
  println(s"  entities=${entities.size} repository_queries=${repositoryQueries.size}")
  println(s"  noise dropped=${droppedMethods.size} of ${allMethods.size} " +
          s"(${droppedAccessors} inert accessors, ${droppedBoilerplate} boilerplate) " +
          s"— fields untouched")
  println(s"  unparsed=${unparsed.size}")
}
