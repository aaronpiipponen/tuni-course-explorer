/** Search's profile-owned persistent controls. */
export type SearchState = { query: string; activeOnly: boolean };
export const initialSearchState = (): SearchState => ({
  query: "",
  activeOnly: true,
});
