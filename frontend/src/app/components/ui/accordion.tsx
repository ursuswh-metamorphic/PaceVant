import * as React from 'react';
import * as AccordionPrimitive from '@radix-ui/react-accordion';
import {ChevronDown} from 'lucide-react';
export const Accordion = AccordionPrimitive.Root;
export function AccordionItem({value, title, children}: React.PropsWithChildren<{value:string; title:string}>) {
  return <AccordionPrimitive.Item value={value} className="border-b border-border last:border-0">
    <AccordionPrimitive.Header><AccordionPrimitive.Trigger className="group flex w-full items-center justify-between py-5 text-left text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-primary">{title}<ChevronDown size={16} className="text-slate-400 transition-transform group-data-[state=open]:rotate-180"/></AccordionPrimitive.Trigger></AccordionPrimitive.Header>
    <AccordionPrimitive.Content className="pb-5 text-sm text-muted-foreground">{children}</AccordionPrimitive.Content>
  </AccordionPrimitive.Item>;
}
