import { useState } from "react";

import { apiRoots, requestJson } from "./apiRoots.js";

/**
 * **The negative case, and it must stay negative.** `slug` uses a regex literal,
 * which reaches the extractor looking exactly like a path: it starts with `/`.
 * A recogniser that only checks for a leading slash reports it as a route, and a
 * confident wrong answer is worse than no answer.
 */
export default function SummaryPage({ id }) {
  const [summaryStatus, setSummaryStatus] = useState("loading");

  function slug(text) {
    return text.replace(/\s+/g, "-").replace(/[^a-z0-9-]/gi, "");
  }

  async function load() {
    const summary = await requestJson(apiRoots.summary, "/detail");
    setSummaryStatus(summary ? "ready" : "error");
    return slug(String(summary));
  }

  return <button onClick={load}>Summary ({summaryStatus})</button>;
}
