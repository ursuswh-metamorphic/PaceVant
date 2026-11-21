import {Check, Circle, CircleAlert, LoaderCircle, Minus, X} from 'lucide-react';
import type {ModuleState} from '@/lib/workflow-nodes';

/** One glyph per execution state, shared by the graph and the result panel. */
export const stateIcons: Record<ModuleState, typeof Check> = {
  idle: Circle,
  running: LoaderCircle,
  passed: Check,
  rejected: X,
  failed: CircleAlert,
  unknown: CircleAlert,
  skipped: Minus,
};
