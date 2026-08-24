import { createBrowserRouter } from "react-router-dom";

import RecordListPage from "./RecordListPage.jsx";
import RecordDetailPage from "./RecordDetailPage.jsx";
import SummaryPage from "./SummaryPage.jsx";

/**
 * jssrc2cpg lowers this config into assignments of the form
 * `_tmp_0.path = "/records"`, so the `path` KEY is structurally present even
 * though surrounding JSX is not. That is what makes these four recoverable.
 *
 * `<Route path="...">` in JSX stays unrecoverable and is not guessed at.
 */
export const router = createBrowserRouter([
  { path: "/", element: <RecordListPage /> },
  { path: "/records", element: <RecordListPage /> },
  { path: "/records/:id", element: <RecordDetailPage /> },
  { path: "/summary/:id", element: <SummaryPage /> },
]);
