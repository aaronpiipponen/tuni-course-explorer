/**
 * The Feedback tab: the definition-driven search and select filters over the read-only inbox.
 *
 * The panel reads the whole listing automatically and narrows that report in the browser on an
 * explicit Apply, so committing a filter issues no further read. It offers the row-level protected
 * image reads, one grouped archive download per submission and named local deletion.
 */
import { useEffect, useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import { deleteFeedback, readFeedbackList } from "../../api/feedback";
import type {
  FeedbackDefinition,
  FeedbackSelectDefinition,
  StoredFeedback,
} from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { FailureNotice, Panel } from "../../shared/Panel";
import { Picker } from "../../shared/Picker";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { FeedbackEntry } from "./FeedbackEntry";

/** One committed listing input: the search text and the selected option values by field. */
interface AppliedInput {
  query: string | null;
  filters: Record<string, string>;
}

/** Return every configured select field in definition order. */
function selectFields(
  definition: FeedbackDefinition | null,
): FeedbackSelectDefinition[] {
  return (definition?.fields ?? []).filter(
    (field): field is FeedbackSelectDefinition => field.kind === "select",
  );
}

/** Return the submissions the committed search and filters select, in their committed order. */
function visibleSubmissions(
  submissions: StoredFeedback[],
  definition: FeedbackDefinition | null,
  applied: AppliedInput,
): StoredFeedback[] {
  if (definition === null) return submissions;
  const filters = Object.entries(applied.filters);
  const matching = submissions.filter((submission) =>
    filters.every(
      ([fieldId, option]) => submission.answers[fieldId] === option,
    ),
  );
  if (applied.query === null || applied.query.trim() === "") return matching;
  const needle = applied.query.toLowerCase();
  const textFields = definition.fields.filter(
    (field) => field.kind === "text" || field.kind === "textarea",
  );
  return matching
    .flatMap((submission) => {
      const rank = textFields.findIndex((field) => {
        const value = submission.answers[field.id];
        return (
          typeof value === "string" && value.toLowerCase().includes(needle)
        );
      });
      return rank === -1 ? [] : [{ submission, rank }];
    })
    .sort(
      (left, right) =>
        left.rank - right.rank ||
        right.submission.created_at.localeCompare(left.submission.created_at) ||
        right.submission.id.localeCompare(left.submission.id),
    )
    .map(({ submission }) => submission);
}

/** Render the feedback inbox and its committed listing input. */
export function Feedback({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const detail = wording.feedback;
  const [query, setQuery] = useState("");
  const [draftFilters, setDraftFilters] = useState<Record<string, string>>({});
  const [applied, setApplied] = useState<AppliedInput>({
    query: null,
    filters: {},
  });
  const [deleting, setDeleting] = useState(false);
  const [deleteFailure, setDeleteFailure] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(true);
  // The listing read is always the whole inbox. Apply and Clear filters narrow it in the browser.
  const panel = usePanelRead(
    (signal, automatic) =>
      readFeedbackList(
        { query: null, filters: {} },
        session.csrfToken,
        signal,
        automatic,
      ),
    {
      pollSeconds: session.pollSeconds,
      enabled: true,
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );
  const definition = panel.report?.definition ?? null;
  const fields = selectFields(definition);
  const selectedCount = fields.filter(
    (field) => (draftFilters[field.id] ?? "") !== "",
  ).length;

  useEffect(() => {
    if (definition === null) return;
    setDraftFilters((previous) => {
      let changed = false;
      const next = { ...previous };
      for (const field of selectFields(definition)) {
        if (!(field.id in next)) {
          next[field.id] = "";
          changed = true;
        }
      }
      return changed ? next : previous;
    });
  }, [definition]);

  const apply = (): void => {
    const filters: Record<string, string> = {};
    for (const field of fields) {
      const value = draftFilters[field.id] ?? "";
      if (value !== "") filters[field.id] = value;
    }
    setApplied({ query: query === "" ? null : query, filters });
  };

  const clearFilters = (): void => {
    setDraftFilters((previous) => {
      const next = { ...previous };
      for (const field of fields) next[field.id] = "";
      return next;
    });
    setApplied((previous) => ({ ...previous, filters: {} }));
  };

  const onDelete = async (submission: StoredFeedback): Promise<void> => {
    setDeleting(true);
    setDeleteFailure(null);
    try {
      await deleteFeedback(submission.id, session.csrfToken);
      panel.reload();
    } catch (error) {
      setDeleteFailure(failureText(error, wording.writeFailed));
      handleAdmissionFailure(error, onRefusal);
    } finally {
      setDeleting(false);
    }
  };

  const submissions = visibleSubmissions(
    panel.report?.submissions ?? [],
    definition,
    applied,
  );
  return (
    <Panel
      title={detail.heading}
      followBody
      marker={
        <AutoMarker
          lastSuccess={panel.lastSuccess}
          label={detail.heading}
          reading={panel.loading}
        />
      }
      span={12}
    >
      <div className="feedback-toolbar">
        <input
          className="feedback-search"
          type="search"
          aria-label={detail.search}
          placeholder={detail.search}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {fields.length > 0 && (
          <button
            className="btn"
            type="button"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((current) => !current)}
          >
            {detail.filtersCount.replace("{count}", String(selectedCount))}
          </button>
        )}
        <button className="btn" type="button" onClick={apply}>
          {detail.apply}
        </button>
      </div>
      {fields.length > 0 && (
        <div
          className={`feedback-filters${filtersOpen ? " open" : ""}`}
          inert={!filtersOpen}
        >
          <div className="feedback-filters-clip">
            <div className="feedback-filters-body">
              {fields.map((field) => (
                <div className="feedback-filter" key={field.id}>
                  <span className="feedback-filter-label">
                    {field.label.en}
                  </span>
                  <Picker
                    label={field.label.en}
                    value={draftFilters[field.id] ?? ""}
                    options={[
                      { value: "", label: detail.all },
                      ...field.options.map((option) => ({
                        value: option.value,
                        label: option.label.en,
                      })),
                    ]}
                    onChange={(value) =>
                      setDraftFilters((previous) => ({
                        ...previous,
                        [field.id]: value,
                      }))
                    }
                  />
                </div>
              ))}
              <div
                className={`feedback-clear${selectedCount === 0 ? " is-empty" : ""}`}
              >
                <button
                  className="btn xs"
                  type="button"
                  disabled={selectedCount === 0}
                  onClick={clearFilters}
                >
                  {detail.clearFilters}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      <FailureNotice text={panel.failure} />
      <FailureNotice text={deleteFailure} />
      {panel.report !== null && submissions.length === 0 && (
        <p className="note">{detail.empty}</p>
      )}
      <div className="feedback-list">
        {definition !== null &&
          submissions.map((submission) => (
            <FeedbackEntry
              key={submission.id}
              definition={definition}
              submission={submission}
              session={session}
              onRefusal={onRefusal}
              pending={deleting}
              onDelete={onDelete}
            />
          ))}
      </div>
    </Panel>
  );
}
