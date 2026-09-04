import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <img
      src="/brand/recoverai-coins.gif"
      alt=""
      aria-hidden="true"
      width={28}
      height={28}
      className={cn("shrink-0 object-contain", className)}
    />
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="font-display text-[1.05rem] font-bold tracking-tight text-foreground">
        Recover<span className="text-muted-foreground">AI</span>
      </span>
    </span>
  );
}
