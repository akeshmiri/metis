import { useState } from "react";

import { apiRoots, requestJson } from "./apiRoots.js";

/**
 * `setStatus` with literal arguments is the UI's own state vocabulary — real
 * state names read out of code, not invented ones. No React application
 * available before this demo had a recoverable status-setter convention, which
 * is the only reason `react` could not be declared a supported framework.
 */
export default function RecordListPage() {
  const [status, setStatus] = useState("loading");
  const [records, setRecords] = useState([]);

  async function load() {
    setStatus("loading");
    try {
      const found = await requestJson(apiRoots.record, "/");
      setRecords(found);
      setStatus("ready");
    } catch (e) {
      setStatus("error");
    }
  }

  return <button onClick={load}>Reload ({status})</button>;
}
