"use client";

import { createContext, useContext } from "react";
import type { PromptPart } from "@/lib/graph";

type DesignNodeActions = {
  updatePrompt: (nodeId: string, prompt: string) => void;
  updateTitle: (nodeId: string, title: string) => void;
  updateWhiteBackground: (nodeId: string, enabled: boolean) => void;
  selectVersion: (nodeId: string, versionId: string) => void;
  branchVersion: (nodeId: string, versionId: string) => void;
  hideVersion: (versionId: string, hidden: boolean) => void;
  collapseVersion: (versionId: string) => void;
  viewVersions: (versionIds: string[]) => void;
  runNode: (nodeId: string) => void;
  editMask: (nodeId: string) => void;
  updateDocument: (nodeId: string, document: PromptPart[]) => void;
  candidates: (nodeId: string) => { id: string; title: string }[];
  hoverNode: (nodeId: string | null) => void;
  jumpNode: (nodeId: string) => void;
};

export const DesignNodeActionsContext = createContext<DesignNodeActions | null>(
  null,
);

export function useDesignNodeActions(): DesignNodeActions {
  const actions = useContext(DesignNodeActionsContext);
  if (!actions) throw new Error("Design node actions are unavailable");
  return actions;
}
