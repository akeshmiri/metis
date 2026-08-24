import { useState } from "react";

import { apiRoots, requestJson } from "./apiRoots.js";

/** A route path built at runtime: the call site is reported, never invented. */
export default function RecordDetailPage({ id }) {
  const [status, setStatus] = useState("loading");

  async function load() {
    const record = await requestJson(apiRoots.record, `/${id}`);
    setStatus(record ? "ready" : "error");
  }

  return <button onClick={load}>Load ({status})</button>;
}
