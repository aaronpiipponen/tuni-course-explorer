/** Derive the publication choice from every selected option that declares a default. */
import type { FeedbackDefinition } from "../../api/feedback";

/**
 * Return whether a publication issue is requested by the current answers.
 *
 * A selected option contributes its boolean `publicIssueByDefault`, an absent property
 * contributes nothing, and an unanswered select contributes nothing. The result is the
 * conjunction of every contributing value, so an empty conjunction is true.
 */
export function derivedPublicationChoice(
  definition: FeedbackDefinition,
  answers: Record<string, string | null>,
): boolean {
  let choice = true;
  for (const field of definition.fields) {
    if (field.kind !== "select") continue;
    const answer = answers[field.id];
    if (answer === null || answer === undefined) continue;
    const selected = field.options.find((option) => option.value === answer);
    if (selected === undefined) continue;
    if (typeof selected.publicIssueByDefault === "boolean") {
      choice = choice && selected.publicIssueByDefault;
    }
  }
  return choice;
}
