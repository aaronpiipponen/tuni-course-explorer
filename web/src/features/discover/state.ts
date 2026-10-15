/** Discover's profile-owned mode, basis and activity controls. */
export type DiscoverState = {
  list: "next" | "recommended";
  mode: "all" | "at_least_one";
  activeOnly: boolean;
  basis: "completed" | "selected";
  basisExpanded: boolean;
};
export const initialDiscoverState = (): DiscoverState => ({
  list: "next",
  mode: "all",
  activeOnly: true,
  basis: "completed",
  basisExpanded: false,
});
