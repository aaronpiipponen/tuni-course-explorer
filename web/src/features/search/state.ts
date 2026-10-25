/** Search's profile-owned persistent controls. */
export type SearchState = { query: string; activeOnly: boolean };
/** Build the initial search state. */
export const initialSearchState = (): SearchState => ({
  query: "",
  activeOnly: true,
});
