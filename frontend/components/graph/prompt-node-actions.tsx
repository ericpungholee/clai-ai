"use client";

import { createContext, useContext } from "react";

type UpdatePromptText = (nodeId: string, text: string) => void;

export const PromptNodeActionsContext = createContext<UpdatePromptText | null>(
  null,
);

export function useUpdatePromptText(): UpdatePromptText {
  const updatePromptText = useContext(PromptNodeActionsContext);

  if (!updatePromptText) {
    throw new Error("Prompt node actions are unavailable");
  }

  return updatePromptText;
}
