import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import {X} from 'lucide-react';
import {cn} from '@/lib/utils';

export const Dialog = DialogPrimitive.Root;
export const DialogTitle = DialogPrimitive.Title;
export const DialogDescription = DialogPrimitive.Description;
export function DialogContent({children, className}: React.PropsWithChildren<{className?:string}>) {
  return <DialogPrimitive.Portal><DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/25 backdrop-blur-[2px]"/>
    <DialogPrimitive.Content className={cn('fixed inset-y-0 right-0 z-50 w-full max-w-2xl overflow-y-auto border-l border-border bg-white p-7 shadow-2xl outline-none', className)}>
      {children}<DialogPrimitive.Close className="absolute right-5 top-5 rounded-lg p-2 text-slate-500 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-primary" aria-label="Close details"><X size={18}/></DialogPrimitive.Close>
    </DialogPrimitive.Content></DialogPrimitive.Portal>;
}
