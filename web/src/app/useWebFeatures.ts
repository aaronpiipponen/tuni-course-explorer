/** Read the site's served feature switches from the mounted bootstrap provider. */
import { useContext } from "react";
import type { WebFeatures } from "../api/types";
import { WebFeaturesContext } from "./webFeaturesContext";

/** Read served feature switches from context. */
export function useWebFeatures(): WebFeatures {
  const features = useContext(WebFeaturesContext);
  if (!features) throw new Error("Web features provider is missing");
  return features;
}
