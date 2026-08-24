// A plain-DOM screen, no framework. `js-ui` keys on `addEventListener`, which a
// React application has none of — the two packs exist because the two shapes are
// genuinely different, and this file is what makes the DOM one reproducible.
//
// **This is also where a selector comes from.** `getElementById("archive")` and
// `querySelector(".record-row")` are literal strings sitting in the code, which
// is structurally recoverable in a way a JSX prop is not. A selector is
// extracted here; it is never authored ahead of time and never guessed.
//
// Every id below exists in `records.html`, so the two can be checked against
// each other rather than drifting.

const filterOwner = document.getElementById("filter-owner");
const applyFilter = document.getElementById("apply-filter");
const archiveButton = document.getElementById("archive");
const newRecord = document.getElementById("new-record");
const rows = document.querySelector("#record-rows");

// **The unrecoverable case, and it must stay unrecoverable.** This button has no
// id and no data-testid; it is reached by walking the DOM, so no literal in this
// file names it. It must be reported rather than matched on its text.
const exportButton = rows.querySelector("tr").children[2].firstElementChild;

// A named handler passed by reference: the registration says nothing about the
// body, so resolving it needs the name looked up as a method.
function syncFilterState() {
  applyFilter.disabled = filterOwner.value.length === 0;
}

filterOwner.addEventListener("input", syncFilterState);

// An inline closure: the body IS at the registration site.
applyFilter.addEventListener("click", async () => {
  const response = await fetch("/record?owner=" + filterOwner.value);
  rows.dataset.state = response.ok ? "ready" : "error";
});

archiveButton.addEventListener("click", async () => {
  await fetch("/record/1/archive", { method: "POST" });
  rows.dataset.state = "ready";
});

newRecord.addEventListener("click", function () {
  window.location.assign("/records/new");
});

exportButton.addEventListener("click", function () {
  rows.dataset.state = "exporting";
});
