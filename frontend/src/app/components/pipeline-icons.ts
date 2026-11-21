import {
  Activity,
  BadgeCheck,
  Bot,
  Box,
  Boxes,
  Check,
  Circle,
  CircleAlert,
  GitBranch,
  Layers,
  LoaderCircle,
  Minus,
  ReceiptText,
  ScanLine,
  ShieldCheck,
  Sigma,
  X,
} from 'lucide-react';
import type {ModuleState} from '@/lib/workflow-nodes';

/** One glyph per execution state, shared by the graph, the result panel and the Overview showcase. */
export const stateIcons: Record<ModuleState, typeof Check> = {
  idle: Circle,
  running: LoaderCircle,
  passed: Check,
  rejected: X,
  failed: CircleAlert,
  unknown: CircleAlert,
  skipped: Minus,
};

/** Module icons in workflowNodes order. Kept here so the Overview does not load React Flow. */
export const moduleIcons = [ShieldCheck, Bot, Boxes, Box, Activity, GitBranch, Sigma, ShieldCheck, BadgeCheck, ScanLine, Layers, ReceiptText];
