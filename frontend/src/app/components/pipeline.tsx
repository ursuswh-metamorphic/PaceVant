import {useState, useMemo, useEffect, useRef} from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesInitialized,
  useReactFlow,
  Handle,
  Position,
  MarkerType,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Check,
  Circle,
  CircleAlert,
  LoaderCircle,
  Minus,
  Bot,
  ShieldCheck,
  Boxes,
  Box,
  Activity,
  BadgeCheck,
  ScanLine,
  Layers,
  ReceiptText,
  GitBranch,
  Sigma,
  Focus,
  Maximize2,
  ChevronLeft,
  ChevronRight,
  ArrowDownRight,
} from 'lucide-react';
import {useReducedMotion} from 'motion/react';
import {StageDetail} from '@/components/stage-detail';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from '@/components/ui/dialog';
import {Button} from '@/components/ui/button';
import {
  workflowNodes as nodes,
  workflowNodeChecks,
  workflowNodeState,
  type ModuleState,
} from '@/lib/workflow-nodes';
import {dictionary, type Language} from '@/lib/i18n';
import type {Job} from '@/lib/types';
import {cn} from '@/lib/utils';

export const nodeState = workflowNodeState;

type SecurityNodeData = {
  index: number;
  state: ModuleState;
  language: Language;
};

type StageGroupData = {
  phase: number;
  phaseLabel: string;
  title: string;
  subtitle: string;
};

const icons = [
  ShieldCheck,
  Bot,
  Boxes,
  Box,
  Activity,
  GitBranch,
  Sigma,
  ShieldCheck,
  BadgeCheck,
  ScanLine,
  Layers,
  ReceiptText,
];

// Node coordinates: 3 rows corresponding to the 3 phases
const NODE_WIDTH = 215;
const NODE_HEIGHT = 126;

const nodeLayoutCoordinates: Array<{x: number; y: number}> = [
  // Phase 0: Chuẩn bị (Preparation) - 3 nodes
  {x: 50, y: 55},
  {x: 300, y: 55},
  {x: 550, y: 55},

  // Phase 1: Xác minh (Verification) - 4 nodes
  {x: 50, y: 235},
  {x: 300, y: 235},
  {x: 550, y: 235},
  {x: 800, y: 235},

  // Phase 2: Thực thi (Execution) - 5 nodes
  {x: 50, y: 415},
  {x: 300, y: 415},
  {x: 550, y: 415},
  {x: 800, y: 415},
  {x: 1050, y: 415},
];

function SecurityGraphNode({data}: NodeProps<Node<SecurityNodeData, 'security'>>) {
  const {index, state, language} = data;
  const node = nodes[index];
  const t = dictionary[language];
  const Icon = icons[index];

  const StatusIcon =
    state === 'passed'
      ? Check
      : state === 'running'
        ? LoaderCircle
        : ['rejected', 'failed', 'unknown'].includes(state)
          ? CircleAlert
          : state === 'skipped'
            ? Minus
            : Circle;

  return (
    <div
      className={cn('security-node', 'state-' + state)}
      tabIndex={0}
      role="button"
      aria-label={`${String(index + 1).padStart(2, '0')} ${node.label} - ${t[state]}`}
    >
      {/* Handles for intra-row and inter-row connections */}
      <Handle
        type="target"
        position={Position.Left}
        id="target-left"
        className="node-handle"
      />
      <Handle
        type="target"
        position={Position.Top}
        id="target-top"
        className="node-handle"
      />

      <div className="security-node-heading">
        <span className="security-node-icon">
          <Icon size={16} strokeWidth={1.8} />
        </span>
        <span className="security-node-number">{String(index + 1).padStart(2, '0')}</span>
      </div>

      <strong>{node.label}</strong>
      <p>{node.description[language === 'vi' ? 0 : 1]}</p>

      <span className="security-node-status">
        <StatusIcon
          size={11}
          className={state === 'running' ? 'animate-spin' : ''}
        />
        {t[state]}
      </span>

      <Handle
        type="source"
        position={Position.Right}
        id="source-right"
        className="node-handle"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="source-bottom"
        className="node-handle"
      />
    </div>
  );
}

function StageGroupNode({data}: NodeProps<Node<StageGroupData, 'stageGroup'>>) {
  return (
    <div className="stage-group-box">
      <div className="stage-group-top">
        <span className="stage-group-pill">{data.phaseLabel}</span>
        <span className="stage-group-name">{data.title}</span>
        <span className="stage-group-desc">{data.subtitle}</span>
      </div>
    </div>
  );
}

const nodeTypes = {
  security: SecurityGraphNode,
  stageGroup: StageGroupNode,
};

function ViewportNavigation({job, language}: {job?: Job; language: Language}) {
  const initialized = useNodesInitialized();
  const {fitView, setCenter, getZoom} = useReactFlow();
  const reduced = useReducedMotion();
  const [follow, setFollow] = useState(true);
  const last = useRef('');
  const [activePhase, setActivePhase] = useState<number | 'all'>('all');
  const vi = language === 'vi';

  // Initial fit view showing the whole 3-row architecture clearly
  useEffect(() => {
    if (!initialized) return;
    void fitView({
      padding: 0.1,
      minZoom: 0.5,
      maxZoom: 1,
      duration: reduced ? 0 : 400,
    });
  }, [initialized, fitView, reduced]);

  // Auto-follow running stage smoothly
  useEffect(() => {
    if (!initialized || !job || !follow) return;
    const index =
      job.terminal && job.workflow?.outcome
        ? nodes.length - 1
        : nodes.findIndex(node => node.active.includes(job.active_stage ?? ''));
    const key = job.job_id + ':' + job.active_stage + ':' + job.status;
    if (index < 0 || key === last.current) return;
    last.current = key;
    setActivePhase(nodes[index].phase);

    const pos = nodeLayoutCoordinates[index];
    if (pos) {
      void setCenter(pos.x + NODE_WIDTH / 2, pos.y + NODE_HEIGHT / 2, {
        zoom: Math.max(0.85, getZoom()),
        duration: reduced ? 0 : 300,
      });
    }
  }, [
    initialized,
    job?.job_id,
    job?.active_stage,
    job?.status,
    follow,
    getZoom,
    setCenter,
    reduced,
  ]);

  function focusPhase(value: number | 'all') {
    setFollow(false);
    setActivePhase(value);
    if (value === 'all') {
      void fitView({padding: 0.1, duration: reduced ? 0 : 300});
      return;
    }

    const phaseCenters = [
      {x: 410, y: 115, zoom: 0.95}, // Phase 0
      {x: 540, y: 295, zoom: 0.88}, // Phase 1
      {x: 670, y: 475, zoom: 0.82}, // Phase 2
    ];
    const target = phaseCenters[value];
    if (target) {
      void setCenter(target.x, target.y, {zoom: target.zoom, duration: reduced ? 0 : 300});
    }
  }

  const phaseLabels = vi
    ? ['Toàn bộ', '01 Chuẩn bị', '02 Xác minh', '03 Thực thi']
    : ['All', '01 Prepare', '02 Verify', '03 Execute'];

  return (
    <div className="graph-navigation">
      <div
        className="graph-phases"
        role="group"
        aria-label={vi ? 'Các giai đoạn xử lý' : 'Workflow phases'}
      >
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={activePhase === 'all'}
          onClick={() => focusPhase('all')}
        >
          {phaseLabels[0]}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={activePhase === 0}
          onClick={() => focusPhase(0)}
        >
          {phaseLabels[1]}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={activePhase === 1}
          onClick={() => focusPhase(1)}
        >
          {phaseLabels[2]}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={activePhase === 2}
          onClick={() => focusPhase(2)}
        >
          {phaseLabels[3]}
        </Button>
      </div>

      <div className="graph-controls-pill">
        <Button
          variant="ghost"
          size="sm"
          aria-label={vi ? 'Khung nhìn đầy đủ' : 'Fit full view'}
          onClick={() => {
            setActivePhase('all');
            void fitView({padding: 0.1, duration: reduced ? 0 : 300});
          }}
          className="graph-follow"
        >
          <Maximize2 size={13} />
          {vi ? 'Vừa khung' : 'Fit'}
        </Button>

        <Button
          variant="ghost"
          size="sm"
          aria-pressed={follow}
          onClick={() => {
            last.current = '';
            setFollow(value => !value);
          }}
          className="graph-follow"
        >
          <Focus size={13} />
          {vi ? 'Theo dõi' : 'Follow'}
        </Button>
      </div>
    </div>
  );
}

export function Pipeline({job, language}: {job?: Job; language: Language}) {
  const t = dictionary[language];
  const vi = language === 'vi';
  const reduced = useReducedMotion();
  const [selected, setSelected] = useState<number | null>(null);

  // Group background nodes framing the 3 phases
  const stageGroupNodes = useMemo<Node[]>(() => {
    return [
      {
        id: 'group-phase-0',
        type: 'stageGroup',
        position: {x: 20, y: 15},
        style: {width: 780, height: 175, zIndex: -1},
        data: {
          phase: 0,
          phaseLabel: vi ? 'Phase 01' : 'Phase 01',
          title: vi ? 'Chuẩn bị (Preparation)' : 'Preparation',
          subtitle: vi
            ? 'Owner Policy · Intent Proposal · Calldata Builder'
            : 'Owner Policy · Intent Proposal · Calldata Builder',
        },
        selectable: false,
        draggable: false,
        focusable: false,
      },
      {
        id: 'group-phase-1',
        type: 'stageGroup',
        position: {x: 20, y: 195},
        style: {width: 1030, height: 175, zIndex: -1},
        data: {
          phase: 1,
          phaseLabel: vi ? 'Phase 02' : 'Phase 02',
          title: vi ? 'Xác minh (Verification)' : 'Verification',
          subtitle: vi
            ? 'EVM Simulation · Economic Risk · ITAG Shield · Z3 Formal Proof'
            : 'EVM Simulation · Economic Risk · ITAG Shield · Z3 Formal Proof',
        },
        selectable: false,
        draggable: false,
        focusable: false,
      },
      {
        id: 'group-phase-2',
        type: 'stageGroup',
        position: {x: 20, y: 375},
        style: {width: 1280, height: 175, zIndex: -1},
        data: {
          phase: 2,
          phaseLabel: vi ? 'Phase 03' : 'Phase 03',
          title: vi ? 'Thực thi (Execution)' : 'Execution',
          subtitle: vi
            ? 'Security Decision · EIP-712 Attestation · Exact Preflight · Relayer & PolicyVault'
            : 'Security Decision · EIP-712 Attestation · Exact Preflight · Relayer & PolicyVault',
        },
        selectable: false,
        draggable: false,
        focusable: false,
      },
    ];
  }, [vi]);

  // 12 Security Nodes placed across the 3 horizontal rows
  const securityNodes = useMemo<Node[]>(
    () =>
      nodes.map((node, index) => ({
        id: String(index),
        type: 'security',
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        position: nodeLayoutCoordinates[index],
        data: {index, state: nodeState(job, index), language},
        ariaLabel: node.label,
        draggable: false,
      })),
    [job, language],
  );

  const graphNodes = useMemo(() => {
    return [...stageGroupNodes, ...securityNodes];
  }, [stageGroupNodes, securityNodes]);

  // Edges connecting nodes left-to-right within rows, and smooth transition from Row 1 -> Row 2, Row 2 -> Row 3
  const edges = useMemo(() => {
    const list = [];
    for (let i = 0; i < nodes.length - 1; i++) {
      const isRowTransition = i === 2 || i === 6;
      const targetState = nodeState(job, i + 1);
      const sourceState = nodeState(job, i);
      const isRunning = !reduced && targetState === 'running';
      const isPassed = sourceState === 'passed';

      list.push({
        id: `edge-${i}-${i + 1}`,
        source: String(i),
        target: String(i + 1),
        sourceHandle: isRowTransition ? 'source-bottom' : 'source-right',
        targetHandle: isRowTransition ? 'target-top' : 'target-left',
        type: 'smoothstep',
        pathOptions: {borderRadius: 16},
        animated: isRunning,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: isPassed ? '#10b981' : isRunning ? '#3861fb' : '#cbd5e1',
        },
        style: {
          stroke: isPassed ? '#10b981' : isRunning ? '#3861fb' : '#cbd5e1',
          strokeWidth: isRowTransition ? 2 : 1.75,
          strokeDasharray: isRunning ? '5 5' : undefined,
        },
        label: isRowTransition
          ? vi
            ? i === 2
              ? 'Sang Xác minh'
              : 'Sang Thực thi'
            : i === 2
              ? 'To Verification'
              : 'To Execution'
          : undefined,
        labelStyle: {fill: '#64748b', fontSize: 10, fontWeight: 700},
        labelBgStyle: {fill: '#ffffff', rx: 6, ry: 6, fillOpacity: 0.95},
        labelBgPadding: [6, 4] as [number, number],
      });
    }
    return list;
  }, [job, reduced, vi]);

  const selectedNode = selected !== null ? nodes[selected] : undefined;
  const SelectedIcon = selected !== null ? icons[selected] : Bot;

  return (
    <div className="execution-canvas" data-testid="execution-pipeline">
      <div className="canvas-title">
        <h3>{t.graph}</h3>
        <span>
          {vi
            ? '3 giai đoạn: Chuẩn bị → Xác minh → Thực thi (Chọn module để xem chi tiết)'
            : '3 Phases: Preparation → Verification → Execution (Click module to inspect)'}
        </span>
      </div>

      <div className="flow-viewport">
        <ReactFlow
          nodes={graphNodes}
          edges={edges}
          nodeTypes={nodeTypes}
          minZoom={0.25}
          maxZoom={1.5}
          nodesConnectable={false}
          onNodeClick={(_, node) => {
            if (node.type === 'security') {
              setSelected(Number(node.id));
            }
          }}
          onKeyDown={event => {
            if (event.key === 'Enter' || event.key === ' ') {
              const id = (event.target as HTMLElement)
                .closest('.react-flow__node')
                ?.getAttribute('data-id');
              if (id && !id.startsWith('group-')) {
                event.preventDefault();
                setSelected(Number(id));
              }
            }
          }}
          proOptions={{hideAttribution: true}}
        >
          <ViewportNavigation job={job} language={language} />
          <Background gap={24} size={1} color="#e2e8f0" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeColor={node => {
              if (node.type === 'stageGroup') return 'rgba(241, 245, 249, 0.4)';
              const state = node.data?.state;
              return state === 'passed'
                ? '#10b981'
                : state === 'running'
                  ? '#3861fb'
                  : state === 'rejected'
                    ? '#e11d48'
                    : '#cbd5e1';
            }}
            ariaLabel={vi ? 'Sơ đồ 3 giai đoạn xử lý' : '3-phase workflow map'}
          />
        </ReactFlow>
      </div>

      <div className="graph-legend">
        <span>
          <i className="legend-idle" />
          {t.idle}
        </span>
        <span>
          <i className="legend-running" />
          {t.running}
        </span>
        <span>
          <i className="legend-passed" />
          {t.passed}
        </span>
        <span>
          <i className="legend-rejected" />
          {t.rejected}
        </span>
      </div>

      <Dialog
        open={selected !== null}
        onOpenChange={open => {
          if (!open) setSelected(null);
        }}
      >
        <DialogContent className="module-sheet">
          {selectedNode && selected !== null && (
            <>
              <div className="module-sheet-heading">
                <span className="module-sheet-icon">
                  <SelectedIcon size={26} />
                </span>
                <div>
                  <DialogTitle>{selectedNode.label}</DialogTitle>
                  <span className={'module-state state-' + nodeState(job, selected)}>
                    {t[nodeState(job, selected)]}
                  </span>
                </div>
              </div>

              <DialogDescription className="module-description">
                {selectedNode.explanation[vi ? 0 : 1]}
              </DialogDescription>

              <div className="module-sequence">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={selected === 0}
                  onClick={() => setSelected(selected - 1)}
                >
                  <ChevronLeft size={14} />
                  {vi ? 'Trước' : 'Previous'}
                </Button>
                <span>
                  {String(selected + 1).padStart(2, '0')} / {nodes.length}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={selected === nodes.length - 1}
                  onClick={() => setSelected(selected + 1)}
                >
                  {vi ? 'Tiếp theo' : 'Next'}
                  <ChevronRight size={14} />
                </Button>
              </div>

              <section className="module-guide">
                <h3>{vi ? 'Module này làm gì?' : 'What does this module do?'}</h3>
                <ul>
                  {(
                    workflowNodeChecks[
                      selected === 11 ? 'RECONCILIATION' : selectedNode.events[0]
                    ] ?? []
                  ).map(check => (
                    <li key={check[1]}>{check[vi ? 0 : 1]}</li>
                  ))}
                </ul>
              </section>

              {!job?.workflow?.timeline.some(
                event =>
                  selectedNode.events.includes(event.stage) ||
                  (selectedNode.events.includes('PROOF') &&
                    event.stage === 'PROOF_REJECTION'),
              ) && (
                <div className="module-empty">
                  {nodeState(job, selected) === 'running'
                    ? vi
                      ? 'Bước này đang xử lý. Đầu ra sẽ xuất hiện khi backend ghi nhận kết quả.'
                      : 'This step is running. Output will appear when recorded by the backend.'
                    : vi
                      ? 'Chưa có kết quả xử lý tại bước này.'
                      : 'No processing result has been recorded for this step.'}
                  {job?.terminal && selectedNode.active.includes(job.active_stage ?? '') && (
                    <span className="module-stop">
                      {job.reason_code ??
                        job.workflow?.reason_code ??
                        t[nodeState(job, selected)]}
                    </span>
                  )}
                </div>
              )}

              <StageDetail
                job={job}
                index={selected}
                events={selectedNode.events}
                language={language}
              />
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
