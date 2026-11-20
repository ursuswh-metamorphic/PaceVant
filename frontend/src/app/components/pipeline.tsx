import {AnimatePresence, motion, useReducedMotion} from 'motion/react';
import {Check, Circle, CircleAlert, LoaderCircle, ShieldCheck, Minus} from 'lucide-react';
import {GATES, gateStates} from '@/lib/pipeline';
import type {Job} from '@/lib/types';
import {cn} from '@/lib/utils';

export function Pipeline({job}: {job?: Job}) {
  const reduced = useReducedMotion();
  const states = gateStates(job);
  return <div className="pipeline" data-testid="execution-pipeline">
    {GATES.map((gate, index) => {
      const status = states[index];
      const Icon = status === 'passed' ? Check : status === 'running' ? LoaderCircle : ['rejected','failed','unknown'].includes(status) ? CircleAlert : status === 'skipped' ? Minus : Circle;
      return <motion.div layout={!reduced} key={gate.id} className={cn('pipeline-row', 'gate-' + status)} data-testid={'gate-' + gate.id} data-state={status}>
        <span className="gate-marker"><Icon size={15} strokeWidth={status === 'pending' ? 1.5 : 2} className={cn(status === 'running' && !reduced && 'animate-spin')}/></span>
        <div className="min-w-0 flex-1"><p className="gate-label">{gate.label}</p><p className="gate-detail">{gate.detail}</p></div>
        <AnimatePresence mode="wait"><motion.span key={status} initial={reduced ? false : {opacity:0, y:3}} animate={{opacity:1,y:0}} exit={{opacity:0}} transition={{duration:.15}} className="gate-status">{status === 'passed' ? 'Passed' : status === 'skipped' ? 'Not run' : status.charAt(0).toUpperCase() + status.slice(1)}</motion.span></AnimatePresence>
      </motion.div>;
    })}
    {!job && <div className="pipeline-idle"><ShieldCheck size={14}/><span>Checks appear only when the backend reports them.</span></div>}
  </div>;
}
