"use client";

import { createContext, useContext } from "react";

type DesignNodeActions = {
  updatePrompt: (nodeId: string, prompt: string) => void;
  updateTitle: (nodeId: string, title: string) => void;
  updateWhiteBackground: (nodeId: string, enabled: boolean) => void;
  selectVersion: (nodeId: string, versionId: string) => void;
  branchVersion: (nodeId: string, versionId: string) => void;
  runNode: (nodeId: string) => void;
};

export const DesignNodeActionsContext = createContext<DesignNodeActions | null>(
  null,
);

export function useDesignNodeActions(): DesignNodeActions {
  const actions = useContext(DesignNodeActionsContext);
  if (!actions) throw new Error("Design node actions are unavailable");
  return actions;
}
