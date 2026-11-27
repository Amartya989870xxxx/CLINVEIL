import type { IconName } from "../components/common/Icon";

export interface RouteMeta {
  path: string;
  label: string;
  icon: IconName;
  group: "Workflow" | "Evidence";
}

export const ROUTES: RouteMeta[] = [
  { path: "/overview", label: "Overview", icon: "overview", group: "Workflow" },
  { path: "/process", label: "Process Dataset", icon: "process", group: "Workflow" },
  { path: "/run", label: "Processing Run", icon: "run", group: "Workflow" },
  { path: "/results", label: "Results", icon: "results", group: "Workflow" },
  { path: "/privacy", label: "Privacy & Quality", icon: "shield", group: "Evidence" },
  { path: "/preview", label: "Data Preview", icon: "preview", group: "Evidence" },
  { path: "/architecture", label: "Architecture", icon: "architecture", group: "Evidence" },
  { path: "/about", label: "About & Limitations", icon: "book", group: "Evidence" },
];
