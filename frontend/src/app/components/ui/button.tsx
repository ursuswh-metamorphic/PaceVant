import * as React from 'react';
import {Slot} from '@radix-ui/react-slot';
import {cva, type VariantProps} from 'class-variance-authority';
import {cn} from '@/lib/utils';

const variants = cva('inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-100 disabled:pointer-events-none disabled:opacity-45', {
  variants: {
    variant: {default:'bg-primary text-white hover:bg-blue-700 shadow-xs', outline:'border border-border bg-white text-foreground hover:bg-slate-50', ghost:'text-muted-foreground hover:bg-slate-100 hover:text-foreground', danger:'bg-red-50 text-red-700 border border-red-100 hover:bg-red-100'},
    size: {default:'h-10 px-4', sm:'h-8 px-3 text-xs', icon:'size-8'},
  }, defaultVariants:{variant:'default', size:'default'},
});
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> {asChild?: boolean}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({className, variant, size, asChild=false, ...props}, ref) => {
  const Comp = asChild ? Slot : 'button';
  return <Comp ref={ref} className={cn(variants({variant, size}), className)} {...props}/>;
});
Button.displayName = 'Button';
